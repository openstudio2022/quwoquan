import 'dart:async';
import 'dart:convert';
import 'dart:developer' as developer;

import 'package:quwoquan_app/runtime/platform/app_recovery_native_bridge.dart';
import 'package:quwoquan_app/runtime/shell/recovery/recovery_operation_gateway.dart';

abstract interface class RecoveryFailureStore {
  Future<String?> read();

  Future<void> write(String value);

  Future<void> clear();
}

/// 复用最小原生桥的 KeyStore/Keychain 加密队列，首帧前也可用。
final class NativeRecoveryFailureStore implements RecoveryFailureStore {
  NativeRecoveryFailureStore({AppRecoveryNativeBridge? nativeBridge})
    : _nativeBridge = nativeBridge ?? AppRecoveryNativeBridge();

  final AppRecoveryNativeBridge _nativeBridge;

  @override
  Future<String?> read() => _nativeBridge.readRecoveryFailureQueue();

  @override
  Future<void> write(String value) async {
    if (!await _nativeBridge.writeRecoveryFailureQueue(value)) {
      throw StateError('native recovery queue write failed');
    }
  }

  @override
  Future<void> clear() async {
    if (!await _nativeBridge.clearRecoveryFailureQueue()) {
      throw StateError('native recovery queue clear failed');
    }
  }
}

final class RecoveryFailureReporter {
  RecoveryFailureReporter({
    RecoveryFailureStore? store,
    AppRecoveryNativeBridge? nativeBridge,
    RecoveryOperationGateway? gateway,
    DateTime Function()? now,
  }) : _store = store ?? NativeRecoveryFailureStore(nativeBridge: nativeBridge),
       _nativeBridge = nativeBridge ?? AppRecoveryNativeBridge(),
       _gateway = gateway ?? RecoveryOperationGateway(),
       _now = now ?? DateTime.now;

  static final RecoveryFailureReporter instance = RecoveryFailureReporter();

  static const int maxRecords = 20;
  static const int maxRecordBytes = 64 << 10;
  static const int maxMessageBytes = 2 << 10;
  static const int maxStackBytes = 32 << 10;
  static const Duration retention = Duration(days: 7);
  static const Duration sourceTypeRateWindow = Duration(seconds: 15);

  final RecoveryFailureStore _store;
  final AppRecoveryNativeBridge _nativeBridge;
  final RecoveryOperationGateway _gateway;
  final DateTime Function() _now;
  final Map<String, DateTime> _recentSourceTypes = <String, DateTime>{};
  Future<void> _serial = Future<void>.value();
  bool _flushing = false;

  Future<bool> record({
    required String errorSource,
    required String errorType,
    required String errorMessage,
    required String stackTrace,
    DateTime? occurredAt,
  }) async {
    try {
      final context = await _nativeBridge.context();
      if (context == null) return false;
      final now = _now().toUtc();
      final source = _normalizeSource(errorSource);
      final type = _normalizeType(errorType);
      final rateKey = '$source:$type';
      final previous = _recentSourceTypes[rateKey];
      if (previous != null && now.difference(previous) < sourceTypeRateWindow) {
        return true;
      }
      final failure = <String, Object?>{
        'occurredAt': (occurredAt ?? now).toUtc().toIso8601String(),
        'appVersion': context.appVersion,
        'buildNumber': '${context.buildNumber}',
        'platform': context.platform,
        'osVersion': _truncateUtf8(context.osVersion, 64),
        'deviceModel': _truncateUtf8(context.deviceModel, 128),
        'errorSource': source,
        'errorType': type,
        'errorMessage': _truncateUtf8(_sanitize(errorMessage), maxMessageBytes),
        'stackTrace': _truncateUtf8(_sanitize(stackTrace), maxStackBytes),
      };
      if ((failure['errorMessage'] as String).isEmpty) {
        failure['errorMessage'] = 'Unrecoverable application failure';
      }
      if ((failure['stackTrace'] as String).isEmpty) {
        failure['stackTrace'] = 'Stack trace unavailable';
      }
      if (utf8.encode(jsonEncode(failure)).length > maxRecordBytes) {
        return false;
      }

      var persisted = false;
      await _enqueue(() async {
        final queue = await _loadQueue(now);
        queue.add(
          _QueuedRecoveryFailure(failure: failure, savedAt: now, attempts: 0),
        );
        queue.sort((left, right) => left.savedAt.compareTo(right.savedAt));
        while (queue.length > maxRecords) {
          queue.removeAt(0);
        }
        await _persist(queue);
        persisted = true;
      });
      if (persisted) {
        _recentSourceTypes[rateKey] = now;
        unawaited(flush());
      }
      return persisted;
    } catch (_) {
      return false;
    }
  }

