// ASSISTANT_WEAK_TYPE: VENDOR_JSON — 站内/聚合搜索桥接；结果归一化后进入工具协议。

import 'package:quwoquan_app/assistant/retrieval/domain/retrieval_broker.dart';
import 'package:quwoquan_app/assistant/tool/impl/web/websearch_tool.dart';
import 'package:quwoquan_app/assistant/tool/impl/search/search_tool_contract.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_contract.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_registry.g.dart';
import 'package:quwoquan_app/core/services/search_repository.dart';

class SearchTool implements AssistantTool {
  SearchTool({
    required SearchRepository searchRepository,
    WebSearchTool? webSearchTool,
  }) : _searchRepository = searchRepository,
       _webSearchTool = webSearchTool ?? WebSearchTool();

  final SearchRepository _searchRepository;
  final WebSearchTool _webSearchTool;

  @override
  String get name => SearchToolContract.name;

  @override
  String get description => SearchToolContract.description;

  @override
  Future<AssistantToolResult> execute(AssistantToolArguments arguments) async {
    final request = SearchToolArgumentsContract.fromAssistantArguments(
      arguments,
    );
    final searchPlans = request.searchPlans;
    final queryVariants = request.queryVariants;
    if (searchPlans.length >= 2) {
      return _executeMultiQuery(request, searchPlans);
    }
    if (searchPlans.isEmpty && queryVariants.isNotEmpty) {
      final variantPlans = _searchPlansFromSeeds(request.query, queryVariants);
      if (variantPlans.length >= 2) {
        return _executeMultiQuery(request, variantPlans);
      }
    }
    final singlePlan = searchPlans.isNotEmpty ? searchPlans.first : null;
    return _executeSingleQuery(request, searchPlan: singlePlan);
  }

  Future<AssistantToolResult> _executeSingleQuery(
    SearchToolArgumentsContract arguments, {
    RetrievalSearchPlan? searchPlan,
  }) async {
    final outcome = await _runSingleQuery(arguments, searchPlan: searchPlan);
    return outcome.toToolResult();
  }

