import 'package:quwoquan_app/assistant/retrieval/domain/retrieval_broker.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_contract.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_registry.g.dart';
import 'package:quwoquan_app/core/models/search_models.dart';
import 'package:quwoquan_app/core/services/search_repository.dart';

const String searchToolContractVersion = 'search_tool_v1';

class SearchToolArgumentsContract {
  const SearchToolArgumentsContract({
    required this.query,
    this.mode = SearchMode.result,
    this.objectTypes = const <SearchObjectType>{},
    this.limit = SearchContractDefaults.assistantLimit,
    this.conversationType,
    this.contentTypes = const <SearchContentTypeFilter>{},
    this.categoryId,
    this.subCategory,
    this.queryVariants = const <String>[],
    this.searchPlans = const <RetrievalSearchPlan>[],
    this.bridgePayload = const <String, Object?>{},
  });

  final String query;
  final SearchMode mode;
  final Set<SearchObjectType> objectTypes;
  final int limit;
  final String? conversationType;
  final Set<SearchContentTypeFilter> contentTypes;
  final String? categoryId;
  final String? subCategory;
  final List<String> queryVariants;
  final List<RetrievalSearchPlan> searchPlans;

  /// 仅用于工具间桥接的剩余上下文，不作为业务模型参与推导。
  final Map<String, Object?> bridgePayload;

  factory SearchToolArgumentsContract.fromAssistantArguments(
    AssistantToolArguments arguments,
  ) {
    final publicKeys = SearchToolContract.allFields.toSet();
    final bridgePayload = <String, Object?>{};
    for (final entry in arguments.entries) {
      if (publicKeys.contains(entry.key)) {
        continue;
      }
      bridgePayload[entry.key] = entry.value;
    }
    return SearchToolArgumentsContract(
      query: arguments.stringField(SearchToolFieldNames.query) ?? '',
      mode: _searchModeFromWire(
        arguments.stringField(SearchToolFieldNames.mode),
      ),
      objectTypes: arguments
          .stringListField(SearchToolFieldNames.objectTypes)
          .map(SearchObjectType.fromWire)
          .whereType<SearchObjectType>()
          .toSet(),
      limit:
          arguments.intField(SearchToolFieldNames.limit) ??
          SearchContractDefaults.assistantLimit,
      conversationType: _conversationTypeFromWire(
        arguments.stringField(SearchToolFieldNames.conversationType),
      ),
      contentTypes: arguments
          .stringListField(SearchToolFieldNames.contentTypes)
          .map(SearchContentTypeFilter.fromWire)
          .whereType<SearchContentTypeFilter>()
          .toSet(),
      categoryId: _nonEmpty(
        arguments.stringField(SearchToolFieldNames.categoryId),
      ),
      subCategory: _nonEmpty(
        arguments.stringField(SearchToolFieldNames.subCategory),
      ),
      queryVariants: arguments.stringListField(
        SearchToolFieldNames.queryVariants,
      ),
      searchPlans: RetrievalSearchPlan.listFromJson(
        arguments[SearchToolFieldNames.searchPlans],
      ),
      bridgePayload: bridgePayload,
    );
  }

  SearchToolArgumentsContract copyWith({
    String? query,
    SearchMode? mode,
    Set<SearchObjectType>? objectTypes,
    int? limit,
    String? conversationType,
    Set<SearchContentTypeFilter>? contentTypes,
    String? categoryId,
    String? subCategory,
    List<String>? queryVariants,
    List<RetrievalSearchPlan>? searchPlans,
    Map<String, Object?>? bridgePayload,
  }) {
    return SearchToolArgumentsContract(
      query: query ?? this.query,
      mode: mode ?? this.mode,
      objectTypes: objectTypes ?? this.objectTypes,
      limit: limit ?? this.limit,
      conversationType: conversationType ?? this.conversationType,
      contentTypes: contentTypes ?? this.contentTypes,
      categoryId: categoryId ?? this.categoryId,
      subCategory: subCategory ?? this.subCategory,
      queryVariants: queryVariants ?? this.queryVariants,
      searchPlans: searchPlans ?? this.searchPlans,
      bridgePayload: bridgePayload ?? this.bridgePayload,
    );
  }

  SearchRequest toSearchRequest() {
    return SearchRequest(
      query: query,
      mode: mode,
      objectTypes: objectTypes,
      limit: limit,
      conversationType: conversationType,
      contentTypes: contentTypes,
      categoryId: categoryId,
      subCategory: subCategory,
    );
  }

  AssistantToolArguments toWebSearchArguments({
    required String query,
    required int count,
    List<RetrievalSearchPlan> searchPlans = const <RetrievalSearchPlan>[],
    List<String> queryVariants = const <String>[],
  }) {
    return AssistantToolArguments(<String, Object?>{
      ...bridgePayload,
      'query': query,
      'count': count,
      if (searchPlans.isNotEmpty)
        'taskGraphSearchPlan': searchPlans
            .map((item) => item.toJson())
            .toList(growable: false),
      if (queryVariants.isNotEmpty)
        'queryVariants': queryVariants.toList(growable: false),
    });
  }
}

