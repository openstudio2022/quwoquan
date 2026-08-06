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
    this.searchRequestId,
  });

  final SearchRequest request;
  final List<SearchSection> sections;
  final List<SearchDegradeSignal> degradeSignals;

  /// 云侧相关搜索词（`_shared/search_contract.yaml` responseFields.relatedTerms）；
  /// 结果页「相关搜索」优先消费它，本地扇出（mock/local）为空（R-003）。
  final List<String> relatedTerms;

  /// 云侧单次搜索请求 ID（响应 envelope `requestId`），
  /// 是搜索反馈（impression/click）归因锚点；本地扇出为 null 时不上报反馈。
  final String? searchRequestId;

  List<SearchHit> get hits =>
      sections.expand((section) => section.hits).toList(growable: false);
}
