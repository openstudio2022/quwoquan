import 'package:quwoquan_app/core/constants/emoji_category_constants.dart';

/// 分类 ID 与 [EmojiCategoryConstants.categoryEmojis] 顺序一致
const List<String> emojiCategoryIds = [
  'smiley',
  'animal',
  'food',
  'drink',
  'activity',
  'travel',
  'object',
];

/// 公共 Emoji 目录：唯一编号（categoryId_index）与字符互查
class EmojiCatalog {
  EmojiCatalog._();

  static List<List<String>> get _categories =>
      EmojiCategoryConstants.categoryEmojis;

  static final List<EmojiEntry> _allEntries = _buildEntries();
  static final Map<String, String> _idToChar = {
    for (final e in _allEntries) e.id: e.char
  };
  static final Map<String, String> _charToId = {
    for (final e in _allEntries) e.char: e.id
  };

  static List<EmojiEntry> _buildEntries() {
    final list = <EmojiEntry>[];
    for (var c = 0; c < _categories.length; c++) {
      final categoryId = emojiCategoryIds[c];
      final chars = _categories[c];
      for (var i = 0; i < chars.length; i++) {
        list.add(EmojiEntry(
          id: '${categoryId}_$i',
          char: chars[i],
          categoryId: categoryId,
        ));
      }
    }
    return list;
  }

  /// 按分类返回 (id, char) 列表，与现有七分类顺序一致
  static List<EmojiEntry> getByCategory(String categoryId) {
    final idx = emojiCategoryIds.indexOf(categoryId);
    if (idx < 0) return [];
    final chars = _categories[idx];
    return List.generate(
      chars.length,
      (i) => EmojiEntry(
        id: '${categoryId}_$i',
        char: chars[i],
        categoryId: categoryId,
      ),
    );
  }

  /// 所有分类 ID
  static List<String> get categoryIds => List.from(emojiCategoryIds);

  /// 根据 id 取字符；无则返回 null
  static String? getCharById(String id) => _idToChar[id];

  /// 根据字符反查 id；无则返回 null
  static String? getIdByChar(String char) => _charToId[char];

  /// 解析 id 或 char 为唯一 id；若无效返回 null
  static String? resolveId(String idOrChar) {
    if (_idToChar.containsKey(idOrChar)) return idOrChar;
    return _charToId[idOrChar];
  }
}

class EmojiEntry {
  const EmojiEntry({
    required this.id,
    required this.char,
    required this.categoryId,
  });
  final String id;
  final String char;
  final String categoryId;
}
