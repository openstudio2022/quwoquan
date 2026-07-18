// ignore_for_file: prefer_initializing_formals

import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:crypto/crypto.dart';
import 'package:quwoquan_app/app/navigation/generated/app_pages.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_context_provider.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_outbox.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_session_store.dart';

enum AppTelemetryRecordResult { accepted, sampledOut, rateLimited, rejected }

abstract interface class AppTelemetryRecorder {
  Future<AppTelemetryRecordResult> record(
    AppTelemetryPayload payload, {
    String? pageName,
    DateTime? occurredAt,
  });

  Future<AppTelemetryFlushResult> flush();

  Future<void> clearPendingForLogout();

  void onNetworkAvailable();
}

/// 严格目录化产品遥测入口。调用方只能提交 codegen 生成的强类型 payload；Reporter
/// 负责九字段上下文、采样、限流、TTL 和可靠入队，不执行同步网络请求。
final class AppTelemetryReporter implements AppTelemetryRecorder {
  AppTelemetryReporter({
    required AppTelemetrySessionStore sessionStore,
    required AppTelemetryContextProvider contextProvider,
    required AppTelemetryOutbox outbox,
    DateTime Function()? now,
    Random? random,
  }) : _sessionStore = sessionStore,
       _contextProvider = contextProvider,
       _outbox = outbox,
       _now = now ?? DateTime.now,
       _random = random ?? Random.secure(),
       _eventBucket = _TokenBucket(
         capacity: 50,
         refillPerMinute: 120,
         now: now ?? DateTime.now,
       ),
       _errorBucket = _TokenBucket(
         capacity: 10,
         refillPerMinute: 20,
         now: now ?? DateTime.now,
       );

  final AppTelemetrySessionStore _sessionStore;
  final AppTelemetryContextProvider _contextProvider;
  final AppTelemetryOutbox _outbox;
  final DateTime Function() _now;
  final Random _random;
  final _TokenBucket _eventBucket;
  final _TokenBucket _errorBucket;
  Timer? _flushTimer;
  int _retryAttempt = 0;
  bool _disposed = false;

  @override
  Future<AppTelemetryRecordResult> record(
    AppTelemetryPayload payload, {
    String? pageName,
    DateTime? occurredAt,
  }) async {
    if (_disposed) return AppTelemetryRecordResult.rejected;
    if (AppTelemetryCatalog.validate(payload) != null) {
      return AppTelemetryRecordResult.rejected;
    }
    final definition = AppTelemetryCatalog.events[payload.eventType]!;
    final resolvedPage = (pageName ?? _contextProvider.pageName).trim();
    if (!_isRegisteredPageName(resolvedPage)) {
      return AppTelemetryRecordResult.rejected;
    }
    final eventTime = (occurredAt ?? _now()).toUtc();
    final age = _now().toUtc().difference(eventTime);
    if (age > const Duration(hours: 72) ||
        eventTime.isAfter(_now().toUtc().add(const Duration(minutes: 5)))) {
      return AppTelemetryRecordResult.rejected;
    }
    final bucket = payload.logType == 'error' ? _errorBucket : _eventBucket;
    final staticContext = _contextProvider.staticContext;
    final wire = <String, Object?>{
      'logType': payload.logType,
      'eventType': payload.eventType,
      'sessionId': _sessionStore.sessionId,
      'pageName': resolvedPage,
      'occurredAt': eventTime.toIso8601String(),
      'deviceManufacturer': staticContext.deviceManufacturer,
      'deviceModel': staticContext.deviceModel,
      'appVersion': staticContext.appVersion,
      'networkClass': _contextProvider.networkClass,
      ...payload.extensions,
    };
    final ttl = payload.logType == 'error'
        ? const Duration(hours: 72)
        : const Duration(hours: 24);
    final queued = AppTelemetryQueuedRecord(
      wire: wire,
      logType: payload.logType,
      eventType: payload.eventType,
      enqueuedAt: _now().toUtc(),
      expiresAt: _now().toUtc().add(ttl),
      droppable: payload.logType == 'event' && definition.normalSampleRate < 1,
    );
    if (!bucket.take()) {
      if (payload.logType == 'error') {
        await _outbox.deadLetter(queued, reason: 'error_rate_limited');
      }
      return AppTelemetryRecordResult.rateLimited;
    }
    if (!_shouldKeep(payload, definition, wire['sessionId']!.toString())) {
      return AppTelemetryRecordResult.sampledOut;
    }
    await _outbox.enqueue(queued);
    final pending = await _outbox.pendingCount();
    if (pending >= 50) {
      unawaited(flush());
    } else {
      _scheduleFlush(
        payload.logType == 'error'
            ? const Duration(seconds: 1)
            : const Duration(seconds: 10),
      );
    }
    return AppTelemetryRecordResult.accepted;
  }

