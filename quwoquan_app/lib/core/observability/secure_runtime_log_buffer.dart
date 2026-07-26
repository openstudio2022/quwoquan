import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:quwoquan_app/core/observability/generated/runtime_log_catalog.g.dart';
import 'package:quwoquan_app/core/observability/runtime_log_ports.dart';
import 'package:quwoquan_app/core/observability/runtime_log_record.dart';

abstract interface class RuntimeLogRecordStore {
  Future<String?> read();

  Future<void> write(String value);

  Future<void> clear();
}

/// 由系统 KeyStore/Keychain 加密的本地日志存储。
final class SecureRuntimeLogRecordStore implements RuntimeLogRecordStore {
  const SecureRuntimeLogRecordStore() : _storage = const FlutterSecureStorage();

  static const _key = 'qwq.runtime_log_buffer';

  final FlutterSecureStorage _storage;

  @override
  Future<String?> read() => _storage.read(key: _key);

  @override
  Future<void> write(String value) => _storage.write(key: _key, value: value);

  @override
  Future<void> clear() => _storage.delete(key: _key);
}

/// 本地加密可靠缓冲：持久化活跃队列、attempt/nextAttemptAt 与有界 DLQ。
/// 损坏内容会清空安全存储，绝不回退明文或阻塞业务主路径。
final class SecureRuntimeLogBuffer implements ReliableRuntimeLogBuffer {
  SecureRuntimeLogBuffer({
    RuntimeLogRecordStore? store,
    this.capacity = RuntimeLogCatalog.appBufferCapacity,
    this.deadLetterCapacity = RuntimeLogCatalog.appDeadLetterCapacity,
    this.ttl = const Duration(hours: RuntimeLogCatalog.deliveryTtlHours),
  }) : _store = store ?? const SecureRuntimeLogRecordStore() {
    if (capacity <= 0 || deadLetterCapacity <= 0 || ttl <= Duration.zero) {
      throw ArgumentError('runtime log buffer limits must be positive');
    }
  }

  final RuntimeLogRecordStore _store;
  final int capacity;
  final int deadLetterCapacity;
  final Duration ttl;
  final List<_SecureQueueEntry> _entries = <_SecureQueueEntry>[];
  final List<RuntimeLogDeadLetter> _deadLetters = <RuntimeLogDeadLetter>[];
  Future<void>? _loadTask;
  Future<void> _serial = Future<void>.value();

  @override
  Future<void> append(RuntimeLogRecord record) => _enqueue(() async {
    await _ensureLoaded();
    _entries.removeWhere((item) => item.record.recordId == record.recordId);
    _entries.add(_SecureQueueEntry(record: record));
    _trimToCapacity(DateTime.now().toUtc());
    await _persist();
  });

  @override
  Future<List<RuntimeLogRecord>> pending({int limit = 50}) =>
      _enqueue(() async {
        await _ensureLoaded();
        final now = DateTime.now().toUtc();
        _expireLoaded(now);
        final ordered =
            _entries
                .where(
                  (entry) =>
                      entry.nextAttemptAt == null ||
                      !entry.nextAttemptAt!.isAfter(now),
                )
                .map((entry) => entry.record)
                .toList()
              ..sort(compareRuntimeLogPriority);
        await _persist();
        return List<RuntimeLogRecord>.unmodifiable(
          ordered.take(limit).toList(growable: false),
        );
      });

  @override
  Future<void> remove(Iterable<String> recordIds) => _enqueue(() async {
    await _ensureLoaded();
    final removed = recordIds.toSet();
    if (removed.isEmpty) return;
    _entries.removeWhere((entry) => removed.contains(entry.record.recordId));
    await _persist();
  });

  @override
  Future<void> retryLater(
    Iterable<String> recordIds, {
    required DateTime now,
  }) => _enqueue(() async {
    await _ensureLoaded();
    final ids = recordIds.toSet();
    for (final entry in _entries) {
      if (!ids.contains(entry.record.recordId)) continue;
      entry.attempts += 1;
      entry.nextAttemptAt = now.toUtc().add(_retryDelay(entry));
    }
    await _persist();
  });