  Future<AssistantToolResult> _executeMultiQuery(
    SearchToolArgumentsContract arguments,
    List<RetrievalSearchPlan> searchPlans,
  ) async {
    final plans = searchPlans
        .where((item) => item.query.trim().isNotEmpty)
        .toList(growable: false);
    final taskResults = await Future.wait<_SearchToolExecutionOutcome>(
      plans.map((plan) {
        final singleArgs = arguments.copyWith(
          query: plan.query,
          searchPlans: const <RetrievalSearchPlan>[],
          queryVariants: const <String>[],
        );
        return _runSingleQuery(singleArgs, searchPlan: plan);
      }),
      eagerError: false,
    );
    final sections = <SearchSection>[];
    final hits = <SearchHit>[];
    final references = <SearchToolReference>[];
    final degradeSignals = <SearchDegradeSignal>[];
    final coveredDimensions = <String>{};
    final queryLabels = <String>[];
    final queriesUsed = <String>[];
    var degraded = false;
    var provider = '';
    var anySuccess = false;
    AssistantErrorCode failureCode = AssistantErrorCode.executionFailed;

    for (var i = 0; i < taskResults.length; i += 1) {
      final result = taskResults[i];
      final payload = result.payload;
      final plan = i < plans.length
          ? plans[i]
          : const RetrievalSearchPlan(query: '');
      _mergeSections(sections: sections, incoming: payload.sections);
      _mergeHits(target: hits, incoming: payload.hits);
      _mergeReferences(target: references, incoming: payload.references);
      _mergeDegradeSignals(
        target: degradeSignals,
        incoming: payload.degradeSignals,
      );
      degraded = degraded || result.degraded;
      if (provider.isEmpty) {
        provider = payload.provider.trim();
      }
      if (result.success ||
          payload.references.isNotEmpty ||
          payload.hits.isNotEmpty) {
        anySuccess = true;
        coveredDimensions.addAll(_planDimensions(plan));
      } else {
        failureCode = result.errorCode;
      }
      queryLabels.addAll(_planLabels(plan));
      final query = plan.query.trim();
      if (query.isNotEmpty) {
        queriesUsed.add(query);
      }
    }

    final missingDimensions = plans
        .expand(_planDimensions)
        .where(
          (item) => item.trim().isNotEmpty && !coveredDimensions.contains(item),
        )
        .toSet()
        .toList(growable: false);
    final normalizedRequest = arguments.toSearchRequest().normalized();
    final effectiveObjectTypes = normalizedRequest.objectTypes.isNotEmpty
        ? normalizedRequest.objectTypes
        : _defaultObjectTypes(normalizedRequest.mode);
    final summary = _buildMultiQuerySummary(
      queryLabels: queryLabels,
      coveredDimensions: coveredDimensions.toList(growable: false),
      missingDimensions: missingDimensions,
      hitCount: hits.length,
      referenceCount: references.length,
    );
    return _SearchToolExecutionOutcome(
      success: anySuccess,
      message: anySuccess ? '已完成多轮统一检索' : '未找到相关结果',
      degraded: degraded,
      errorCode: anySuccess ? AssistantErrorCode.none : failureCode,
      payload: SearchToolResultPayload(
        query: queriesUsed.isNotEmpty ? queriesUsed.first : '',
        mode: normalizedRequest.mode,
        objectTypes: effectiveObjectTypes,
        sections: sections,
        hits: hits,
        references: references,
        degradeSignals: degradeSignals,
        summary: summary,
        qualityScore: _qualityScore(
          hitCount: hits.length,
          referenceCount: references.length,
          queryCount: plans.length,
          includesWeb: references.isNotEmpty,
          includesInternal: hits.any(
            (item) => item.objectType != SearchObjectType.webDocument,
          ),
        ),
        queryCount: plans.length,
        queryLabels: queryLabels,
        coveredDimensions: coveredDimensions.toList(growable: false),
        missingDimensions: missingDimensions,
        searchPlans: plans,
        referenceCount: references.length,
        totalReferences: references.length,
        queriesUsed: queriesUsed,
        provider: provider,
      ),
    ).toToolResult();
  }

  Set<SearchObjectType> _defaultObjectTypes(SearchMode mode) {
    return switch (mode) {
      SearchMode.suggest => <SearchObjectType>{
        SearchObjectType.webDocument,
        SearchObjectType.chatContact,
        SearchObjectType.chatConversation,
        SearchObjectType.chatMessage,
        SearchObjectType.circleGroup,
        SearchObjectType.circleCircle,
      },
      SearchMode.result => <SearchObjectType>{
        SearchObjectType.webDocument,
        SearchObjectType.contentPost,
        SearchObjectType.circleCircle,
        SearchObjectType.circleGroup,
        SearchObjectType.entityHomepage,
        SearchObjectType.integrationLocationPoi,
      },
    };
  }

