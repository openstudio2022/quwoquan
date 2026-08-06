import 'package:quwoquan_app/service/search_service/search/search_index_view/application/public/search_query_contract.dart';

final class SearchLaunchContext {
  const SearchLaunchContext({
    required this.entrySurfaceId,
    this.initialScope = SearchScope.all,
    this.searchObjectSelection = const SearchObjectSelection(),
    this.prefilledQuery = '',
    this.restoreState = true,
    this.initialFacet,
    this.initialNetworkTabId,
  });

  final String entrySurfaceId;
  final SearchScope initialScope;
  final SearchObjectSelection searchObjectSelection;
  final String prefilledQuery;
  final bool restoreState;
  final String? initialFacet;
  final String? initialNetworkTabId;

  SearchLaunchContext copyWith({
    String? entrySurfaceId,
    SearchScope? initialScope,
    SearchObjectSelection? searchObjectSelection,
    String? prefilledQuery,
    bool? restoreState,
    String? initialFacet,
    String? initialNetworkTabId,
  }) {
    return SearchLaunchContext(
      entrySurfaceId: entrySurfaceId ?? this.entrySurfaceId,
      initialScope: initialScope ?? this.initialScope,
      searchObjectSelection:
          searchObjectSelection ?? this.searchObjectSelection,
      prefilledQuery: prefilledQuery ?? this.prefilledQuery,
      restoreState: restoreState ?? this.restoreState,
      initialFacet: initialFacet ?? this.initialFacet,
      initialNetworkTabId: initialNetworkTabId ?? this.initialNetworkTabId,
    );
  }

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) {
      return true;
    }
    return other is SearchLaunchContext &&
        entrySurfaceId == other.entrySurfaceId &&
        initialScope == other.initialScope &&
        searchObjectSelection == other.searchObjectSelection &&
        prefilledQuery == other.prefilledQuery &&
        restoreState == other.restoreState &&
        initialFacet == other.initialFacet &&
        initialNetworkTabId == other.initialNetworkTabId;
  }

  @override
  int get hashCode => Object.hash(
    entrySurfaceId,
    initialScope,
    searchObjectSelection,
    prefilledQuery,
    restoreState,
    initialFacet,
    initialNetworkTabId,
  );
}

/// 从全局搜索进入会话时携带的强类型锚点。
///
/// 该值对象属于 Search 的公开 application 边界；Chat 和 runtime router 只消费
/// 这条窄契约，不依赖 Search 的 presentation 或 adapter 实现。
final class SearchConversationAnchorContext {
  const SearchConversationAnchorContext({
    required this.messageAnchorId,
    this.sourceQuery,
  });

  final String messageAnchorId;
  final String? sourceQuery;
}
