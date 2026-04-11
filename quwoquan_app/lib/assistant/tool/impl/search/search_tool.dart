// ASSISTANT_WEAK_TYPE: VENDOR_JSON — 站内/聚合搜索桥接；结果归一化后进入工具协议。

import 'package:quwoquan_app/assistant/tool/impl/web/websearch_tool.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_contract.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_registry.g.dart';
import 'package:quwoquan_app/core/models/search_models.dart';
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
  Future<AssistantToolResult> execute(Map<String, dynamic> arguments) async {
    final queryTasks = _normalizeQueryTasks(
      arguments[SearchToolFieldNames.queryTasks],
    );
    final queryVariants =
        (arguments[SearchToolFieldNames.queryVariants] as List?)
            ?.whereType<String>()
            .map((item) => item.trim())
            .where((item) => item.isNotEmpty)
            .toList(growable: false) ??
        const <String>[];
    if (queryTasks.length >= 2) {
      return _executeMultiQuery(arguments, queryTasks);
    }
    if (queryTasks.isEmpty && queryVariants.isNotEmpty) {
      final variantTasks = _queryTasksFromSeeds(
        (arguments[SearchToolFieldNames.query] as String?)?.trim() ?? '',
        queryVariants,
      );
      if (variantTasks.length >= 2) {
        return _executeMultiQuery(arguments, variantTasks);
      }
    }
    final singleTask = queryTasks.isNotEmpty ? queryTasks.first : null;
    return _executeSingleQuery(arguments, queryTask: singleTask);
  }

  SearchRequest _requestFromArguments(Map<String, dynamic> arguments) {
    final rawObjectTypes =
        (arguments[SearchToolFieldNames.objectTypes] as List?)
            ?.whereType<String>()
            .map(SearchObjectType.fromWire)
            .whereType<SearchObjectType>()
            .toSet() ??
        const <SearchObjectType>{};
    final rawContentTypes =
        (arguments[SearchToolFieldNames.contentTypes] as List?)
            ?.whereType<String>()
            .map(SearchContentTypeFilter.fromWire)
            .whereType<SearchContentTypeFilter>()
            .toSet() ??
        const <SearchContentTypeFilter>{};
    return SearchRequest(
      query: (arguments[SearchToolFieldNames.query] as String?)?.trim() ?? '',
      mode: _modeFromArguments(arguments),
      objectTypes: rawObjectTypes,
      limit:
          (arguments[SearchToolFieldNames.limit] as num?)?.toInt() ??
          SearchContractDefaults.assistantLimit,
      conversationType: _conversationTypeFromArguments(arguments),
      contentTypes: rawContentTypes,
      categoryId: (arguments[SearchToolFieldNames.categoryId] as String?)
          ?.trim(),
      subCategory: (arguments[SearchToolFieldNames.subCategory] as String?)
          ?.trim(),
    );
  }

  SearchMode _modeFromArguments(Map<String, dynamic> arguments) {
    final raw = (arguments[SearchToolFieldNames.mode] as String?)?.trim();
    if (raw == null || raw.isEmpty) {
      return SearchMode.result;
    }
    for (final mode in SearchMode.values) {
      if (mode.wireValue == raw) {
        return mode;
      }
    }
    return SearchMode.result;
  }

  String? _conversationTypeFromArguments(Map<String, dynamic> arguments) {
    final raw = (arguments[SearchToolFieldNames.conversationType] as String?)
        ?.trim();
    if (raw == null || raw.isEmpty) {
      return null;
    }
    return SearchConversationType.fromWire(raw)?.wireValue;
  }

  Future<AssistantToolResult> _executeSingleQuery(
    Map<String, dynamic> arguments, {
    Map<String, dynamic>? queryTask,
  }) async {
    final request = _requestFromArguments(arguments);
    final normalized = request.normalized();
    if (normalized.query.isEmpty) {
      return const AssistantToolResult(
        success: false,
        message: 'Missing query',
        errorCode: AssistantErrorCode.invalidArguments,
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
    final sections = <Map<String, dynamic>>[];
    final hits = <Map<String, dynamic>>[];
    final references = <Map<String, dynamic>>[];
    final degradeSignals = <Map<String, dynamic>>[];
    SearchResponse? internalResponse;
    AssistantToolResult? webResult;
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
      _mergeSectionMaps(
        sections: sections,
        incoming: internalResponse.sections.map((item) => item.toMap()),
      );
      _mergeMapList(
        target: hits,
        incoming: internalResponse.hits.map((item) => item.toMap()),
        keyOf: _hitKey,
      );
      _mergeMapList(
        target: degradeSignals,
        incoming: internalResponse.degradeSignals.map((item) => item.toMap()),
        keyOf: _degradeKey,
      );
      degraded = degraded || internalResponse.degradeSignals.isNotEmpty;
    }

    if (includesWeb) {
      webResult = await _webSearchTool.execute(<String, dynamic>{
        ...arguments,
        SearchToolFieldNames.query: normalized.query,
        'count': normalized.limit,
      });
      final webData = webResult.data ?? const <String, dynamic>{};
      provider = (webData['provider'] as String?)?.trim() ?? '';
      final webReferences =
          (webData['references'] as List?)
              ?.whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      _mergeMapList(
        target: references,
        incoming: webReferences,
        keyOf: _referenceKey,
      );
      final webHits = webReferences
          .map(_webReferenceToHit)
          .map((item) => item.toMap())
          .toList(growable: false);
      if (webHits.isNotEmpty) {
        _mergeSectionMaps(
          sections: sections,
          incoming: <Map<String, dynamic>>[
            SearchSection(
              id: 'web',
              title: '网页',
              objectTypes: const <SearchObjectType>[
                SearchObjectType.webDocument,
              ],
              hits: webReferences
                  .map(_webReferenceToHit)
                  .toList(growable: false),
              resolvedFrom: SearchResolvedFrom.remote,
            ).toMap(),
          ],
        );
        _mergeMapList(target: hits, incoming: webHits, keyOf: _hitKey);
      }
      if (!webResult.success) {
        degraded = true;
        failureCode = webResult.errorCode;
        degradeSignals.add(<String, dynamic>{
          'code': 'web_search_failed',
          'message': webResult.message,
          'objectType': SearchObjectType.webDocument.wireValue,
        });
      } else if (webResult.degraded) {
        degraded = true;
      }
    }

    final success = hits.isNotEmpty || references.isNotEmpty;
    final coveredDimensions = success
        ? _taskDimensions(queryTask)
        : const <String>[];
    final summary = _buildSingleQuerySummary(
      hitCount: hits.length,
      referenceCount: references.length,
      webSummary:
          (((webResult?.data ?? const <String, dynamic>{})['summary'])
                  as String?)
              ?.trim() ??
          '',
      includesWeb: includesWeb,
      includesInternal: internalObjectTypes.isNotEmpty,
    );
    final qualityScore = _qualityScore(
      hitCount: hits.length,
      referenceCount: references.length,
      queryCount: 1,
      includesWeb: includesWeb,
      includesInternal: internalObjectTypes.isNotEmpty,
    );
    final queryLabels = _taskLabels(queryTask);
    return AssistantToolResult(
      success: success,
      message: success ? '已完成统一检索' : '未找到相关结果',
      degraded: degraded,
      data: <String, dynamic>{
        SearchToolFieldNames.query: normalized.query,
        SearchToolFieldNames.mode: normalized.mode.wireValue,
        SearchToolFieldNames.objectTypes: effectiveObjectTypes
            .map((item) => item.wireValue)
            .toList(growable: false),
        'sections': sections,
        'hits': hits,
        'references': references,
        'degradeSignals': degradeSignals,
        'summary': summary,
        'qualityScore': qualityScore,
        'queryCount': 1,
        'queryLabels': queryLabels,
        'coveredDimensions': coveredDimensions,
        'missingDimensions': const <String>[],
        'referenceCount': references.length,
        'totalReferences': references.length,
        'queriesUsed': <String>[normalized.query],
        if (provider.isNotEmpty) 'provider': provider,
        if (queryTask != null)
          SearchToolFieldNames.queryTasks: <Map<String, dynamic>>[queryTask],
        if (internalResponse != null) 'internal': internalResponse.toMap(),
      },
      errorCode: success ? AssistantErrorCode.none : failureCode,
    );
  }

  Future<AssistantToolResult> _executeMultiQuery(
    Map<String, dynamic> arguments,
    List<Map<String, dynamic>> queryTasks,
  ) async {
    final tasks = _normalizeQueryTasks(queryTasks);
    final taskResults = await Future.wait<AssistantToolResult>(
      tasks.map((task) {
        final singleArgs =
            <String, dynamic>{
                ...arguments,
                SearchToolFieldNames.query:
                    (task['query'] as String?)?.trim() ?? '',
              }
              ..remove(SearchToolFieldNames.queryTasks)
              ..remove(SearchToolFieldNames.queryVariants);
        return _executeSingleQuery(singleArgs, queryTask: task);
      }),
      eagerError: false,
    );
    final sections = <Map<String, dynamic>>[];
    final hits = <Map<String, dynamic>>[];
    final references = <Map<String, dynamic>>[];
    final degradeSignals = <Map<String, dynamic>>[];
    final coveredDimensions = <String>{};
    final queryLabels = <String>[];
    final queriesUsed = <String>[];
    var degraded = false;
    var provider = '';
    var anySuccess = false;
    AssistantErrorCode failureCode = AssistantErrorCode.executionFailed;

    for (var i = 0; i < taskResults.length; i += 1) {
      final result = taskResults[i];
      final data = result.data ?? const <String, dynamic>{};
      final task = i < tasks.length ? tasks[i] : const <String, dynamic>{};
      _mergeSectionMaps(
        sections: sections,
        incoming:
            (data['sections'] as List?)?.whereType<Map>().map(
              (item) => item.cast<String, dynamic>(),
            ) ??
            const <Map<String, dynamic>>[],
      );
      _mergeMapList(
        target: hits,
        incoming:
            (data['hits'] as List?)?.whereType<Map>().map(
              (item) => item.cast<String, dynamic>(),
            ) ??
            const <Map<String, dynamic>>[],
        keyOf: _hitKey,
      );
      _mergeMapList(
        target: references,
        incoming:
            (data['references'] as List?)?.whereType<Map>().map(
              (item) => item.cast<String, dynamic>(),
            ) ??
            const <Map<String, dynamic>>[],
        keyOf: _referenceKey,
      );
      _mergeMapList(
        target: degradeSignals,
        incoming:
            (data['degradeSignals'] as List?)?.whereType<Map>().map(
              (item) => item.cast<String, dynamic>(),
            ) ??
            const <Map<String, dynamic>>[],
        keyOf: _degradeKey,
      );
      degraded = degraded || result.degraded;
      if (provider.isEmpty) {
        provider = (data['provider'] as String?)?.trim() ?? '';
      }
      final referencesCount =
          (data['references'] as List?)?.whereType<Map>().length ?? 0;
      final hitCount = (data['hits'] as List?)?.whereType<Map>().length ?? 0;
      if (result.success || referencesCount > 0 || hitCount > 0) {
        anySuccess = true;
        coveredDimensions.addAll(_taskDimensions(task));
      } else {
        failureCode = result.errorCode;
      }
      queryLabels.addAll(_taskLabels(task));
      final query = (task['query'] as String?)?.trim() ?? '';
      if (query.isNotEmpty) {
        queriesUsed.add(query);
      }
    }

    final missingDimensions = tasks
        .expand(_taskDimensions)
        .where(
          (item) => item.trim().isNotEmpty && !coveredDimensions.contains(item),
        )
        .toSet()
        .toList(growable: false);
    final normalizedRequest = _requestFromArguments(arguments).normalized();
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
    return AssistantToolResult(
      success: anySuccess,
      message: anySuccess ? '已完成多轮统一检索' : '未找到相关结果',
      degraded: degraded,
      data: <String, dynamic>{
        SearchToolFieldNames.query: queriesUsed.isNotEmpty
            ? queriesUsed.first
            : '',
        SearchToolFieldNames.mode: normalizedRequest.mode.wireValue,
        SearchToolFieldNames.objectTypes: effectiveObjectTypes
            .map((item) => item.wireValue)
            .toList(growable: false),
        'sections': sections,
        'hits': hits,
        'references': references,
        'degradeSignals': degradeSignals,
        'summary': summary,
        'qualityScore': _qualityScore(
          hitCount: hits.length,
          referenceCount: references.length,
          queryCount: tasks.length,
          includesWeb: references.isNotEmpty,
          includesInternal: hits.any(
            (item) =>
                (item['objectType']?.toString() ?? '') !=
                SearchObjectType.webDocument.wireValue,
          ),
        ),
        'queryCount': tasks.length,
        'queryLabels': queryLabels,
        'coveredDimensions': coveredDimensions.toList(growable: false),
        'missingDimensions': missingDimensions,
        SearchToolFieldNames.queryTasks: tasks,
        'referenceCount': references.length,
        'totalReferences': references.length,
        'queriesUsed': queriesUsed,
        if (provider.isNotEmpty) 'provider': provider,
      },
      errorCode: anySuccess ? AssistantErrorCode.none : failureCode,
    );
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

  List<Map<String, dynamic>> _normalizeQueryTasks(Object? raw) {
    if (raw is! List) {
      return const <Map<String, dynamic>>[];
    }
    return raw
        .whereType<Map>()
        .map((item) => item.cast<String, dynamic>())
        .where(
          (item) => ((item['query'] as String?)?.trim().isNotEmpty ?? false),
        )
        .toList(growable: false);
  }

  List<Map<String, dynamic>> _queryTasksFromSeeds(
    String query,
    List<String> queryVariants,
  ) {
    final tasks = <Map<String, dynamic>>[];
    final seen = <String>{};
    final seeds = <String>[query.trim(), ...queryVariants];
    for (var i = 0; i < seeds.length; i += 1) {
      final item = seeds[i].trim();
      if (item.isEmpty || !seen.add(item)) {
        continue;
      }
      tasks.add(<String, dynamic>{
        'id': 'query_${i + 1}',
        'label': '检索${i + 1}',
        'dimension': 'query_${i + 1}',
        'query': item,
      });
    }
    return tasks;
  }

  void _mergeSectionMaps({
    required List<Map<String, dynamic>> sections,
    required Iterable<Map<String, dynamic>> incoming,
  }) {
    final index = <String, int>{
      for (var i = 0; i < sections.length; i += 1)
        (sections[i]['id'] as String?)?.trim() ?? '': i,
    };
    for (final raw in incoming) {
      final id = (raw['id'] as String?)?.trim() ?? '';
      if (id.isEmpty) {
        continue;
      }
      final rawHits =
          (raw['hits'] as List?)
              ?.whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      final rawObjectTypes =
          (raw['objectTypes'] as List?)?.whereType<String>().toSet() ??
          const <String>{};
      if (!index.containsKey(id)) {
        sections.add(<String, dynamic>{
          ...raw,
          'objectTypes': rawObjectTypes.toList(growable: false),
          'hits': rawHits,
        });
        index[id] = sections.length - 1;
        continue;
      }
      final existing = sections[index[id]!]
        ..putIfAbsent('hits', () => <dynamic>[]);
      final mergedHits =
          (existing['hits'] as List?)
              ?.whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      final mergedObjectTypes =
          (existing['objectTypes'] as List?)?.whereType<String>().toSet() ??
          <String>{};
      mergedObjectTypes.addAll(rawObjectTypes);
      final dedupedHits = <Map<String, dynamic>>[];
      _mergeMapList(
        target: dedupedHits,
        incoming: <Map<String, dynamic>>[...mergedHits, ...rawHits],
        keyOf: _hitKey,
      );
      sections[index[id]!] = <String, dynamic>{
        ...existing,
        'objectTypes': mergedObjectTypes.toList(growable: false),
        'hits': dedupedHits,
      };
    }
  }

  void _mergeMapList({
    required List<Map<String, dynamic>> target,
    required Iterable<Map<String, dynamic>> incoming,
    required String Function(Map<String, dynamic>) keyOf,
  }) {
    final seen = <String>{for (final item in target) keyOf(item)};
    for (final item in incoming) {
      final key = keyOf(item);
      if (key.isEmpty || !seen.add(key)) {
        continue;
      }
      target.add(item);
    }
  }

  String _hitKey(Map<String, dynamic> hit) {
    return '${hit['objectType']}:${hit['objectId']}';
  }

  String _referenceKey(Map<String, dynamic> reference) {
    final url = (reference['url'] ?? '').toString().trim();
    if (url.isNotEmpty) {
      return url;
    }
    return '${reference['title']}:${reference['source']}';
  }

  String _degradeKey(Map<String, dynamic> signal) {
    return '${signal['code']}:${signal['objectType']}';
  }

  List<String> _taskDimensions(Map<String, dynamic>? queryTask) {
    if (queryTask == null) {
      return const <String>[];
    }
    final dimension = (queryTask['dimension'] as String?)?.trim() ?? '';
    final label = (queryTask['label'] as String?)?.trim() ?? '';
    return <String>[
      if (dimension.isNotEmpty) dimension else if (label.isNotEmpty) label,
    ];
  }

  List<String> _taskLabels(Map<String, dynamic>? queryTask) {
    if (queryTask == null) {
      return const <String>[];
    }
    final label = (queryTask['label'] as String?)?.trim() ?? '';
    if (label.isEmpty) {
      return const <String>[];
    }
    return <String>[label];
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

  SearchHit _webReferenceToHit(Map<String, dynamic> reference) {
    final url = (reference['url'] ?? '').toString().trim();
    final title = (reference['title'] ?? url).toString().trim();
    final snippet = (reference['snippet'] ?? reference['summary'])?.toString();
    return SearchHit(
      objectType: SearchObjectType.webDocument,
      objectId: url.isNotEmpty ? url : title,
      title: title.isNotEmpty ? title : '网页结果',
      subtitle: (reference['source'] ?? reference['sourceDomain'])?.toString(),
      snippet: snippet,
      resolvedFrom: SearchResolvedFrom.remote,
      matchedField: 'query',
      payload: reference,
    );
  }
}
