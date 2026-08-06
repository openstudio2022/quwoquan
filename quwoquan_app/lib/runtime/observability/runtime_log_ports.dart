import 'package:quwoquan_app/runtime/observability/generated/runtime_log_catalog.g.dart';
import 'package:quwoquan_app/runtime/observability/runtime_log_record.dart';

abstract interface class RuntimeLogBuffer {
  Future<void> append(RuntimeLogRecord record);

  Future<List<RuntimeLogRecord>> pending({int limit = 50});

  Future<void> remove(Iterable<String> recordIds);

  Future<void> clear();
}

/// 可靠投递缓冲的附加端口。生产缓冲必须实现；简单测试替身可只实现
/// [RuntimeLogBuffer]，RuntimeLogger 会保持基本投递语义。
abstract interface class ReliableRuntimeLogBuffer implements RuntimeLogBuffer {
  /// 临时失败：递增 attempt，并按指数退避 + 确定性 jitter 设置下一次投递时间。
  Future<void> retryLater(Iterable<String> recordIds, {required DateTime now});

  /// 永久失败：移出活跃队列并写入有界 DLQ，避免 422 等错误卡住队头。
  Future<void> deadLetter(
    Iterable<String> recordIds, {
    required String reason,
    required DateTime now,
  });

  /// 清理超过 TTL 的活跃记录；过期记录进入 DLQ，返回清理数量。
  Future<int> expire({required DateTime now});

  Future<List<RuntimeLogDeadLetter>> deadLetters({int limit = 50});

  /// 当前活跃队列最早允许再次投递的时间；null 表示无待投记录。
  Future<DateTime?> nextDeliveryAt();
}

final class RuntimeLogDeadLetter {
  const RuntimeLogDeadLetter({
    required this.record,
    required this.reason,
    required this.failedAt,
  });

  final RuntimeLogRecord record;
  final String reason;
  final DateTime failedAt;
}

abstract interface class RuntimeLogTransport {
  Future<int> send(List<RuntimeLogRecord> records);
}

/// Transport 用此异常明确区分永久 4xx 与可重试的网络/429/5xx。
final class RuntimeLogTransportException implements Exception {
  const RuntimeLogTransportException({
    required this.permanent,
    required this.reason,
  });

  final bool permanent;
  final String reason;

  @override
  String toString() => 'RuntimeLogTransportException($reason)';
}

final class InMemoryRuntimeLogBuffer implements ReliableRuntimeLogBuffer {
  InMemoryRuntimeLogBuffer({
    this.capacity = RuntimeLogCatalog.appBufferCapacity,
    this.deadLetterCapacity = RuntimeLogCatalog.appDeadLetterCapacity,
    this.ttl = const Duration(hours: RuntimeLogCatalog.deliveryTtlHours),
    DateTime Function()? now,
  }) : _now = now ?? DateTime.now {
    if (capacity <= 0 || deadLetterCapacity <= 0 || ttl <= Duration.zero) {
      throw ArgumentError('runtime log buffer limits must be positive');
    }
  }

  final int capacity;
  final int deadLetterCapacity;
  final Duration ttl;
  final DateTime Function() _now;
  final List<_RuntimeLogQueueEntry> _entries = <_RuntimeLogQueueEntry>[];
  final List<RuntimeLogDeadLetter> _deadLetters = <RuntimeLogDeadLetter>[];

  @override
  Future<void> append(RuntimeLogRecord record) async {
    _entries.removeWhere((entry) => entry.record.recordId == record.recordId);
    _entries.add(_RuntimeLogQueueEntry(record: record));
    _trimToCapacity();
  }

  @override
  Future<void> clear() async {
    _entries.clear();
    _deadLetters.clear();
  }

  @override
  Future<List<RuntimeLogRecord>> pending({int limit = 50}) async {
    final now = _now().toUtc();
    await expire(now: now);
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
    return List<RuntimeLogRecord>.unmodifiable(ordered.take(limit));
  }