  Future<_SearchToolExecutionOutcome> _runSingleQuery(
    SearchToolArgumentsContract arguments, {
    RetrievalSearchPlan? searchPlan,
  }) async {
    final request = arguments.toSearchRequest();
    final normalized = request.normalized();
    if (normalized.query.isEmpty) {
      return const _SearchToolExecutionOutcome(
        success: false,
        message: 'Missing query',
        errorCode: AssistantErrorCode.invalidArguments,
        payload: SearchToolResultPayload(
          query: '',
          mode: SearchMode.result,
          objectTypes: <SearchObjectType>{},
        ),
      );
    }

    final effectiveObjectTypes = normalized.objectTypes.isNotEmpty
        ? normalized.objectTypes
        : _defaultObjectTypes(normalized.mode);
    final internalObjectTypes = effectiveObjectTypes
        .where((item) => item != SearchObjectType.webDocument)
        .toSet();
    final includesWeb = effectiveObjectTypes.contains(
      SearchObjectType.webDocument,
    );
    final sections = <SearchSection>[];
    final hits = <SearchHit>[];
    final references = <SearchToolReference>[];
    final degradeSignals = <SearchDegradeSignal>[];
    SearchResponse? internalResponse;
    AssistantToolResult? webResult;
    var webPayload = const SearchToolWebSearchPayload();
    AssistantErrorCode failureCode = AssistantErrorCode.executionFailed;
    var degraded = false;
    var provider = '';

    if (internalObjectTypes.isNotEmpty) {
      internalResponse = await _searchRepository.search(
        SearchRequest(
          query: normalized.query,
          mode: normalized.mode,
          objectTypes: internalObjectTypes,
          limit: normalized.limit,
          conversationType: normalized.conversationType,
          contentTypes: normalized.contentTypes,
          categoryId: normalized.categoryId,
          subCategory: normalized.subCategory,
        ),
      );
      _mergeSections(sections: sections, incoming: internalResponse.sections);
      _mergeHits(target: hits, incoming: internalResponse.hits);
      _mergeDegradeSignals(
        target: degradeSignals,
        incoming: internalResponse.degradeSignals,
      );
      degraded = degraded || internalResponse.degradeSignals.isNotEmpty;
    }

    if (includesWeb) {
      webResult = await _webSearchTool.execute(
        arguments.toWebSearchArguments(
          query: normalized.query,
          count: normalized.limit,
          searchPlans: searchPlan == null
              ? const <RetrievalSearchPlan>[]
              : <RetrievalSearchPlan>[searchPlan],
          queryVariants: searchPlan == null
              ? arguments.queryVariants
              : const <String>[],
        ),
      );
      webPayload = SearchToolWebSearchPayload.fromToolResult(webResult);
      provider = webPayload.provider.trim();
      _mergeReferences(target: references, incoming: webPayload.references);
      final webHits = webPayload.references
          .map((item) => item.toSearchHit())
          .toList(growable: false);
      if (webHits.isNotEmpty) {
        _mergeSections(
          sections: sections,
          incoming: <SearchSection>[
            SearchSection(
              id: 'web',
              title: '网页',
              objectTypes: const <SearchObjectType>[
                SearchObjectType.webDocument,
              ],
              hits: webHits,
              resolvedFrom: SearchResolvedFrom.remote,
            ),
          ],
        );
        _mergeHits(target: hits, incoming: webHits);
      }
      if (!webResult.success) {
        degraded = true;
        failureCode = webResult.errorCode;
        degradeSignals.add(
          const SearchDegradeSignal(
            code: 'web_search_failed',
            message: '网页检索失败',
            objectType: SearchObjectType.webDocument,
          ),
        );
      } else if (webResult.degraded) {
        degraded = true;
      }
    }

    final success = hits.isNotEmpty || references.isNotEmpty;
    final coveredDimensions = success
        ? _planDimensions(searchPlan)
        : const <String>[];
    final summary = _buildSingleQuerySummary(
      hitCount: hits.length,
      referenceCount: references.length,
      webSummary: webPayload.summary,
      includesWeb: includesWeb,
      includesInternal: internalObjectTypes.isNotEmpty,
    );
    final queryLabels = _planLabels(searchPlan);
    return _SearchToolExecutionOutcome(
      success: success,
      message: success ? '已完成统一检索' : '未找到相关结果',
      degraded: degraded,
      errorCode: success ? AssistantErrorCode.none : failureCode,
      payload: SearchToolResultPayload(
        query: normalized.query,
        mode: normalized.mode,
        objectTypes: effectiveObjectTypes,
        sections: sections,
        hits: hits,
        references: references,
        degradeSignals: degradeSignals,
        summary: summary,
        qualityScore: _qualityScore(
          hitCount: hits.length,
          referenceCount: references.length,
          queryCount: 1,
          includesWeb: includesWeb,
          includesInternal: internalObjectTypes.isNotEmpty,
        ),
        queryCount: 1,
        queryLabels: queryLabels,
        coveredDimensions: coveredDimensions,
        missingDimensions: const <String>[],
        referenceCount: references.length,
        totalReferences: references.length,
        queriesUsed: <String>[normalized.query],
        provider: provider,
        searchPlans: searchPlan == null
            ? const <RetrievalSearchPlan>[]
            : <RetrievalSearchPlan>[searchPlan],
        internalResponse: internalResponse,
      ),
    );
  }

