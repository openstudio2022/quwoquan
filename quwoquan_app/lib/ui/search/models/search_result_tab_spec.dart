import 'package:quwoquan_app/core/constants/ui_text_constants.dart';

class SearchResultTabIds {
  const SearchResultTabIds._();

  static const String xiaoqu = 'xiaoqu';
  static const String all = 'all';
  static const String intersection = 'intersection';
  static const String image = 'image';
  static const String video = 'video';
  static const String article = 'article';

  static const Set<String> redirectedResultTabIds = <String>{
    'humanity',
    'locations',
    'homepages',
    'groups',
    'messages',
    'contacts',
    'content',
  };
}

class SearchResultTabSpec {
  const SearchResultTabSpec({
    required this.id,
    required this.label,
    required this.description,
  });

  final String id;
  final String label;
  final String description;

  static const List<SearchResultTabSpec> fixedTabs = <SearchResultTabSpec>[
    SearchResultTabSpec(
      id: SearchResultTabIds.xiaoqu,
      label: UITextConstants.searchXiaoquTab,
      description: UITextConstants.searchXiaoquTabDescription,
    ),
    SearchResultTabSpec(
      id: SearchResultTabIds.all,
      label: UITextConstants.searchAllTab,
      description: UITextConstants.searchAllTabDescription,
    ),
    SearchResultTabSpec(
      id: SearchResultTabIds.intersection,
      label: UITextConstants.searchIntersectionTab,
      description: UITextConstants.searchIntersectionTabDescription,
    ),
    SearchResultTabSpec(
      id: SearchResultTabIds.image,
      label: UITextConstants.searchImageTab,
      description: UITextConstants.searchImageTabDescription,
    ),
    SearchResultTabSpec(
      id: SearchResultTabIds.video,
      label: UITextConstants.searchVideoTab,
      description: UITextConstants.searchVideoTabDescription,
    ),
    SearchResultTabSpec(
      id: SearchResultTabIds.article,
      label: UITextConstants.searchArticleTab,
      description: UITextConstants.searchArticleTabDescription,
    ),
  ];

  static String? normalizeInitialTabId(String? tabId) {
    final normalized = tabId?.trim();
    if (normalized == null || normalized.isEmpty) {
      return null;
    }
    if (SearchResultTabIds.redirectedResultTabIds.contains(normalized)) {
      return SearchResultTabIds.all;
    }
    final known = fixedTabs.any((tab) => tab.id == normalized);
    return known ? normalized : SearchResultTabIds.all;
  }
}