  Future<void> recordPendingNativeStartupFatal() async {
    final pending = await _nativeBridge.readPendingNativeStartupFatal();
    if (pending == null) return;
    final rawOccurredAt = pending['occurredAt']?.toString() ?? '';
    final persisted = await record(
      errorSource: 'native',
      errorType: pending['errorType']?.toString() ?? 'NativeStartupCrash',
      errorMessage: 'Native startup terminated before safe shell',
      stackTrace: 'Native stack unavailable after process termination',
      occurredAt: DateTime.tryParse(rawOccurredAt),
    );
    if (persisted) {
      await _nativeBridge.acknowledgePendingNativeStartupFatal();
    }
  }

  Future<void> flush() => _enqueue(() async {
    if (_flushing) return;
    _flushing = true;
    try {
      final now = _now().toUtc();
      final queue = await _loadQueue(now);
      if (queue.isEmpty) {
        await _persist(queue);
        return;
      }
      final context = await _nativeBridge.context();
      if (context == null) return;
      final retained = <_QueuedRecoveryFailure>[];
      for (final entry in queue) {
        try {
          await _gateway.reportRecoveryFailure(
            binding: context.runtimeBinding,
            request: entry.toRequest(),
          );
        } catch (_) {
          retained.add(entry.incremented());
        }
      }
      await _persist(retained);
    } catch (_) {
      // 队列、插件或网络异常不得形成第二次启动崩溃。
    } finally {
      _flushing = false;
    }
  });

  Future<T> _enqueue<T>(Future<T> Function() action) {
    final result = _serial.then((_) => action());
    _serial = result.then<void>((_) {}, onError: (_, _) {});
    return result;
  }

  Future<List<_QueuedRecoveryFailure>> _loadQueue(DateTime now) async {
    final raw = await _store.read();
    if (raw == null || raw.trim().isEmpty) return <_QueuedRecoveryFailure>[];
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! List) throw const FormatException('queue is not a list');
      final queue = decoded
          .map(_QueuedRecoveryFailure.fromWire)
          .where((entry) => now.difference(entry.savedAt) <= retention)
          .toList(growable: true);
      queue.sort((left, right) => left.savedAt.compareTo(right.savedAt));
      while (queue.length > maxRecords) {
        queue.removeAt(0);
      }
      return queue;
    } catch (error, stackTrace) {
      // 队列坏了就丢掉重来，否则每次启动都会在同一条记录上失败。但「丢掉了几条
      // 待上报的恢复失败」本身就是要上报的事实，而这里正是上报器自己，不能自指，
      // 用 developer.log。
      developer.log(
        'recovery failure queue is not decodable, dropping it',
        name: 'runtime.recovery',
        error: error,
        stackTrace: stackTrace,
      );
      await _store.clear();
      return <_QueuedRecoveryFailure>[];
    }
  }

  Future<void> _persist(List<_QueuedRecoveryFailure> queue) {
    if (queue.isEmpty) return _store.clear();
    return _store.write(
      jsonEncode(queue.map((entry) => entry.toWire()).toList()),
    );
  }

  static String _normalizeSource(String raw) {
    final source = raw.trim().toLowerCase();
    return source == 'native' || source == 'runtime' ? source : 'flutter';
  }

  static String _normalizeType(String raw) {
    final normalized = raw.trim().replaceAll(RegExp(r'[^A-Za-z0-9_.-]'), '_');
    if (normalized.isEmpty) return 'UnhandledException';
    return normalized.length <= 128 ? normalized : normalized.substring(0, 128);
  }

  static String _sanitize(String raw) {
    var value = raw.trim();
    value = value.replaceAll(
      RegExp(
        r'(access[_-]?token|refresh[_-]?token|authorization|cookie)\s*[:=]\s*[^\s,;]+',
        caseSensitive: false,
      ),
      r'$1=<redacted>',
    );
    value = value.replaceAll(
      RegExp(r'[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}', caseSensitive: false),
      '<redacted-email>',
    );
    value = value.replaceAll(
      RegExp(r'(?:\+?86[- ]?)?1[3-9][0-9]{9}'),
      '<redacted-phone>',
    );
    value = value.replaceAll(
      RegExp(r'(/Users/|/home/|\\Users\\)[^/\\\s]+', caseSensitive: false),
      r'$1<redacted>',
    );
    value = value.replaceAll(
      RegExp(r'(https://[^\s?#]+)\?[^\s#]*'),
      r'$1?<redacted>',
    );
    return value;
  }

  static String _truncateUtf8(String raw, int maxBytes) {
    if (utf8.encode(raw).length <= maxBytes) return raw;
    final buffer = StringBuffer();
    var used = 0;
    for (final rune in raw.runes) {
      final scalar = String.fromCharCode(rune);
      final bytes = utf8.encode(scalar).length;
      if (used + bytes > maxBytes) break;
      buffer.write(scalar);
      used += bytes;
    }
    return buffer.toString();
  }
}