  @override
  Future<void> deadLetter(
    Iterable<String> recordIds, {
    required String reason,
    required DateTime now,
  }) => _enqueue(() async {
    await _ensureLoaded();
    _deadLetterLoaded(recordIds.toSet(), reason, now.toUtc());
    await _persist();
  });

  @override
  Future<int> expire({required DateTime now}) => _enqueue(() async {
    await _ensureLoaded();
    final count = _expireLoaded(now.toUtc());
    await _persist();
    return count;
  });

  @override
  Future<List<RuntimeLogDeadLetter>> deadLetters({int limit = 50}) =>
      _enqueue(() async {
        await _ensureLoaded();
        return List<RuntimeLogDeadLetter>.unmodifiable(
          _deadLetters.reversed.take(limit),
        );
      });

  @override
  Future<DateTime?> nextDeliveryAt() => _enqueue(() async {
    await _ensureLoaded();
    if (_entries.isEmpty) return null;
    DateTime? next;
    for (final entry in _entries) {
      final candidate = entry.nextAttemptAt ?? entry.record.observedAt.toUtc();
      if (next == null || candidate.isBefore(next)) {
        next = candidate;
      }
    }
    return next;
  });

  @override
  Future<void> clear() => _enqueue(() async {
    await _ensureLoaded();
    _entries.clear();
    _deadLetters.clear();
    await _store.clear();
  });

  Future<T> _enqueue<T>(Future<T> Function() action) {
    final result = _serial.then((_) => action());
    _serial = result.then<void>((_) {}, onError: (_, _) {});
    return result;
  }

  Future<void> _ensureLoaded() {
    final task = _loadTask;
    if (task != null) return task;
    final load = _load();
    _loadTask = load;
    return load;
  }

  Future<void> _load() async {
    final encoded = await _store.read();
    if (encoded == null || encoded.trim().isEmpty) return;
    try {
      final decoded = jsonDecode(encoded);
      if (decoded is! Map) throw const FormatException('日志缓冲不是对象');
      final value = decoded.cast<String, Object?>();
      final pending = value['pending'];
      final deadLetters = value['deadLetters'];
      if (pending is! List || deadLetters is! List) {
        throw const FormatException('日志缓冲字段不完整');
      }
      for (final item in pending) {
        if (item is! Map) throw const FormatException('日志队列项不是对象');
        _entries.add(_SecureQueueEntry.fromWire(item.cast<String, Object?>()));
      }
      for (final item in deadLetters) {
        if (item is! Map) throw const FormatException('日志死信不是对象');
        _deadLetters.add(_deadLetterFromWire(item.cast<String, Object?>()));
      }
      _trimToCapacity(DateTime.now().toUtc());
      _trimDeadLetters();
      await _persist();
    } catch (_) {
      _entries.clear();
      _deadLetters.clear();
      await _store.clear();
    }
  }

  Future<void> _persist() async {
    if (_entries.isEmpty && _deadLetters.isEmpty) {
      await _store.clear();
      return;
    }
    await _store.write(
      jsonEncode(<String, Object?>{
        'pending': _entries.map((entry) => entry.toWire()).toList(),
        'deadLetters': _deadLetters
            .map(
              (item) => <String, Object?>{
                'record': item.record.toWire(),
                'reason': item.reason,
                'failedAt': item.failedAt.toIso8601String(),
              },
            )
            .toList(),
      }),
    );
  }

  int _expireLoaded(DateTime now) {
    final ids = _entries
        .where((entry) => now.difference(entry.record.occurredAt) > ttl)
        .map((entry) => entry.record.recordId)
        .toSet();
    _deadLetterLoaded(ids, 'ttl_expired', now);
    return ids.length;
  }