  List<RetrievalSearchPlan> _searchPlansFromSeeds(
    String query,
    List<String> queryVariants,
  ) {
    final plans = <RetrievalSearchPlan>[];
    final seen = <String>{};
    final seeds = <String>[query.trim(), ...queryVariants];
    for (var i = 0; i < seeds.length; i += 1) {
      final item = seeds[i].trim();
      if (item.isEmpty || !seen.add(item)) {
        continue;
      }
      plans.add(
        RetrievalSearchPlan(
          id: 'query_${i + 1}',
          label: '检索${i + 1}',
          dimension: 'query_${i + 1}',
          query: item,
        ),
      );
    }
    return plans;
  }

  void _mergeSections({
    required List<SearchSection> sections,
    required Iterable<SearchSection> incoming,
  }) {
    final index = <String, int>{
      for (var i = 0; i < sections.length; i += 1) sections[i].id.trim(): i,
    };
    for (final raw in incoming) {
      final id = raw.id.trim();
      if (id.isEmpty) {
        continue;
      }
      if (!index.containsKey(id)) {
        sections.add(raw);
        index[id] = sections.length - 1;
        continue;
      }
      final existing = sections[index[id]!];
      final mergedHits = <SearchHit>[...existing.hits];
      _mergeHits(target: mergedHits, incoming: raw.hits);
      final mergedDegradeSignals = <SearchDegradeSignal>[
        ...existing.degradeSignals,
      ];
      _mergeDegradeSignals(
        target: mergedDegradeSignals,
        incoming: raw.degradeSignals,
      );
      sections[index[id]!] = SearchSection(
        id: existing.id,
        title: existing.title.trim().isNotEmpty ? existing.title : raw.title,
        objectTypes: <SearchObjectType>{
          ...existing.objectTypes,
          ...raw.objectTypes,
        }.toList(growable: false),
        hits: mergedHits,
        resolvedFrom: existing.resolvedFrom,
        degradeSignals: mergedDegradeSignals,
      );
    }
  }

  void _mergeHits({
    required List<SearchHit> target,
    required Iterable<SearchHit> incoming,
  }) {
    final seen = <String>{for (final item in target) _hitKey(item)};
    for (final item in incoming) {
      final key = _hitKey(item);
      if (key.isEmpty || !seen.add(key)) {
        continue;
      }
      target.add(item);
    }
  }

  void _mergeReferences({
    required List<SearchToolReference> target,
    required Iterable<SearchToolReference> incoming,
  }) {
    final seen = <String>{for (final item in target) _referenceKey(item)};
    for (final item in incoming) {
      final key = _referenceKey(item);
      if (key.isEmpty || !seen.add(key)) {
        continue;
      }
      target.add(item);
    }
  }

  void _mergeDegradeSignals({
    required List<SearchDegradeSignal> target,
    required Iterable<SearchDegradeSignal> incoming,
  }) {
    final seen = <String>{for (final item in target) _degradeKey(item)};
    for (final item in incoming) {
      final key = _degradeKey(item);
      if (key.isEmpty || !seen.add(key)) {
        continue;
      }
      target.add(item);
    }
  }

  String _hitKey(SearchHit hit) {
    return '${hit.objectType.wireValue}:${hit.objectId}';
  }

