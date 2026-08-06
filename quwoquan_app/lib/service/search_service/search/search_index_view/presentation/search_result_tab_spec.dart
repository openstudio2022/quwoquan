import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';

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
      label: SearchText.searchXiaoquTab,
      description: SearchText.searchXiaoquTabDescription,
    ),
    SearchResultTabSpec(
      id: SearchResultTabIds.all,
      label: SearchText.searchAllTab,
      description: SearchText.searchAllTabDescription,
    ),
    SearchResultTabSpec(
      id: SearchResultTabIds.intersection,
      label: SearchText.searchIntersectionTab,
      description: SearchText.searchIntersectionTabDescription,
    ),
    SearchResultTabSpec(
      id: SearchResultTabIds.image,
      label: SearchText.searchImageTab,
      description: SearchText.searchImageTabDescription,
    ),
    SearchResultTabSpec(
      id: SearchResultTabIds.video,
      label: SearchText.searchVideoTab,
      description: SearchText.searchVideoTabDescription,
    ),
    SearchResultTabSpec(
      id: SearchResultTabIds.article,
      label: SearchText.searchArticleTab,
      description: SearchText.searchArticleTabDescription,
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