  @override
  Future<AppTelemetryFlushResult> flush() async {
    if (_disposed) return AppTelemetryFlushResult.empty;
    _flushTimer?.cancel();
    _flushTimer = null;
    final result = await _outbox.flush();
    switch (result) {
      case AppTelemetryFlushResult.delivered:
      case AppTelemetryFlushResult.deadLettered:
        _retryAttempt = 0;
        if (await _outbox.pendingCount() > 0) {
          _scheduleFlush(Duration.zero);
        }
        break;
      case AppTelemetryFlushResult.deferred:
        _retryAttempt++;
        _scheduleFlush(_retryDelay(_retryAttempt));
        break;
      case AppTelemetryFlushResult.identityBlocked:
      case AppTelemetryFlushResult.empty:
        break;
    }
    return result;
  }

  @override
  Future<void> clearPendingForLogout() => _outbox.purge();

  @override
  void onNetworkAvailable() {
    if (_disposed) return;
    _retryAttempt = 0;
    _scheduleFlush(Duration.zero);
  }

  Future<void> dispose() async {
    _disposed = true;
    _flushTimer?.cancel();
    _flushTimer = null;
  }

  bool _shouldKeep(
    AppTelemetryPayload payload,
    AppTelemetryEventDefinition definition,
    String sessionId,
  ) {
    if (payload.logType == 'error' || definition.normalSampleRate >= 1) {
      return true;
    }
    final duration = payload.extensions['durationMs'];
    if (duration is int &&
        definition.slowThresholdMs > 0 &&
        duration >= definition.slowThresholdMs) {
      return true;
    }
    if (payload.extensions['hasError'] == true) return true;
    final startupDuration = payload.extensions['tClickToContentMs'];
    if (startupDuration is int &&
        definition.slowThresholdMs > 0 &&
        startupDuration >= definition.slowThresholdMs) {
      return true;
    }
    final digest = sha256.convert(
      utf8.encode('$sessionId:${payload.eventType}'),
    );
    final bucket = (digest.bytes[0] << 8) | digest.bytes[1];
    return bucket / 65536 < definition.normalSampleRate;
  }

  bool _isRegisteredPageName(String value) {
    if (AppPages.fallbackContexts.contains(value)) return true;
    if (AppPages.internalLocations.containsValue(value)) return true;
    return AppPages.routes.any((page) => page.pageName == value);
  }

  void _scheduleFlush(Duration delay) {
    if (_disposed) return;
    if (_flushTimer != null && _flushTimer!.isActive) {
      if (delay != Duration.zero) return;
      _flushTimer!.cancel();
    }
    _flushTimer = Timer(delay, () {
      _flushTimer = null;
      unawaited(flush());
    });
  }

  Duration _retryDelay(int attempt) {
    final exponent = min(attempt - 1, 8);
    final capMs = min(300000, 1000 * (1 << exponent));
    return Duration(milliseconds: _random.nextInt(capMs + 1));
  }
}

final class _TokenBucket {
  _TokenBucket({
    required this.capacity,
    required this.refillPerMinute,
    required DateTime Function() now,
  }) : _now = now,
       _tokens = capacity.toDouble(),
       _lastRefill = now();

  final int capacity;
  final int refillPerMinute;
  final DateTime Function() _now;
  double _tokens;
  DateTime _lastRefill;

  bool take() {
    final current = _now();
    final elapsedMs = current.difference(_lastRefill).inMilliseconds;
    if (elapsedMs > 0) {
      _tokens = min(
        capacity.toDouble(),
        _tokens + elapsedMs * refillPerMinute / 60000,
      );
      _lastRefill = current;
    }
    if (_tokens < 1) return false;
    _tokens -= 1;
    return true;
  }
}