  @override
  Future<void> remove(Iterable<String> recordIds) async {
    final ids = recordIds.toSet();
    _entries.removeWhere((entry) => ids.contains(entry.record.recordId));
  }

  @override
  Future<void> retryLater(
    Iterable<String> recordIds, {
    required DateTime now,
  }) async {
    final ids = recordIds.toSet();
    for (final entry in _entries) {
      if (!ids.contains(entry.record.recordId)) continue;
      entry.attempts += 1;
      entry.nextAttemptAt = now.toUtc().add(_retryDelay(entry));
    }
  }

  @override
  Future<void> deadLetter(
    Iterable<String> recordIds, {
    required String reason,
    required DateTime now,
  }) async {
    final ids = recordIds.toSet();
    if (ids.isEmpty) return;
    final failed = _entries
        .where((entry) => ids.contains(entry.record.recordId))
        .map(
          (entry) => RuntimeLogDeadLetter(
            record: entry.record,
            reason: reason,
            failedAt: now.toUtc(),
          ),
        )
        .toList(growable: false);
    _entries.removeWhere((entry) => ids.contains(entry.record.recordId));
    _deadLetters.addAll(failed);
    _trimDeadLetters();
  }

  @override
  Future<int> expire({required DateTime now}) async {
    final expired = _entries
        .where((entry) => now.toUtc().difference(entry.record.occurredAt) > ttl)
        .map((entry) => entry.record.recordId)
        .toList(growable: false);
    await deadLetter(expired, reason: 'ttl_expired', now: now);
    return expired.length;
  }

  @override
  Future<List<RuntimeLogDeadLetter>> deadLetters({int limit = 50}) async =>
      List<RuntimeLogDeadLetter>.unmodifiable(
        _deadLetters.reversed.take(limit),
      );

  @override
  Future<DateTime?> nextDeliveryAt() async {
    if (_entries.isEmpty) return null;
    DateTime? next;
    for (final entry in _entries) {
      final candidate = entry.nextAttemptAt ?? entry.record.observedAt.toUtc();
      if (next == null || candidate.isBefore(next)) {
        next = candidate;
      }
    }
    return next;
  }

  void _trimToCapacity() {
    while (_entries.length > capacity) {
      // 优先淘汰最低级别、最旧记录，避免 INFO 洪峰挤掉 WARN/ERROR。
      _entries.sort((left, right) {
        final severity =
            _runtimeLogSeverityRank(left.record.severity) -
            _runtimeLogSeverityRank(right.record.severity);
        if (severity != 0) return severity;
        return left.record.occurredAt.compareTo(right.record.occurredAt);
      });
      final removed = _entries.removeAt(0);
      _deadLetters.add(
        RuntimeLogDeadLetter(
          record: removed.record,
          reason: 'capacity_evicted',
          failedAt: _now().toUtc(),
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

final class _RuntimeLogQueueEntry {
  _RuntimeLogQueueEntry({required this.record});

  final RuntimeLogRecord record;
  int attempts = 0;
  DateTime? nextAttemptAt;
}

Duration _retryDelay(_RuntimeLogQueueEntry entry) {
  // 5s, 10s, 20s ...，封顶 5min；recordId hash 提供 0~24% 确定性 jitter，
  // 重启后不会形成同步重试风暴。
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

int compareRuntimeLogPriority(RuntimeLogRecord left, RuntimeLogRecord right) {
  final severity =
      _runtimeLogSeverityRank(right.severity) -
      _runtimeLogSeverityRank(left.severity);
  if (severity != 0) return severity;
  return left.occurredAt.compareTo(right.occurredAt);
}

int _runtimeLogSeverityRank(RuntimeLogSeverity severity) {
  switch (severity) {
    case RuntimeLogSeverity.error:
      return 4;
    case RuntimeLogSeverity.warn:
      return 3;
    case RuntimeLogSeverity.info:
      return 2;
    case RuntimeLogSeverity.debug:
      return 1;
  }
}