  void _deadLetterLoaded(Set<String> ids, String reason, DateTime now) {
    if (ids.isEmpty) return;
    final failed = _entries
        .where((entry) => ids.contains(entry.record.recordId))
        .map(
          (entry) => RuntimeLogDeadLetter(
            record: entry.record,
            reason: reason,
            failedAt: now,
          ),
        )
        .toList(growable: false);
    _entries.removeWhere((entry) => ids.contains(entry.record.recordId));
    _deadLetters.addAll(failed);
    _trimDeadLetters();
  }

  void _trimToCapacity(DateTime now) {
    while (_entries.length > capacity) {
      _entries.sort((left, right) {
        final severity = left.record.severity.index.compareTo(
          right.record.severity.index,
        );
        if (severity != 0) return severity;
        return left.record.occurredAt.compareTo(right.record.occurredAt);
      });
      final removed = _entries.removeAt(0);
      _deadLetters.add(
        RuntimeLogDeadLetter(
          record: removed.record,
          reason: 'capacity_evicted',
          failedAt: now,
        ),
      );
      _trimDeadLetters();
    }
  }

  void _trimDeadLetters() {
    final overflow = _deadLetters.length - deadLetterCapacity;
    if (overflow > 0) {
      _deadLetters.removeRange(0, overflow);
    }
  }
}

final class _SecureQueueEntry {
  _SecureQueueEntry({
    required this.record,
    this.attempts = 0,
    this.nextAttemptAt,
  });

  factory _SecureQueueEntry.fromWire(Map<String, Object?> wire) {
    final record = wire['record'];
    if (record is! Map) throw const FormatException('日志记录不是对象');
    return _SecureQueueEntry(
      record: RuntimeLogRecord.fromWire(record.cast<String, Object?>()),
      attempts: _asNonNegativeInt(wire['attempts']),
      nextAttemptAt: _optionalDateTime(wire['nextAttemptAt']),
    );
  }

  final RuntimeLogRecord record;
  int attempts;
  DateTime? nextAttemptAt;

  Map<String, Object?> toWire() => <String, Object?>{
    'record': record.toWire(),
    'attempts': attempts,
    if (nextAttemptAt != null)
      'nextAttemptAt': nextAttemptAt!.toIso8601String(),
  };
}

RuntimeLogDeadLetter _deadLetterFromWire(Map<String, Object?> wire) {
  final record = wire['record'];
  if (record is! Map) throw const FormatException('死信日志记录不是对象');
  final reason = wire['reason']?.toString().trim() ?? '';
  final failedAt = _optionalDateTime(wire['failedAt']);
  if (reason.isEmpty || failedAt == null) {
    throw const FormatException('死信字段不完整');
  }
  return RuntimeLogDeadLetter(
    record: RuntimeLogRecord.fromWire(record.cast<String, Object?>()),
    reason: reason,
    failedAt: failedAt,
  );
}

DateTime? _optionalDateTime(Object? value) {
  if (value == null) return null;
  return DateTime.tryParse(value.toString())?.toUtc();
}

int _asNonNegativeInt(Object? value) {
  final parsed = value is int ? value : int.tryParse(value?.toString() ?? '');
  if (parsed == null || parsed < 0) {
    throw const FormatException('attempts 非法');
  }
  return parsed;
}

Duration _retryDelay(_SecureQueueEntry entry) {
  final exponent = (entry.attempts - 1).clamp(
    0,
    RuntimeLogCatalog.retryMaxExponent,
  );
  final baseSeconds = (RuntimeLogCatalog.retryBaseSeconds * (1 << exponent))
      .clamp(
        RuntimeLogCatalog.retryBaseSeconds,
        RuntimeLogCatalog.retryMaxSeconds,
      );
  final hash = entry.record.recordId.codeUnits.fold<int>(
    0,
    (value, unit) => (value * 31 + unit) & 0x7fffffff,
  );
  final jitterMillis =
      baseSeconds * 1000 * (hash % RuntimeLogCatalog.retryJitterPercent) ~/ 100;
  return Duration(seconds: baseSeconds, milliseconds: jitterMillis);
}
