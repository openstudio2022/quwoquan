import 'dart:async';
import 'dart:convert';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:crypto/crypto.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_trace_context_store.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/services/ops/ops_event_repository.dart';

const String kAppExceptionQueueBoxName = 'app_exception_queue';

class AppExceptionTelemetryService {
  AppExceptionTelemetryService({
    OpsEventRepository? eventRepository,
    String queueBoxName = kAppExceptionQueueBoxName,
  }) : _eventRepository = eventRepository ?? RemoteOpsEventRepository(),
       _queueBoxName = queueBoxName;

  static final AppExceptionTelemetryService instance =
      AppExceptionTelemetryService();

  final OpsEventRepository _eventRepository;
  final String _queueBoxName;

  final Set<String> _recentFingerprints = <String>{};

  Future<void> recordGlobalException({
    required String source,
    required String exceptionText,
    required String stackText,
    String pageId = 'global.app.runtime',
    String pageName = 'app',
    String surfaceId = 'global.app.runtime',
    String routeId = 'global.app.runtime',
    String operationId = 'app.runtime.capture_exception',
  }) async {
    final now = DateTime.now().toUtc();
    final fingerprint = _fingerprint(source, exceptionText, stackText);
    if (!_rememberFingerprint(fingerprint)) {
      return;
    }
    final trace = AppTraceContextStore.instance;
    final requestId = trace.newRequestId();
    final event = OpsEventRecordInput(
      eventId: 'app_exception:$requestId',
      eventType: 'exception',
      eventName: 'runtime_exception',
      eventVersion: 'v1',
      priority: 'P0',
      producer: 'app.exception',
      source: source,
      sessionId: trace.sessionId,
      pageVisitId: trace.newPageVisitId(),
      surfaceId: surfaceId,
      routeId: routeId,
      operationId: operationId,
      requestId: requestId,
      pageName: pageName,
      targetType: 'app_runtime',
      targetKey: pageId,
      entityType: 'app_runtime',
      entityId: fingerprint,
      occurredAt: now.toIso8601String(),
      clientSentAt: now.toIso8601String(),
      errorCode: 'APP.RUNTIME.uncaught_exception',
      errorModule: 'APP',
      errorKind: 'RUNTIME',
      errorReason: 'uncaught_exception',
      origin: 'localClient',
      nature: 'bug',
      failurePoint: source,
      stackHash: _stackHash(stackText),
      businessObject: 'app_runtime',
      functionModule: 'global_error_handler',
      appRuntimeEnv: CloudRuntimeConfig.appRuntimeEnv,
      appVersion: CloudRequestHeaders.appVersion,
      platform: CloudRequestHeaders.platform(),
      networkClass: await _networkClass(),
      payload: {
        'exception': _truncate(exceptionText, 2048),
        'stack': _truncate(stackText, 8192),
      },
    );
    await _enqueue(event);
    await flushPending();
  }

  Future<void> flushPending() async {
    final box = await _ensureBox();
    final events = <OpsEventRecordInput>[];
    final keys = box.keys.map((key) => key.toString()).toList(growable: false)
      ..sort();
    for (final key in keys) {
      final raw = box.get(key);
      if (raw == null || raw.isEmpty) {
        await box.delete(key);
        continue;
      }
      try {
        final decoded = (jsonDecode(raw) as Map).cast<String, Object?>();
        events.add(OpsEventRecordInput.fromJsonObject(decoded));
      } catch (_) {
        await box.delete(key);
      }
    }
    if (events.isEmpty) {
      return;
    }
    try {
      final ack = await _eventRepository.reportEventBatch(events: events);
      if (ack.acceptedCount + ack.duplicateCount >= events.length) {
        await box.clear();
      }
    } catch (_) {
      // Best effort: keep the local latest-100 queue for the next flush.
    }
  }

  Future<Box<String>> _ensureBox() async {
    if (!Hive.isBoxOpen(_queueBoxName)) {
      try {
        await Hive.initFlutter();
      } catch (_) {}
      return Hive.openBox<String>(_queueBoxName);
    }
    return Hive.box<String>(_queueBoxName);
  }

  Future<void> _enqueue(OpsEventRecordInput event) async {
    final box = await _ensureBox();
    await box.put(event.eventId, jsonEncode(event.toJson()));
    if (box.length > 100) {
      final keys = box.keys.map((key) => key.toString()).toList(growable: false)
        ..sort();
      final overflow = box.length - 100;
      for (var i = 0; i < overflow; i++) {
        await box.delete(keys[i]);
      }
    }
  }

  bool _rememberFingerprint(String fingerprint) {
    if (_recentFingerprints.contains(fingerprint)) {
      return false;
    }
    _recentFingerprints.add(fingerprint);
    if (_recentFingerprints.length > 32) {
      _recentFingerprints.remove(_recentFingerprints.first);
    }
    return true;
  }

  Future<String> _networkClass() async {
    try {
      final values = await Connectivity().checkConnectivity();
      if (values.contains(ConnectivityResult.wifi)) {
        return 'wifi';
      }
      if (values.contains(ConnectivityResult.mobile)) {
        return 'mobile';
      }
      if (values.contains(ConnectivityResult.none)) {
        return 'none';
      }
      return 'other';
    } catch (_) {
      return 'other';
    }
  }

  String _fingerprint(String source, String exceptionText, String stackText) {
    return sha256
        .convert(
          utf8.encode(
            '$source|${_truncate(exceptionText, 512)}|${_stackHead(stackText)}',
          ),
        )
        .toString()
        .substring(0, 16);
  }

  String _stackHash(String stackText) {
    return sha256
        .convert(utf8.encode(_stackHead(stackText)))
        .toString()
        .substring(0, 16);
  }

  String _stackHead(String stackText) {
    return stackText.split('\n').take(8).join('\n');
  }

  String _truncate(String value, int maxLength) {
    if (value.length <= maxLength) {
      return value;
    }
    return value.substring(0, maxLength);
  }
}
