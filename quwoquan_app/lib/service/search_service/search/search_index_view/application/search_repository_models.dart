part of "search_repository.dart";

class SearchRequest {
  const SearchRequest({
    required this.query,
    this.mode = CanonicalSearchMode.suggest,
    this.objectTypes = const <SearchObjectType>{},
    this.ids = const <String>[],
    this.limit = 0,
    this.conversationType,
    this.contentTypes = const <SearchContentTypeFilter>{},
    this.categoryId,
    this.subCategory,
    this.cursor,
  });

  final String query;
  final CanonicalSearchMode mode;
  final Set<SearchObjectType> objectTypes;
  final List<String> ids;
  final int limit;
  final String? conversationType;
  final Set<SearchContentTypeFilter> contentTypes;
  final String? categoryId;
  final String? subCategory;

  /// 服务端签发的 opaque 分页游标（响应 `nextCursor` 原样回传）；
  /// 首屏为 null。端侧不得解释或改写其内容。
  final String? cursor;

  SearchRequest normalized() {
    final trimmedQuery = query.trim();
    final normalizedLimit = limit > 0
        ? limit
        : switch (mode) {
            CanonicalSearchMode.suggest => SearchContractDefaults.suggestLimit,
            CanonicalSearchMode.result => SearchContractDefaults.resultLimit,
          };
    return SearchRequest(
      query: trimmedQuery,
      mode: mode,
      objectTypes: objectTypes,
      ids: List<String>.unmodifiable(
        ids.map((item) => item.trim()).where((item) => item.isNotEmpty),
      ),
      limit: normalizedLimit.clamp(1, 50).toInt(),
      conversationType: _normalizeConversationType(conversationType),
      contentTypes: contentTypes,
      categoryId: _normalize(categoryId),
      subCategory: _normalize(subCategory),
      cursor: _normalize(cursor),
    );
  }
}

class SearchDegradeSignal {
  const SearchDegradeSignal({
    required this.code,
    required this.message,
    this.objectType,
  });

  final String code;
  final String message;
  final SearchObjectType? objectType;
}

/// API Edge `SearchPage` flat card；objectRef 始终保持 opaque。
final class SearchPageResultItem {
  const SearchPageResultItem({
    required this.objectRef,
    required this.resultType,
    this.contentType,
    required this.title,
    this.subtitle,
    this.snippet,
    this.thumbnailUrl,
    required this.action,
    this.rankPosition = 0,
    this.rankReason,
  });

  factory SearchPageResultItem.fromWireSlice(SearchPageItem value) =>
      SearchPageResultItem(
        objectRef: value.objectRef,
        resultType: value.resultType,
        contentType: value.contentType,
        title: value.title,
        subtitle: value.subtitle,
        snippet: value.snippet,
        thumbnailUrl: value.thumbnailUrl,
        action: value.action,
        rankPosition: value.rankPosition,
        rankReason: value.rankReason,
      );

  final String objectRef;
  final SearchPageObjectType resultType;

  /// 仅 `content.post` 命中携带（article/image/video）；媒体 Tab 依赖它区分形态。
  final SearchPageContentType? contentType;
  final String title;
  final String? subtitle;
  final String? snippet;
  final String? thumbnailUrl;
  final String action;

  /// 服务端最终排序位置（0 起）；端侧只读消费，不得客户端重排。
  final int rankPosition;

  /// 服务端首要排序理由 label；null 时不展示理由标签。
  final String? rankReason;
}

final class SearchPageResultFacet {
  const SearchPageResultFacet({required this.key, required this.count});

  factory SearchPageResultFacet.fromWireSlice(SearchPageFacet value) =>
      SearchPageResultFacet(key: value.key, count: value.count);

  final String key;
  final int count;
}

/// 统一检索命中项。wire 枚举来自 `quwoquan_cloud_contracts` Search owner，
/// 默认值与执行策略来自 `search_execution_policy.g.dart`，展示分区元数据来自
/// `search_display_metadata.g.dart`。
///
/// `payload` 为 [SearchHitPayload]（sealed）；生产 adapter 必须映射为具名视图。
class SearchHit {
  const SearchHit({
    required this.objectType,
    required this.objectId,
    required this.title,
    this.subtitle,
    this.snippet,
    required this.resolvedFrom,
    this.matchedField,
    this.payload = const SearchHitPayloadEmpty(),
    this.connectionState = 'unconnected',
    this.intersectionReason,
    this.rankReasons = const <String>[],
    this.rankPosition,
    this.coverWidth,
    this.coverHeight,
  });

  final SearchObjectType objectType;
  final String objectId;
  final String title;
  final String? subtitle;
  final String? snippet;
  final SearchResolvedFrom resolvedFrom;
  final String? matchedField;
  final SearchHitPayload payload;
  final String connectionState;
  final CanonicalSearchIntersectionReason? intersectionReason;

  /// 云侧排序透明化（`_shared/search_contract.yaml` hit_fields.rankReasons）：
  /// 命中已展开为人类可读的排序理由标签。本地扇出（mock/local）为空列表。
  final List<String> rankReasons;

  /// 云侧分页内 1-based 最终排序位（hit_fields.rankPosition）。本地扇出为 null，
  /// 结果页据此决定是否消费云侧排序而非端侧 publishedAt 兜底排序（R-001）。
  final int? rankPosition;

  /// 云侧封面像素宽 / 高（hit_fields.coverWidth/coverHeight），用于结果页卡片真实宽高比；
  /// 本地扇出为 null（R-003）。
  final double? coverWidth;
  final double? coverHeight;
}

class SearchSection {
  const SearchSection({
    required this.id,
    required this.title,
    required this.objectTypes,
    required this.hits,
    required this.resolvedFrom,
    this.degradeSignals = const <SearchDegradeSignal>[],
  });

  final String id;
  final String title;
  final List<SearchObjectType> objectTypes;
  final List<SearchHit> hits;
  final SearchResolvedFrom resolvedFrom;
  final List<SearchDegradeSignal> degradeSignals;
}

class SearchResponse {
  const SearchResponse({
    required this.request,
    required this.sections,
    this.degradeSignals = const <SearchDegradeSignal>[],
    this.relatedTerms = const <String>[],
    this.matchedTerms = const <String>[],
    this.searchRequestId,
    this.pageItems = const <SearchPageResultItem>[],
    this.pageFacets = const <SearchPageResultFacet>[],
    this.nextCursor,
  });

  final SearchRequest request;
  final List<SearchSection> sections;
  final List<SearchDegradeSignal> degradeSignals;

  /// 云侧相关搜索词（`_shared/search_contract.yaml` responseFields.relatedTerms）；
  /// 结果页「相关搜索」优先消费它，本地扇出（mock/local）为空（R-003）。
  final List<String> relatedTerms;

  /// 云侧归一化命中词（查询级别对全部结果一致），用于命中片段高亮；
  /// 本地扇出为空列表。
  final List<String> matchedTerms;

  /// 云侧单次搜索请求 ID（响应 envelope `requestId`），
  /// 是搜索反馈（impression/click）归因锚点；本地扇出为 null 时不上报反馈。
  final String? searchRequestId;

  /// 新 build 的正式云结果；不映射为旧 SearchHit/SearchResponseView。
  final List<SearchPageResultItem> pageItems;
  final List<SearchPageResultFacet> pageFacets;
  final String? nextCursor;

  List<SearchHit> get hits =>
      sections.expand((section) => section.hits).toList(growable: false);
}
