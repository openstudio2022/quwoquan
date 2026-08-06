import 'dart:async';
import 'dart:convert';

import 'package:hive_flutter/hive_flutter.dart';
import 'package:quwoquan_app/runtime/models/visit_models.dart';
import 'package:quwoquan_app/runtime/observability/visit/visit_append_port.dart';
import 'package:quwoquan_app/runtime/platform/storage/hive_runtime.dart';

const String kVisitRecordsBoxName = 'visit_records';
const String kVisitPendingSyncBoxName = 'visit_records_pending_sync';
const Duration kVisitDedupWindow = Duration(minutes: 5);

/// Local experience hints are rebuildable and must not grow with every entity
/// ever opened during a long-lived account session. The most recently visited
/// targets survive; an evicted target is treated as first-time locally until a
/// later authoritative projection is loaded or it is visited again.
const int kVisitRecordRetentionLimit = 2048;

class VisitRecorderService {
  VisitRecorderService({String? boxName, VisitAppendPort? remoteWriter})
    : this._(boxName ?? kVisitRecordsBoxName, remoteWriter);

  VisitRecorderService._(this._boxName, this._remoteWriter);

  final String _boxName;
  final VisitAppendPort? _remoteWriter;
  Timer? _pendingFlushTimer;
  bool _terminallyPurged = false;

  Future<Box<String>?> _ensurePendingBox() async {
    return HiveRuntime.openStringBoxOrNull(kVisitPendingSyncBoxName);
  }

  Future<Box<String>?> _ensureBox() async {
    return HiveRuntime.openStringBoxOrNull(_boxName);
  }

  Future<void> recordVisit(VisitTarget target) async {
    if (_terminallyPurged) {
      return;
    }
    final box = await _ensureBox();
    if (_terminallyPurged) {
      return;
    }
    if (box == null) {
      if (_remoteWriter != null) {
        unawaited(_syncRemote(target));
      }
      return;
    }
    final key = target.targetKey;
    final now = DateTime.now();
    final existing = _getRecordFromBox(box, key);
    var shouldSyncRemote = false;

    if (existing == null) {
      final record = VisitRecord(
        targetKey: key,
        firstSeenAt: now,
        lastSeenAt: now,
        visitCount: 1,
        count7d: 1,
        count30d: 1,
        lastSeenTimestamps: <String>[now.toIso8601String()],
      );
      await box.put(key, jsonEncode(record.toStorageMap()));
      await _pruneRetainedRecords(box, protectedKey: key);
      shouldSyncRemote = true;
    } else {
      final withinDedup =
          now.difference(existing.lastSeenAt) < kVisitDedupWindow;
      if (withinDedup) {
        final updated = existing.copyWith(lastSeenAt: now);
        await box.put(key, jsonEncode(updated.toStorageMap()));
      } else {
        final timestamps = List<String>.from(existing.lastSeenTimestamps)
          ..add(now.toIso8601String());
        if (timestamps.length > VisitRecord.kMaxTimestamps) {
          timestamps.removeRange(
            0,
            timestamps.length - VisitRecord.kMaxTimestamps,
          );
        }
        final dates = timestamps.map(DateTime.parse).toList(growable: false);
        final sevenDaysAgo = now.subtract(const Duration(days: 7));
        final thirtyDaysAgo = now.subtract(const Duration(days: 30));
        final count7d = dates.where((d) => d.isAfter(sevenDaysAgo)).length;
        final count30d = dates.where((d) => d.isAfter(thirtyDaysAgo)).length;

        final updated = existing.copyWith(
          lastSeenAt: now,
          visitCount: existing.visitCount + 1,
          count7d: count7d,
          count30d: count30d,
          lastSeenTimestamps: timestamps,
        );
        await box.put(key, jsonEncode(updated.toStorageMap()));
        shouldSyncRemote = true;
      }
    }

    if (shouldSyncRemote) {
      unawaited(_syncRemote(target));
    }
  }

  ExperienceLevel getExperience(VisitTarget target) {
    final record = getRecord(target);
    if (record == null) return ExperienceLevel.firstTime;
    if (record.visitCount == 1) return ExperienceLevel.firstTime;
    if (record.visitCount >= 5 ||
        record.count7d >= 5 ||
        record.count30d >= 10) {
      return ExperienceLevel.frequent;
    }
    return ExperienceLevel.returning;
  }

  VisitRecord? getRecord(VisitTarget target) {
    return _getRecord(target.targetKey);
  }

  VisitRecord? _getRecord(String key) {
    if (!Hive.isBoxOpen(_boxName)) return null;
    return _getRecordFromBox(Hive.box<String>(_boxName), key);
  }

  static VisitRecord? _getRecordFromBox(Box<String> box, String key) {
    final raw = box.get(key);
    if (raw == null) return null;
    try {
      final map = jsonDecode(raw) as Map<String, dynamic>;
      return VisitRecord.fromStorageMap(map);
    } catch (_) {
      return null;
    }
  }

