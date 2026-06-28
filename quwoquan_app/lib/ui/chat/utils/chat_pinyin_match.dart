import 'package:lpinyin/lpinyin.dart';

/// 联系人/群聊搜索的拼音匹配真相源（chat 域与发起群聊页同源）。
///
/// 匹配顺序：原名小写包含 → 全拼小写包含 → 首字母缩略拼音小写包含。
/// 例如 `pinyinMatches('李明', 'li')` → true（全拼 liming 含 li）；
/// `pinyinMatches('李明', 'lm')` → true（缩略 lm 含 lm）。
bool pinyinMatches(String name, String query) {
  if (query.isEmpty) return true;
  final q = query.toLowerCase();
  if (name.toLowerCase().contains(q)) return true;
  final full = PinyinHelper.getPinyin(name, separator: '').toLowerCase();
  if (full.contains(q)) return true;
  final short = PinyinHelper.getShortPinyin(name).toLowerCase();
  return short.contains(q);
}
