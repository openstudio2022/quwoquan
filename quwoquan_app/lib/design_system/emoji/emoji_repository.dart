import 'dart:convert';
import 'dart:developer' as developer;

import 'package:quwoquan_app/design_system/emoji/emoji_catalog.dart';
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
    } catch (error, stackTrace) {
      // 磁盘上这条记录坏了。表情面板照常可用，但「最近使用」会看起来像从没用过，
      // 与真的没用过无从区分，所以降级必须留痕。design_system 是最底层，不能反向
      // 依赖 runtime 的遥测端口，用 developer.log（release 下同样生效）。
      developer.log(
        'recent emoji list is not decodable',
        name: 'design_system.emoji',
        error: error,
        stackTrace: stackTrace,
      );
      return [];
    }
  }

  /// 总使用统计：id -> count
  Map<String, int> getTotalCounts() =>
      _decodeCounts(_prefs.getString(_keyTotal));

  /// 待上报增量：id -> count
  Map<String, int> getIncrementalForReport() =>
      _decodeCounts(_prefs.getString(_keyIncremental));

  /// JSON 解码收口：磁盘 JSON 立即投影为 typed `id -> count`，弱类型不外泄。
  static Map<String, int> _decodeCounts(String? raw) {
    if (raw == null || raw.isEmpty) return {};
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! Map) return {};
      return decoded.map(
        (k, v) => MapEntry(
          k.toString(),
          (v is int) ? v : int.tryParse(v.toString()) ?? 0,
        ),
      );
    } catch (error, stackTrace) {
      developer.log(
        'emoji usage counts are not decodable',
        name: 'design_system.emoji',
        error: error,
        stackTrace: stackTrace,
      );
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

  Future<void> clearForTerminalAccountClosure() async {
    const keys = <String>[
      _keyRecent,
      _keyTotal,
      _keyIncremental,
      _keyLastReportDate,
    ];
    for (final key in keys) {
      await _prefs.remove(key);
    }
    if (keys.any(_prefs.containsKey)) {
      throw StateError('emoji usage cleanup verification failed');
    }
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