  static Future<void> _pruneRetainedRecords(
    Box<String> box, {
    required String protectedKey,
  }) async {
    if (box.length <= kVisitRecordRetentionLimit) {
      return;
    }
    final candidates = <({String key, DateTime lastSeenAt})>[];
    for (final rawKey in box.keys) {
      final key = rawKey.toString();
      if (key == protectedKey) {
        continue;
      }
      final record = _getRecordFromBox(box, key);
      candidates.add((
        key: key,
        lastSeenAt:
            record?.lastSeenAt ?? DateTime.fromMillisecondsSinceEpoch(0),
      ));
    }
    candidates.sort((left, right) {
      final byLastSeen = left.lastSeenAt.compareTo(right.lastSeenAt);
      if (byLastSeen != 0) {
        return byLastSeen;
      }
      return left.key.compareTo(right.key);
    });
    final overflow = box.length - kVisitRecordRetentionLimit;
    await box.deleteAll(
      candidates.take(overflow).map((candidate) => candidate.key),
    );
  }

  /// 为本次真实访问派生稳定幂等键：网络重试与断网补传复用同一 key，
  /// 服务端据此不重复累加 visitCount。
  static String _newVisitIdempotencyKey(String targetKey) {
    final micros = DateTime.now().microsecondsSinceEpoch;
    final targetHash = targetKey.codeUnits.fold<int>(
      17,
      (hash, unit) => (hash * 31 + unit) & 0x7fffffff,
    );
    return 'visit_${micros}_$targetHash';
  }

  Future<void> _syncRemote(VisitTarget target) async {
    if (_terminallyPurged) {
      return;
    }
    final writer = _remoteWriter;
    if (writer == null) {
      return;
    }
    final input = VisitAppendInput(
      idempotencyKey: _newVisitIdempotencyKey(target.targetKey),
      targetType: _targetTypeFor(target),
      targetKey: target.targetKey,
    );
    try {
      await writer.recordVisit(input);
      if (_terminallyPurged) {
        return;
      }
      _schedulePendingFlush(writer, delay: const Duration(seconds: 4));
    } catch (_) {
      if (_terminallyPurged) {
        return;
      }
      await _enqueuePending(input);
      _schedulePendingFlush(writer, delay: const Duration(seconds: 12));
    }
  }

  void _schedulePendingFlush(
    VisitAppendPort writer, {
    Duration delay = const Duration(seconds: 8),
  }) {
    if (_terminallyPurged) {
      return;
    }
    _pendingFlushTimer?.cancel();
    _pendingFlushTimer = Timer(delay, () {
      _pendingFlushTimer = null;
      unawaited(_flushPending(writer));
    });
  }

  Future<void> _flushPending(VisitAppendPort writer) async {
    if (_terminallyPurged) {
      return;
    }
    final box = await _ensurePendingBox();
    if (_terminallyPurged || box == null) {
      return;
    }
    final keys = box.keys.map((key) => key.toString()).toList(growable: false)
      ..sort();
    for (final key in keys) {
      if (_terminallyPurged) {
        break;
      }
      final raw = box.get(key);
      if (raw == null || raw.isEmpty) {
        await box.delete(key);
        continue;
      }
      try {
        await writer.recordVisit(
          VisitAppendInput.fromStorageJson(
            jsonDecode(raw) as Map<String, dynamic>,
          ),
        );
        await box.delete(key);
      } catch (_) {
        break;
      }
    }
  }

  Future<void> _enqueuePending(VisitAppendInput input) async {
    if (_terminallyPurged) {
      return;
    }
    final box = await _ensurePendingBox();
    if (_terminallyPurged || box == null) {
      return;
    }
    final key = DateTime.now().microsecondsSinceEpoch.toString();
    await box.put(key, jsonEncode(input.toStorageJson()));
    const maxBacklog = 200;
    if (box.length > maxBacklog) {
      final keys =
          box.keys.map((value) => value.toString()).toList(growable: false)
            ..sort();
      final overflow = box.length - maxBacklog;
      for (var i = 0; i < overflow; i++) {
        await box.delete(keys[i]);
      }
    }
  }

  Future<void> clearForTerminalAccountClosure() async {
    _terminallyPurged = true;
    _pendingFlushTimer?.cancel();
    _pendingFlushTimer = null;
    for (final boxName in <String>[_boxName, kVisitPendingSyncBoxName]) {
      final box = await HiveRuntime.openStringBoxOrNull(boxName);
      if (box == null) {
        continue;
      }
      await box.clear();
      if (box.isNotEmpty) {
        throw StateError(
          'visit state cleanup verification failed for $boxName',
        );
      }
    }
  }

  String _targetTypeFor(VisitTarget target) {
    switch (target.type) {
      case VisitTargetType.page:
        return 'page';
      case VisitTargetType.entity:
        switch (target.entityKind) {
          case VisitEntityKind.author:
            return 'user';
          case VisitEntityKind.circle:
            return 'circle';
          case null:
            return 'entity';
        }
    }
  }
}