class SearchToolReference {
  const SearchToolReference({
    this.title = '',
    this.url = '',
    this.source = '',
    this.sourceHost = '',
    this.sourceTier = '',
    this.snippet = '',
    this.summary = '',
    this.searchPlanId = '',
    this.dimension = '',
    this.retrievedAt = '',
    this.observedAt = '',
    this.publishedAt = '',
    this.freshnessHours,
    this.freshnessKnown = false,
    this.freshnessSatisfied = false,
    this.authorityScore,
    this.relevanceScore,
    this.authorityDomains = const <String>[],
  });

  final String title;
  final String url;
  final String source;
  final String sourceHost;
  final String sourceTier;
  final String snippet;
  final String summary;
  final String searchPlanId;
  final String dimension;
  final String retrievedAt;
  final String observedAt;
  final String publishedAt;
  final int? freshnessHours;
  final bool freshnessKnown;
  final bool freshnessSatisfied;
  final double? authorityScore;
  final double? relevanceScore;
  final List<String> authorityDomains;

  factory SearchToolReference.fromJson(Object? raw) {
    final payload = AssistantToolPayload.fromJson(raw);
    return SearchToolReference(
      title: payload.stringField('title') ?? '',
      url: payload.stringField('url') ?? '',
      source: _firstNonEmpty(<String?>[
        payload.stringField('source'),
        payload.stringField('sourceDomain'),
      ]),
      sourceHost: _firstNonEmpty(<String?>[
        payload.stringField('sourceHost'),
        payload.stringField('sourceDomain'),
      ]),
      sourceTier: payload.stringField('sourceTier') ?? '',
      snippet: payload.stringField('snippet') ?? '',
      summary: payload.stringField('summary') ?? '',
      searchPlanId: payload.stringField('searchPlanId') ?? '',
      dimension: payload.stringField('dimension') ?? '',
      retrievedAt: payload.stringField('retrievedAt') ?? '',
      observedAt: payload.stringField('observedAt') ?? '',
      publishedAt: _firstNonEmpty(<String?>[
        payload.stringField('publishedAt'),
        payload.stringField('published'),
        payload.stringField('published_at'),
        payload.stringField('date'),
        payload.stringField('timestamp'),
        payload.stringField('time'),
      ]),
      freshnessHours: payload.intField('freshnessHours'),
      freshnessKnown: payload.boolField('freshnessKnown') ?? false,
      freshnessSatisfied: payload.boolField('freshnessSatisfied') ?? false,
      authorityScore: payload.doubleField('authorityScore'),
      relevanceScore: payload.doubleField('relevanceScore'),
      authorityDomains: payload.stringListField('authorityDomains'),
    );
  }

  static List<SearchToolReference> listFromJson(Object? raw) {
    if (raw is! List) {
      return const <SearchToolReference>[];
    }
    return raw
        .map(SearchToolReference.fromJson)
        .where(
          (item) => item.url.trim().isNotEmpty || item.title.trim().isNotEmpty,
        )
        .toList(growable: false);
  }

  SearchHit toSearchHit() {
    final effectiveUrl = url.trim();
    final effectiveTitle = title.trim();
    final effectiveSnippet = snippet.trim().isNotEmpty
        ? snippet.trim()
        : summary.trim();
    return SearchHit(
      objectType: SearchObjectType.webDocument,
      objectId: effectiveUrl.isNotEmpty ? effectiveUrl : effectiveTitle,
      title: effectiveTitle.isNotEmpty ? effectiveTitle : '网页结果',
      subtitle: _firstNonEmpty(<String?>[
        _nonEmpty(source),
        _nonEmpty(sourceHost),
      ]),
      snippet: effectiveSnippet.isNotEmpty ? effectiveSnippet : null,
      resolvedFrom: SearchResolvedFrom.remote,
      matchedField: 'query',
      payload: SearchHitPayloadWireMap(toJson()),
    );
  }

  Map<String, Object?> toJson() {
    return <String, Object?>{
      if (title.trim().isNotEmpty) 'title': title.trim(),
      if (url.trim().isNotEmpty) 'url': url.trim(),
      if (source.trim().isNotEmpty) 'source': source.trim(),
      if (sourceHost.trim().isNotEmpty) 'sourceHost': sourceHost.trim(),
      if (sourceTier.trim().isNotEmpty) 'sourceTier': sourceTier.trim(),
      if (snippet.trim().isNotEmpty) 'snippet': snippet.trim(),
      if (summary.trim().isNotEmpty) 'summary': summary.trim(),
      if (searchPlanId.trim().isNotEmpty) 'searchPlanId': searchPlanId.trim(),
      if (dimension.trim().isNotEmpty) 'dimension': dimension.trim(),
      if (retrievedAt.trim().isNotEmpty) 'retrievedAt': retrievedAt.trim(),
      if (observedAt.trim().isNotEmpty) 'observedAt': observedAt.trim(),
      if (publishedAt.trim().isNotEmpty) 'publishedAt': publishedAt.trim(),
      if (freshnessHours != null) 'freshnessHours': freshnessHours,
      if (freshnessKnown) 'freshnessKnown': true,
      if (freshnessSatisfied) 'freshnessSatisfied': true,
      if (authorityScore != null) 'authorityScore': authorityScore,
      if (relevanceScore != null) 'relevanceScore': relevanceScore,
      if (authorityDomains.isNotEmpty)
        'authorityDomains': authorityDomains.toList(growable: false),
    };
  }
}

