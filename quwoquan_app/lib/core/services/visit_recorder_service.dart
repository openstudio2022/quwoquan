import 'dart:async';
import 'dart:convert';

import 'package:hive_flutter/hive_flutter.dart';
import 'package:quwoquan_app/assistant/infrastructure/infrastructure.dart';
import 'package:quwoquan_app/cloud/services/ops/ops_visit_repository.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/services/hive_runtime.dart';

const String kVisitRecordsBoxName = 'visit_records';
const String kVisitPendingSyncBoxName = 'visit_records_pending_sync';
const Duration kVisitDedupWindow = Duration(minutes: 5);

class VisitRecorderService {
  VisitRecorderService({
    String? boxName,
    OpsVisitRepository? remoteRepository,
    String currentUserId = '',
  }) : _boxName = boxName ?? kVisitRecordsBoxName,
       _remoteRepository = remoteRepository,
       _currentUserId = currentUserId.trim();

  final String _boxName;
  final OpsVisitRepository? _remoteRepository;
  final String _currentUserId;
  Timer? _pendingFlushTimer;

  Future<Box<String>?> _ensurePendingBox() async {
    return HiveRuntime.openStringBoxOrNull(kVisitPendingSyncBoxName);
  }

  Future<Box<String>?> _ensureBox() async {
    return HiveRuntime.openStringBoxOrNull(_boxName);
  }

  Future<void> recordVisit(VisitTarget target) async {
    final box = await _ensureBox();
    if (box == null) {
      if (_remoteRepository != null) {
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
      await box.put(key, jsonEncode(record.toJson()));
      shouldSyncRemote = true;
    } else {
      final withinDedup =
          now.difference(existing.lastSeenAt) < kVisitDedupWindow;
      if (withinDedup) {
        final updated = existing.copyWith(lastSeenAt: now);
        await box.put(key, jsonEncode(updated.toJson()));
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
        await box.put(key, jsonEncode(updated.toJson()));
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
      return VisitRecord.fromJson(map);
    } catch (_) {
      return null;
    }
  }

  Future<void> _syncRemote(VisitTarget target) async {
    final repository = _remoteRepository;
    if (repository == null) {
      return;
    }
    final trace = AppTraceContextStore.instance;
    final userId = _currentUserId.isNotEmpty ? _currentUserId : 'anonymous';
    final input = OpsVisitReportInput(
      userId: userId,
      targetType: _targetTypeFor(target),
      targetKey: target.targetKey,
      sessionId: trace.sessionId,
      source: _sourceFor(target),
    );
    try {
      await repository.recordVisit(input: input);
      _schedulePendingFlush(repository, delay: const Duration(seconds: 4));
    } catch (_) {
      await _enqueuePending(input);
      _schedulePendingFlush(repository, delay: const Duration(seconds: 12));
    }
  }

  void _schedulePendingFlush(
    OpsVisitRepository repository, {
    Duration delay = const Duration(seconds: 8),
  }) {
    _pendingFlushTimer?.cancel();
    _pendingFlushTimer = Timer(delay, () {
      _pendingFlushTimer = null;
      unawaited(_flushPending(repository));
    });
  }

  Future<void> _flushPending(OpsVisitRepository repository) async {
    final box = await _ensurePendingBox();
    if (box == null) {
      return;
    }
    final keys = box.keys.map((key) => key.toString()).toList(growable: false)
      ..sort();
    for (final key in keys) {
      final raw = box.get(key);
      if (raw == null || raw.isEmpty) {
        await box.delete(key);
        continue;
      }
      try {
        await repository.recordVisit(
          input: OpsVisitReportInput.fromJson(
            jsonDecode(raw) as Map<String, dynamic>,
          ),
        );
        await box.delete(key);
      } catch (_) {
        break;
      }
    }
  }

  Future<void> _enqueuePending(OpsVisitReportInput input) async {
    final box = await _ensurePendingBox();
    if (box == null) {
      return;
    }
    final key = DateTime.now().microsecondsSinceEpoch.toString();
    await box.put(key, jsonEncode(input.toJson()));
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

  String _sourceFor(VisitTarget target) {
    switch (target.type) {
      case VisitTargetType.page:
        return 'page_access';
      case VisitTargetType.entity:
        return 'entity_visit';
    }
  }
}