final class _QueuedRecoveryFailure {
  const _QueuedRecoveryFailure({
    required this.failure,
    required this.savedAt,
    required this.attempts,
  });

  factory _QueuedRecoveryFailure.fromWire(Object? raw) {
    if (raw is! Map) throw const FormatException('invalid queue entry');
    final wire = raw.cast<String, Object?>();
    final failure = wire['failure'];
    final savedAt = DateTime.tryParse(wire['savedAt']?.toString() ?? '');
    final attempts = int.tryParse(wire['attempts']?.toString() ?? '');
    if (failure is! Map ||
        savedAt == null ||
        attempts == null ||
        attempts < 0) {
      throw const FormatException('invalid queue entry values');
    }
    final normalized = failure.cast<String, Object?>();
    const exactFields = <String>{
      'occurredAt',
      'appVersion',
      'buildNumber',
      'platform',
      'osVersion',
      'deviceModel',
      'errorSource',
      'errorType',
      'errorMessage',
      'stackTrace',
    };
    if (normalized.keys.toSet().difference(exactFields).isNotEmpty ||
        exactFields.difference(normalized.keys.toSet()).isNotEmpty) {
      throw const FormatException('invalid recovery failure fields');
    }
    return _QueuedRecoveryFailure(
      failure: normalized,
      savedAt: savedAt.toUtc(),
      attempts: attempts,
    );
  }

  final Map<String, Object?> failure;
  final DateTime savedAt;
  final int attempts;

  _QueuedRecoveryFailure incremented() => _QueuedRecoveryFailure(
    failure: failure,
    savedAt: savedAt,
    attempts: attempts + 1,
  );

  RecoveryFailurePayload toRequest() {
    return RecoveryFailurePayload(
      occurredAt: DateTime.parse(failure['occurredAt']! as String).toUtc(),
      appVersion: failure['appVersion']! as String,
      buildNumber: failure['buildNumber']! as String,
      platform: failure['platform']! as String,
      osVersion: failure['osVersion']! as String,
      deviceModel: failure['deviceModel']! as String,
      errorSource: failure['errorSource']! as String,
      errorType: failure['errorType']! as String,
      errorMessage: failure['errorMessage']! as String,
      stackTrace: failure['stackTrace']! as String,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    'failure': failure,
    'savedAt': savedAt.toUtc().toIso8601String(),
    'attempts': attempts,
  };
}