class SearchToolWebSearchPayload {
  const SearchToolWebSearchPayload({
    this.provider = '',
    this.summary = '',
    this.references = const <SearchToolReference>[],
  });

  final String provider;
  final String summary;
  final List<SearchToolReference> references;

  factory SearchToolWebSearchPayload.fromToolResult(
    AssistantToolResult result,
  ) {
    final data = result.data;
    if (data == null || data.isEmptyPayload) {
      return const SearchToolWebSearchPayload();
    }
    return SearchToolWebSearchPayload(
      provider: data.stringField('provider') ?? '',
      summary: data.stringField('summary') ?? '',
      references: SearchToolReference.listFromJson(data['references']),
    );
  }
}

class SearchToolResultPayload {
  const SearchToolResultPayload({
    required this.query,
    required this.mode,
    required this.objectTypes,
    this.sections = const <SearchSection>[],
    this.hits = const <SearchHit>[],
    this.references = const <SearchToolReference>[],
    this.degradeSignals = const <SearchDegradeSignal>[],
    this.summary = '',
    this.qualityScore = 0,
    this.queryCount = 1,
    this.queryLabels = const <String>[],
    this.coveredDimensions = const <String>[],
    this.missingDimensions = const <String>[],
    this.referenceCount = 0,
    this.totalReferences = 0,
    this.queriesUsed = const <String>[],
    this.searchPlans = const <RetrievalSearchPlan>[],
    this.provider = '',
    this.internalResponse,
  });

  final String query;
  final SearchMode mode;
  final Set<SearchObjectType> objectTypes;
  final List<SearchSection> sections;
  final List<SearchHit> hits;
  final List<SearchToolReference> references;
  final List<SearchDegradeSignal> degradeSignals;
  final String summary;
  final double qualityScore;
  final int queryCount;
  final List<String> queryLabels;
  final List<String> coveredDimensions;
  final List<String> missingDimensions;
  final int referenceCount;
  final int totalReferences;
  final List<String> queriesUsed;
  final List<RetrievalSearchPlan> searchPlans;
  final String provider;
  final SearchResponse? internalResponse;

  AssistantToolResultData toAssistantToolResultData() {
    return AssistantToolResultData(<String, Object?>{
      SearchToolFieldNames.query: query,
      SearchToolFieldNames.mode: mode.wireValue,
      SearchToolFieldNames.objectTypes: objectTypes
          .map((item) => item.wireValue)
          .toList(growable: false),
      'sections': sections.map((item) => item.toMap()).toList(growable: false),
      'hits': hits.map((item) => item.toMap()).toList(growable: false),
      'references': references
          .map((item) => item.toJson())
          .toList(growable: false),
      'degradeSignals': degradeSignals
          .map((item) => item.toMap())
          .toList(growable: false),
      'summary': summary,
      'qualityScore': qualityScore,
      'queryCount': queryCount,
      'queryLabels': queryLabels.toList(growable: false),
      'coveredDimensions': coveredDimensions.toList(growable: false),
      'missingDimensions': missingDimensions.toList(growable: false),
      'referenceCount': referenceCount,
      'totalReferences': totalReferences,
      'queriesUsed': queriesUsed.toList(growable: false),
      if (provider.trim().isNotEmpty) 'provider': provider.trim(),
      if (searchPlans.isNotEmpty)
        SearchToolFieldNames.searchPlans: searchPlans
            .map((item) => item.toJson())
            .toList(growable: false),
      if (internalResponse != null) 'internal': internalResponse!.toMap(),
      'contractVersion': searchToolContractVersion,
    });
  }
}

SearchMode _searchModeFromWire(String? raw) {
  final trimmed = raw?.trim() ?? '';
  for (final mode in SearchMode.values) {
    if (mode.wireValue == trimmed) {
      return mode;
    }
  }
  return SearchMode.result;
}

String? _conversationTypeFromWire(String? raw) {
  final trimmed = raw?.trim() ?? '';
  if (trimmed.isEmpty) {
    return null;
  }
  return SearchConversationType.fromWire(trimmed)?.wireValue;
}

String? _nonEmpty(String? value) {
  final trimmed = value?.trim() ?? '';
  return trimmed.isEmpty ? null : trimmed;
}

String _firstNonEmpty(List<String?> candidates) {
  for (final candidate in candidates) {
    final trimmed = candidate?.trim() ?? '';
    if (trimmed.isNotEmpty) {
      return trimmed;
    }
  }
  return '';
}
