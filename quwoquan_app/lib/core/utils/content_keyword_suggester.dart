/// 从正式 Post 文本中提取一个待用户确认的屏蔽关键词候选。
///
/// 只负责候选，不直接写 UserSettings；最终值必须由用户确认。
String suggestContentBlockedKeyword(Iterable<String> sources) {
  for (final source in sources) {
    final text = source.trim();
    if (text.isEmpty) continue;
    final hashtag = RegExp(r'#([^#\s]{2,24})').firstMatch(text)?.group(1);
    if (hashtag != null && hashtag.trim().isNotEmpty) {
      return hashtag.trim();
    }
    final tokens = text
        .split(RegExp(r'[^\u4e00-\u9fa5A-Za-z0-9_]+', unicode: true))
        .map((value) => value.trim())
        .where((value) => value.length >= 2);
    for (final token in tokens) {
      final runes = token.runes.toList(growable: false);
      return String.fromCharCodes(runes.take(24));
    }
  }
  return '';
}
