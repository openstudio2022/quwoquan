import 'dart:convert';

import 'package:hive_flutter/hive_flutter.dart';

import 'package:quwoquan_app/core/models/visit_models.dart';

/// 浏览记录持久化 box 名称。
const String kVisitRecordsBoxName = 'visit_records';

/// 同一 target 在此时长内的重复 recordVisit 仅更新 lastSeenAt，不增加 visitCount。
const Duration kVisitDedupWindow = Duration(minutes: 5);

/// 浏览记录服务：记录访问、查询记录与体验等级。
/// 使用 Hive 单 box [kVisitRecordsBoxName]，key 为 [VisitTarget.targetKey]。
class VisitRecorderService {
  VisitRecorderService({String? boxName})
      : _boxName = boxName ?? kVisitRecordsBoxName;

  final String _boxName;

  /// 确保 box 已打开（热重载或测试环境可能未经过 main 初始化）
  Future<Box<String>> _ensureBox() async {
    if (!Hive.isBoxOpen(_boxName)) {
      try {
        await Hive.initFlutter();
      } catch (_) {}
      return Hive.openBox<String>(_boxName);
    }
    return Hive.box<String>(_boxName);
  }

  /// 记录一次访问。同一 [target] 在 [kVisitDedupWindow] 内重复调用仅更新 lastSeenAt。
  Future<void> recordVisit(VisitTarget target) async {
    final box = await _ensureBox();
    final key = target.targetKey;
    final now = DateTime.now();
    final existing = _getRecordFromBox(box, key);

    if (existing == null) {
      final record = VisitRecord(
        targetKey: key,
        firstSeenAt: now,
        lastSeenAt: now,
        visitCount: 1,
        count7d: 1,
        count30d: 1,
        lastSeenTimestamps: [now.toIso8601String()],
      );
      await box.put(key, jsonEncode(record.toJson()));
      return;
    }

    final withinDedup = now.difference(existing.lastSeenAt) < kVisitDedupWindow;
    if (withinDedup) {
      final updated = existing.copyWith(lastSeenAt: now);
      await box.put(key, jsonEncode(updated.toJson()));
      return;
    }

    final timestamps = List<String>.from(existing.lastSeenTimestamps)
      ..add(now.toIso8601String());
    if (timestamps.length > VisitRecord.kMaxTimestamps) {
      timestamps.removeRange(0, timestamps.length - VisitRecord.kMaxTimestamps);
    }
    final dates = timestamps.map((s) => DateTime.parse(s)).toList();
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
  }

  /// 返回 [target] 的体验等级。
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

  /// 返回 [target] 的访问记录，不存在则 null。
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
}
