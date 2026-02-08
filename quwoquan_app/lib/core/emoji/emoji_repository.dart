import 'dart:convert';

import 'package:quwoquan_app/core/emoji/emoji_catalog.dart';
import 'package:shared_preferences/shared_preferences.dart';

const String _keyRecent = 'emoji_recent';
const String _keyTotal = 'emoji_total';
const String _keyIncremental = 'emoji_incremental';
const String _keyLastReportDate = 'emoji_last_report_date';
const int _recentMaxLength = 24;

/// 公共 Emoji 库持久化：最近使用、总统计、待上报增量、上次上报日期
class EmojiRepository {
  EmojiRepository(this._prefs);

  final SharedPreferences _prefs;

  /// 最近使用：有序 id 列表（LRU，最多 _recentMaxLength）
  List<String> getRecent() {
    final raw = _prefs.getString(_keyRecent);
    if (raw == null || raw.isEmpty) return [];
    try {
      final list = jsonDecode(raw) as List<dynamic>?;
      return list?.map((e) => e.toString()).toList() ?? [];
    } catch (_) {
      return [];
    }
  }

  /// 总使用统计：id -> count
  Map<String, int> getTotalCounts() {
    final raw = _prefs.getString(_keyTotal);
    if (raw == null || raw.isEmpty) return {};
    try {
      final map = jsonDecode(raw) as Map<String, dynamic>?;
      if (map == null) return {};
      return map.map((k, v) => MapEntry(k, (v is int) ? v : int.tryParse(v.toString()) ?? 0));
    } catch (_) {
      return {};
    }
  }

  /// 待上报增量：id -> count
  Map<String, int> getIncrementalForReport() {
    final raw = _prefs.getString(_keyIncremental);
    if (raw == null || raw.isEmpty) return {};
    try {
      final map = jsonDecode(raw) as Map<String, dynamic>?;
      if (map == null) return {};
      return map.map((k, v) => MapEntry(k, (v is int) ? v : int.tryParse(v.toString()) ?? 0));
    } catch (_) {
      return {};
    }
  }

  String? getLastReportDate() => _prefs.getString(_keyLastReportDate);

  Future<void> setLastReportDate(String date) async {
    await _prefs.setString(_keyLastReportDate, date);
  }

  /// 清空待上报增量（上报成功后调用）
  Future<void> clearIncremental() async {
    await _prefs.remove(_keyIncremental);
  }

  /// 统一记录入口：更新最近使用、总统计、待上报增量
  Future<void> recordEmojiUsed(String idOrChar) async {
    final id = EmojiCatalog.resolveId(idOrChar);
    if (id == null) return;

    var recent = getRecent();
    recent.remove(id);
    recent.insert(0, id);
    if (recent.length > _recentMaxLength) {
      recent = recent.take(_recentMaxLength).toList();
    }
    await _prefs.setString(_keyRecent, jsonEncode(recent));

    final total = getTotalCounts();
    total[id] = (total[id] ?? 0) + 1;
    await _prefs.setString(_keyTotal, jsonEncode(total));

    final incremental = getIncrementalForReport();
    incremental[id] = (incremental[id] ?? 0) + 1;
    await _prefs.setString(_keyIncremental, jsonEncode(incremental));
  }

  /// 最近使用列表转为 (id, char)，便于 UI 展示
  List<EmojiEntry> getRecentEntries() {
    final ids = getRecent();
    final result = <EmojiEntry>[];
    for (final id in ids) {
      final char = EmojiCatalog.getCharById(id);
      if (char != null) {
        final cat = id.split('_').first;
        result.add(EmojiEntry(id: id, char: char, categoryId: cat));
      }
    }
    return result;
  }
}
