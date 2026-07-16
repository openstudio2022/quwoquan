part of "search_repository.dart";

class SearchRequest {
  const SearchRequest({
    required this.query,
    this.mode = SearchMode.suggest,
    this.objectTypes = const <SearchObjectType>{},
    this.limit = 0,
    this.conversationType,
    this.contentTypes = const <SearchContentTypeFilter>{},
    this.categoryId,
    this.subCategory,
  });

  final String query;
  final SearchMode mode;
  final Set<SearchObjectType> objectTypes;
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
            SearchMode.suggest => SearchContractDefaults.suggestLimit,
            SearchMode.result => SearchContractDefaults.resultLimit,
          };
    return SearchRequest(
      query: trimmedQuery,
      mode: mode,
      objectTypes: objectTypes,
      limit: normalizedLimit.clamp(1, 50).toInt(),
      conversationType: _normalizeConversationType(conversationType),
      contentTypes: contentTypes,
      categoryId: _normalize(categoryId),
      subCategory: _normalize(subCategory),
    );
  }

  Map<String, dynamic> toMap() {
    final normalizedRequest = normalized();
    return <String, dynamic>{
      SearchToolFieldNames.query: normalizedRequest.query,
      SearchToolFieldNames.mode: normalizedRequest.mode.wireValue,
      SearchToolFieldNames.objectTypes: normalizedRequest.objectTypes
          .map((item) => item.wireValue)
          .toList(growable: false),
      SearchToolFieldNames.limit: normalizedRequest.limit,
      if (normalizedRequest.conversationType != null)
        SearchToolFieldNames.conversationType:
            normalizedRequest.conversationType,
      if (normalizedRequest.contentTypes.isNotEmpty)
        SearchToolFieldNames.contentTypes: normalizedRequest.contentTypes
            .map((item) => item.wireValue)
            .toList(growable: false),
      if (normalizedRequest.categoryId != null)
        SearchToolFieldNames.categoryId: normalizedRequest.categoryId,
      if (normalizedRequest.subCategory != null)
        SearchToolFieldNames.subCategory: normalizedRequest.subCategory,
    };
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

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      'code': code,
      'message': message,
      if (objectType != null) 'objectType': objectType!.wireValue,
    };
  }
}

/// 统一检索命中项。枚举与默认值对齐 `_shared/search_contract.yaml`（`search_contract.g.dart`）；
/// 分区元数据见 `search_registry.g.dart`。
///
/// `payload` 为 [SearchHitPayload]（sealed）；帖子/圈子等已收口为具名 codegen 视图，其余为 [SearchHitPayloadWireMap]。
class SearchHit {
  const SearchHit({
    required this.objectType,
    required this.objectId,
    required this.title,
    this.subtitle,
    this.snippet,
    required this.resolvedFrom,
    this.matchedField,
    this.payload = const SearchHitPayloadWireMap(),
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

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      'objectType': objectType.wireValue,
      'objectId': objectId,
      'title': title,
      if (subtitle != null) 'subtitle': subtitle,
      if (snippet != null) 'snippet': snippet,
      'resolvedFrom': resolvedFrom.wireValue,
      if (matchedField != null) 'matchedField': matchedField,
      'payload': payload.toWireMap(),
      if (rankReasons.isNotEmpty) 'rankReasons': rankReasons,
      if (rankPosition != null) 'rankPosition': rankPosition,
      if (coverWidth != null) 'coverWidth': coverWidth,
      if (coverHeight != null) 'coverHeight': coverHeight,
    };
  }
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

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      'id': id,
      'title': title,
      'objectTypes': objectTypes
          .map((item) => item.wireValue)
          .toList(growable: false),
      'resolvedFrom': resolvedFrom.wireValue,
      'hits': hits.map((item) => item.toMap()).toList(growable: false),
      'degradeSignals': degradeSignals
          .map((item) => item.toMap())
          .toList(growable: false),
    };
  }
}

class SearchResponse {
  const SearchResponse({
    required this.request,
    required this.sections,
    this.degradeSignals = const <SearchDegradeSignal>[],
    this.relatedTerms = const <String>[],
  });

  final SearchRequest request;
  final List<SearchSection> sections;
  final List<SearchDegradeSignal> degradeSignals;

  /// 云侧相关搜索词（`_shared/search_contract.yaml` responseFields.relatedTerms）；
  /// 结果页「相关搜索」优先消费它，本地扇出（mock/local）为空（R-003）。
  final List<String> relatedTerms;

  List<SearchHit> get hits =>
      sections.expand((section) => section.hits).toList(growable: false);

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      'request': request.toMap(),
      'sections': sections.map((item) => item.toMap()).toList(growable: false),
      'hits': hits.map((item) => item.toMap()).toList(growable: false),
      'degradeSignals': degradeSignals
          .map((item) => item.toMap())
          .toList(growable: false),
      if (relatedTerms.isNotEmpty) 'relatedTerms': relatedTerms,
    };
  }
}