  String _referenceKey(SearchToolReference reference) {
    final url = reference.url.trim();
    if (url.isNotEmpty) {
      return url;
    }
    return '${reference.title.trim()}:${reference.source.trim()}';
  }

  String _degradeKey(SearchDegradeSignal signal) {
    return '${signal.code}:${signal.objectType?.wireValue ?? ""}';
  }

  List<String> _planDimensions(RetrievalSearchPlan? searchPlan) {
    if (searchPlan == null) {
      return const <String>[];
    }
    return searchPlan.dimensionLabels();
  }

  List<String> _planLabels(RetrievalSearchPlan? searchPlan) {
    if (searchPlan == null) {
      return const <String>[];
    }
    return searchPlan.labels();
  }

  String _buildSingleQuerySummary({
    required int hitCount,
    required int referenceCount,
    required String webSummary,
    required bool includesWeb,
    required bool includesInternal,
  }) {
    if (includesWeb && !includesInternal && webSummary.isNotEmpty) {
      return webSummary;
    }
    if (referenceCount > 0 && hitCount > 0) {
      return '已整理 $hitCount 条站内结果与 $referenceCount 条网页资料。';
    }
    if (referenceCount > 0) {
      return webSummary.isNotEmpty ? webSummary : '已整理 $referenceCount 条网页资料。';
    }
    if (hitCount > 0) {
      return '已整理 $hitCount 条站内检索结果。';
    }
    return '当前未检索到足够线索。';
  }

  String _buildMultiQuerySummary({
    required List<String> queryLabels,
    required List<String> coveredDimensions,
    required List<String> missingDimensions,
    required int hitCount,
    required int referenceCount,
  }) {
    final labels = queryLabels.where((item) => item.trim().isNotEmpty).toList();
    if (coveredDimensions.isNotEmpty && missingDimensions.isEmpty) {
      return '已按 ${coveredDimensions.join("、")} 这些方向交叉检索，当前整理出 ${hitCount + referenceCount} 条线索。';
    }
    if (coveredDimensions.isNotEmpty && missingDimensions.isNotEmpty) {
      return '已确认 ${coveredDimensions.join("、")}，仍缺 ${missingDimensions.join("、")}，先保留 ${hitCount + referenceCount} 条结果。';
    }
    if (labels.isNotEmpty) {
      return '已按 ${labels.join("、")} 并行检索，当前整理出 ${hitCount + referenceCount} 条线索。';
    }
    return '已完成多轮统一检索。';
  }

  double _qualityScore({
    required int hitCount,
    required int referenceCount,
    required int queryCount,
    required bool includesWeb,
    required bool includesInternal,
  }) {
    if (hitCount <= 0 && referenceCount <= 0) {
      return 0.0;
    }
    var score = 0.2;
    score += referenceCount > 0 ? 0.25 : 0.0;
    score += includesWeb && referenceCount > 0 ? 0.1 : 0.0;
    score += includesInternal && hitCount > 0 ? 0.15 : 0.0;
    score += (hitCount.clamp(0, 6)) * 0.04;
    score += (referenceCount.clamp(0, 6)) * 0.04;
    score += queryCount > 1 ? 0.1 : 0.05;
    if (score > 0.95) {
      return 0.95;
    }
    return score;
  }
}

class _SearchToolExecutionOutcome {
  const _SearchToolExecutionOutcome({
    required this.success,
    required this.message,
    required this.errorCode,
    required this.payload,
    this.degraded = false,
  });

  final bool success;
  final String message;
  final AssistantErrorCode errorCode;
  final bool degraded;
  final SearchToolResultPayload payload;

  AssistantToolResult toToolResult() {
    return AssistantToolResult(
      success: success,
      message: message,
      errorCode: errorCode,
      degraded: degraded,
      data: payload.toAssistantToolResultData(),
      runtimeFailure: success
          ? null
          : assistantToolRuntimeFailure(
              errorCode: errorCode,
              message: message,
              functionModule: 'search',
            ),
    );
  }
}
