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
      label: '小趣',
      description: '理解这个搜索词，并给出下一步方向',
    ),
    SearchResultTabSpec(
      id: SearchResultTabIds.all,
      label: '全部',
      description: '已连接优先，未连接按类别比例发现',
    ),
    SearchResultTabSpec(
      id: SearchResultTabIds.intersection,
      label: '交集',
      description: '突出最值得连接的结果',
    ),
    SearchResultTabSpec(
      id: SearchResultTabIds.image,
      label: '图片',
      description: '双列浏览图片结果',
    ),
    SearchResultTabSpec(
      id: SearchResultTabIds.video,
      label: '视频',
      description: '双列浏览视频结果',
    ),
    SearchResultTabSpec(
      id: SearchResultTabIds.article,
      label: '长文',
      description: '单列阅读长文结果',
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
