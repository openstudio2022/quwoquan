// ASSISTANT_WEAK_TYPE: VENDOR_JSON — 搜索供应商 HTTP/JSON，边界归一化为 NormalizedWebReference 等。

import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/assistant/debug/console_pretty_log_formatter.dart';
import 'package:quwoquan_app/assistant/reasoning/geo/geo_scope_support.dart';
import 'package:quwoquan_app/assistant/reasoning/temporal/relative_time_resolver.dart';
import 'package:quwoquan_app/assistant/retrieval/domain/retrieval_broker.dart';
import 'package:path_provider/path_provider.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_log_models.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_log_service.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_run_interaction_collector.dart';
import 'package:quwoquan_app/assistant/tool/runtime/safe_reference_normalizer.dart';
import 'package:quwoquan_app/assistant/tool/runtime/search_cache.dart';
import 'package:quwoquan_app/assistant/tool/impl/web/normalized_web_reference.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';
import 'package:quwoquan_app/core/links/app_public_content_links.dart';

const RelativeTimeResolver _relativeTimeResolver = RelativeTimeResolver();

enum AssistantSearchProvider {
  brave,
  perplexity,
  openclawProxy,
  serpapi,
  duckduckgo,
}

class WebSearchTool implements AssistantTool {
  WebSearchTool({
    String? braveApiKey,
    String? perplexityApiKey,
    String? serpApiKey,
    String? openclawBaseUrl,
    String? openclawToken,
    AssistantSearchProvider? defaultProvider,
    SearchResultCache? searchCache,
    RetrievalBroker? broker,
    http.Client? httpClient,
    bool enableInteractionLogging = true,
    bool resolveRuntimeConfigFromDisk = true,
    Future<String> Function(String path)? textLoader,
  }) : _braveApiKey =
           braveApiKey ??
           const String.fromEnvironment('PERSONAL_ASSISTANT_BRAVE_API_KEY'),
       _perplexityApiKey =
           perplexityApiKey ??
           const String.fromEnvironment(
             'PERSONAL_ASSISTANT_PERPLEXITY_API_KEY',
           ),
       _serpApiKey =
           serpApiKey ??
           const String.fromEnvironment('PERSONAL_ASSISTANT_SERPAPI_API_KEY'),
       _openclawBaseUrl =
           openclawBaseUrl ??
           const String.fromEnvironment('PERSONAL_ASSISTANT_OPENCLAW_BASE_URL'),
       _openclawToken =
           openclawToken ??
           const String.fromEnvironment('PERSONAL_ASSISTANT_OPENCLAW_TOKEN'),
       _defaultProvider = defaultProvider ?? AssistantSearchProvider.serpapi,
       _searchCache = searchCache ?? SearchResultCache(),
       _broker = broker,
       _httpClient = httpClient ?? http.Client(),
       _enableInteractionLogging = enableInteractionLogging,
       _resolveRuntimeConfigFromDisk = resolveRuntimeConfigFromDisk,
       _textLoader = textLoader;

  final String _braveApiKey;
  final String _perplexityApiKey;
  final String _serpApiKey;
  final String _openclawBaseUrl;
  final String _openclawToken;
  final AssistantSearchProvider _defaultProvider;
  final SearchResultCache _searchCache;
  final RetrievalBroker? _broker;
  final http.Client _httpClient;
  final bool _enableInteractionLogging;
  final bool _resolveRuntimeConfigFromDisk;
  final Future<String> Function(String path)? _textLoader;
  static const Duration _networkTimeout = Duration(seconds: 8);

  /// Access to the search cache for external reset (e.g. new session).
  SearchResultCache get searchCache => _searchCache;

  @override
  String get name => 'web_search';

  @override
  String get description => 'Search web content for latest information.';

  @override
  Future<AssistantToolResult> execute(AssistantToolArguments arguments) async {
    final rawArguments = arguments.toDynamicJson();
    final broker = _broker;
    if (broker != null) {
      final request = RetrievalSearchRequest.fromToolArguments(rawArguments);
      final result = await broker.search(request);
      return _sanitizeBrokerSearchResult(request: request, result: result);
    }
    final args = arguments;
    final rawQuery = args.stringField('query') ?? '';
    final searchPlans = _normalizeSearchPlans(
      rawArguments['taskGraphSearchPlan'] ??
          rawArguments['searchPlans'] ??
          rawArguments['queries'] ??
          rawArguments['queryVariants'],
    );
    final variants =
        (rawArguments['queryVariants'] as List?)
            ?.whereType<String>()
            .map((v) => v.trim())
            .where((v) => v.isNotEmpty)
            .toList(growable: false) ??
        const <String>[];
    if (searchPlans.length >= 2) {
      return _executeMultiQuery(rawArguments, searchPlans);
    }
    if (searchPlans.isEmpty && variants.isNotEmpty) {
      final variantPlans = _searchPlansFromSeeds(rawQuery, variants);
      if (variantPlans.length >= 2) {
        return _executeMultiQuery(rawArguments, variantPlans);
      }
    }
    final singlePlanQuery = searchPlans.length == 1
        ? ((searchPlans.first['query'] as String?)?.trim() ?? '')
        : '';
    final queryNorm = rawArguments['queryNormalization'];
    final normalizedQuery = singlePlanQuery.isNotEmpty
        ? singlePlanQuery
        : queryNorm is Map
        ? ((queryNorm['normalizedQuery'] as String?)?.trim() ?? rawQuery)
        : rawQuery;
    final query = normalizedQuery.isNotEmpty ? normalizedQuery : rawQuery;
    final searchPlan = _resolveSingleSearchPlan(
      arguments: arguments,
      normalizedQuery: query,
      normalizedPlans: searchPlans,
    );
    final effectiveArguments = _withResolvedGeoArguments(
      arguments: _withResolvedTemporalArguments(
        arguments: rawArguments,
        searchPlan: searchPlan,
        query: query,
      ),
      searchPlan: searchPlan,
    );
    final calendarAwareQuery =
        (effectiveArguments['query'] as String?)?.trim().isNotEmpty == true
        ? (effectiveArguments['query'] as String).trim()
        : _rewriteQueryWithInlineCalendarPoint(
            query,
            referenceNowIso: _stringValue(
              effectiveArguments['referenceNowIso'],
            ),
            timezone: _stringValue(effectiveArguments['timezone']),
          );
    final domainId =
        ((effectiveArguments['domainId'] as String?)?.trim().isNotEmpty == true
            ? (effectiveArguments['domainId'] as String).trim()
            : (effectiveArguments['__domainId'] as String?)?.trim()) ??
        '';
    final sessionId =
        (effectiveArguments['__sessionId'] as String?)?.trim() ?? '';
    final runId = (effectiveArguments['__runId'] as String?)?.trim() ?? '';
    final traceId = (effectiveArguments['__traceId'] as String?)?.trim() ?? '';
    final count = (effectiveArguments['count'] as int?) ?? 5;
    final cacheKey = _buildSearchCacheKey(
      query: calendarAwareQuery.isNotEmpty ? calendarAwareQuery : query,
      arguments: effectiveArguments,
      domainId: domainId,
      count: count,
    );
    if (query.isEmpty) {
      return AssistantToolResult(
        success: false,
        message: 'Missing query',
        errorCode: AssistantErrorCode.invalidArguments,
        runtimeFailure: assistantToolRuntimeFailure(
          errorCode: AssistantErrorCode.invalidArguments,
          message: 'Missing query',
          functionModule: name,
          stage: 'argument_validation',
        ),
      );
    }

    // Check search cache before hitting the network
    final cached = _searchCache.get(cacheKey);
    if (cached != null) {
      final cachedData = <String, dynamic>{...cached};
      final cachedTimeConstraint = _timeConstraintFromJson(
        (cachedData['timeConstraint'] as Map?)?.cast<String, dynamic>() ??
            const <String, dynamic>{},
      );
      final cachedRefs =
          (cachedData['references'] as List?)
              ?.whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      if (cachedRefs.isNotEmpty && cachedTimeConstraint != null) {
        cachedData['references'] = _decorateReferences(
          references: cachedRefs,
          query: query,
          authorityDomains:
              (cachedData['authorityDomains'] as List?)
                  ?.whereType<String>()
                  .toList(growable: false) ??
              const <String>[],
          timeConstraint: cachedTimeConstraint,
          searchPlan: searchPlan,
          retrievedAt: _stringValue(cachedData['retrievedAt']).isNotEmpty
              ? _stringValue(cachedData['retrievedAt'])
              : DateTime.now().toIso8601String(),
        );
        cachedData['timeConstraint'] = cachedTimeConstraint.toJson();
      }
      return AssistantToolResult(
        success: true,
        message: cachedData['message'] as String? ?? '检索结果（缓存）',
        data: AssistantToolResultData(<String, Object?>{
          ...cachedData,
          'cacheHit': true,
        }),
      );
    }

    final runtimeConfig = await _resolveRuntimeConfig();
    final timeContract = await _loadRetrievalTimeContract();
    final domainPolicy = await _loadDomainRetrievalPolicy(domainId);
    final geoScopedSearchPlan = _withResolvedGeoSearchPlan(
      searchPlan: searchPlan,
      arguments: effectiveArguments,
    );
    final effectiveSearchPlan = _withDomainPolicySearchPlanHints(
      searchPlan: geoScopedSearchPlan,
      domainPolicy: domainPolicy,
    );
    final timeConstraint = _resolveTimeConstraint(
      query: calendarAwareQuery,
      arguments: effectiveArguments,
      domainPolicy: domainPolicy,
      timeContract: timeContract,
    );
    final temporalGuard = _evaluateTemporalGuard(
      query: calendarAwareQuery,
      constraint: timeConstraint,
    );
    final baseScopedQuery = _withTimeConstraintQuery(
      query: temporalGuard.searchQuery,
      constraint: timeConstraint,
    );
    final scopedQuery = _withDomainContextQuery(
      query: baseScopedQuery,
      arguments: effectiveArguments,
      domainPolicy: domainPolicy,
    );
    final authorityDomains = _resolveAuthorityDomains(
      arguments: effectiveArguments,
      domainPolicy: domainPolicy,
    );
    final provider = _resolveProvider(
      raw: effectiveArguments['provider'] as String?,
      config: runtimeConfig,
    );
    if (provider == null) {
      await _logSearchInteraction(
        sessionId: sessionId,
        runId: runId,
        traceId: traceId,
        payload: <String, dynamic>{
          'kind': 'search',
          'provider': 'none',
          'request': <String, dynamic>{
            'query': scopedQuery,
            'originalQuery': query,
            'count': count,
            'providerHint': (effectiveArguments['provider'] as String?) ?? '',
            'timeConstraint': timeConstraint.toJson(),
            'temporalGuard': temporalGuard.toJson(),
            'authorityDomains': authorityDomains,
            if (domainId.isNotEmpty) 'domainId': domainId,
          },
          'error': '未发现可用搜索 provider',
        },
        hasError: true,
      );
      return AssistantToolResult(
        success: false,
        message:
            'Web search error: 未发现可用搜索 provider。会优先使用显式配置 provider，其次 SerpApi / Brave / OpenClaw / Perplexity，'
            '最后才回退到 DuckDuckGo 公共检索。请检查对应 key 或代理配置。',
        data: AssistantToolResultData(<String, Object?>{
          'diagnostics': runtimeConfig.toDiagnostics(),
        }),
        errorCode: AssistantErrorCode.invalidArguments,
        degraded: true,
        runtimeFailure: assistantToolRuntimeFailure(
          errorCode: AssistantErrorCode.invalidArguments,
          message: 'Web search provider is not configured',
          functionModule: name,
          stage: 'provider_resolution',
        ),
      );
    }
    try {
      final decoded = await _runProviderSearch(
        provider: provider,
        query: scopedQuery,
        count: count,
        config: runtimeConfig,
      );
      final summary = _summarizeProviderResult(
        provider: provider,
        decoded: decoded,
      );
      final references = _extractReferences(
        provider: provider,
        decoded: decoded,
      );
      final enrichedReferences = _applyTaskFilters(
        _decorateReferences(
          references: references,
          query: temporalGuard.searchQuery,
          authorityDomains: authorityDomains,
          timeConstraint: timeConstraint,
          searchPlan: effectiveSearchPlan,
          retrievedAt: DateTime.now().toIso8601String(),
        ),
        searchPlan: effectiveSearchPlan,
      );
      final evidenceStats = _buildEvidenceStats(
        references: enrichedReferences,
        authorityDomains: authorityDomains,
        timeConstraint: timeConstraint,
        temporalGuard: temporalGuard,
      );
      await _logSearchInteraction(
        sessionId: sessionId,
        runId: runId,
        traceId: traceId,
        payload: <String, dynamic>{
          'kind': 'search',
          'provider': provider.name,
          'request': <String, dynamic>{
            'query': scopedQuery,
            'originalQuery': query,
            'count': count,
            'providerHint': (effectiveArguments['provider'] as String?) ?? '',
            'timeConstraint': timeConstraint.toJson(),
            'temporalGuard': temporalGuard.toJson(),
            'authorityDomains': authorityDomains,
            if (domainId.isNotEmpty) 'domainId': domainId,
          },
          'response': <String, dynamic>{'summary': summary, 'raw': decoded},
          'diagnostics': runtimeConfig.toDiagnostics(
            selectedProvider: provider.name,
          ),
        },
      );
      final message = summary.isEmpty ? '检索成功，但未获得可用摘要。' : '检索结果：$summary';
      final primaryIsInsufficient =
          evidenceStats['retrievalInsufficient'] == true;
      if (primaryIsInsufficient) {
        return AssistantToolResult(
          success: true,
          message: _insufficientRetrievalMessage(
            temporalGuard: temporalGuard,
            evidenceStats: evidenceStats,
            timeConstraint: timeConstraint,
          ),
          data: AssistantToolResultData(<String, Object?>{
            'provider': provider.name,
            'summary': summary,
            'references': enrichedReferences,
            'timeConstraint': timeConstraint.toJson(),
            'temporalGuard': temporalGuard.toJson(),
            'authorityDomains': authorityDomains,
            'retrievalInsufficient': true,
            if (domainId.isNotEmpty) 'domainId': domainId,
            if (_stringValue(effectiveSearchPlan['id']).isNotEmpty)
              'searchPlanId': _stringValue(effectiveSearchPlan['id']),
            if (_stringValue(effectiveSearchPlan['dimension']).isNotEmpty)
              'dimension': _stringValue(effectiveSearchPlan['dimension']),
            ...evidenceStats,
            'raw': decoded,
            'diagnostics': runtimeConfig.toDiagnostics(
              selectedProvider: provider.name,
            ),
          }),
        );
      }
      final resultData = <String, dynamic>{
        'provider': provider.name,
        'summary': summary,
        'references': enrichedReferences,
        'timeConstraint': timeConstraint.toJson(),
        'temporalGuard': temporalGuard.toJson(),
        'authorityDomains': authorityDomains,
        if (domainId.isNotEmpty) 'domainId': domainId,
        if (_stringValue(effectiveSearchPlan['id']).isNotEmpty)
          'searchPlanId': _stringValue(effectiveSearchPlan['id']),
        if (_stringValue(effectiveSearchPlan['dimension']).isNotEmpty)
          'dimension': _stringValue(effectiveSearchPlan['dimension']),
        ...evidenceStats,
        'raw': decoded,
        'diagnostics': runtimeConfig.toDiagnostics(
          selectedProvider: provider.name,
        ),
        'message': message,
      };
      _searchCache.put(cacheKey, resultData);
      return AssistantToolResult(
        success: true,
        message: message,
        data: AssistantToolResultData.fromJson(resultData),
      );
    } catch (error) {
      final classifiedError = _classifySearchError(error);
      final fallback = await _tryFallbackSearch(
        primaryProvider: provider,
        query: scopedQuery,
        count: count,
        config: runtimeConfig,
      );
      if (fallback != null) {
        final fallbackProvider =
            _parseProvider(fallback.providerLabel) ??
            AssistantSearchProvider.duckduckgo;
        final fallbackReferences = _extractReferences(
          provider: fallbackProvider,
          decoded: fallback.raw,
        );
        final enrichedFallbackReferences = _applyTaskFilters(
          _decorateReferences(
            references: fallbackReferences,
            query: temporalGuard.searchQuery,
            authorityDomains: authorityDomains,
            timeConstraint: timeConstraint,
            searchPlan: effectiveSearchPlan,
            retrievedAt: DateTime.now().toIso8601String(),
          ),
          searchPlan: effectiveSearchPlan,
        );
        final evidenceStats = _buildEvidenceStats(
          references: enrichedFallbackReferences,
          authorityDomains: authorityDomains,
          timeConstraint: timeConstraint,
          temporalGuard: temporalGuard,
        );
        await _logSearchInteraction(
          sessionId: sessionId,
          runId: runId,
          traceId: traceId,
          payload: <String, dynamic>{
            'kind': 'search',
            'provider': fallback.providerLabel,
            'request': <String, dynamic>{
              'query': scopedQuery,
              'originalQuery': query,
              'count': count,
              'fallbackFrom': provider.name,
              'timeConstraint': timeConstraint.toJson(),
              'temporalGuard': temporalGuard.toJson(),
              'authorityDomains': authorityDomains,
              if (domainId.isNotEmpty) 'domainId': domainId,
            },
            'response': <String, dynamic>{
              'summary': fallback.summary,
              'raw': fallback.raw,
            },
            'diagnostics': runtimeConfig.toDiagnostics(
              selectedProvider: fallback.providerLabel,
            ),
          },
        );
        final fallbackMessage = fallback.summary.isEmpty
            ? '检索成功，但未获得可用摘要。'
            : '检索结果：${fallback.summary}';
        final fallbackIsInsufficient =
            evidenceStats['retrievalInsufficient'] == true;
        if (fallbackIsInsufficient) {
          return AssistantToolResult(
            success: true,
            message: _insufficientRetrievalMessage(
              temporalGuard: temporalGuard,
              evidenceStats: evidenceStats,
              timeConstraint: timeConstraint,
            ),
            data: AssistantToolResultData(<String, Object?>{
              'provider': fallback.providerLabel,
              'summary': fallback.summary,
              'references': enrichedFallbackReferences,
              'timeConstraint': timeConstraint.toJson(),
              'temporalGuard': temporalGuard.toJson(),
              'authorityDomains': authorityDomains,
              'retrievalInsufficient': true,
              if (domainId.isNotEmpty) 'domainId': domainId,
              if (_stringValue(effectiveSearchPlan['id']).isNotEmpty)
                'searchPlanId': _stringValue(effectiveSearchPlan['id']),
              if (_stringValue(effectiveSearchPlan['dimension']).isNotEmpty)
                'dimension': _stringValue(effectiveSearchPlan['dimension']),
              ...evidenceStats,
              'raw': fallback.raw,
              'fallbackFrom': provider.name,
              'primaryError': error.toString(),
              'diagnostics': runtimeConfig.toDiagnostics(
                selectedProvider: fallback.providerLabel,
              ),
            }),
          );
        }
        return AssistantToolResult(
          success: true,
          message: fallbackMessage,
          data: AssistantToolResultData(<String, Object?>{
            'provider': fallback.providerLabel,
            'summary': fallback.summary,
            'references': enrichedFallbackReferences,
            'timeConstraint': timeConstraint.toJson(),
            'temporalGuard': temporalGuard.toJson(),
            'authorityDomains': authorityDomains,
            if (domainId.isNotEmpty) 'domainId': domainId,
            if (_stringValue(effectiveSearchPlan['id']).isNotEmpty)
              'searchPlanId': _stringValue(effectiveSearchPlan['id']),
            if (_stringValue(effectiveSearchPlan['dimension']).isNotEmpty)
              'dimension': _stringValue(effectiveSearchPlan['dimension']),
            ...evidenceStats,
            'raw': fallback.raw,
            'fallbackFrom': provider.name,
            'primaryError': error.toString(),
            'diagnostics': runtimeConfig.toDiagnostics(
              selectedProvider: fallback.providerLabel,
            ),
          }),
        );
      }
      await _logSearchInteraction(
        sessionId: sessionId,
        runId: runId,
        traceId: traceId,
        payload: <String, dynamic>{
          'kind': 'search',
          'provider': provider.name,
          'request': <String, dynamic>{
            'query': scopedQuery,
            'originalQuery': query,
            'count': count,
            'timeConstraint': timeConstraint.toJson(),
            'temporalGuard': temporalGuard.toJson(),
            'authorityDomains': authorityDomains,
            if (domainId.isNotEmpty) 'domainId': domainId,
          },
          'error': error.toString(),
          'diagnostics': runtimeConfig.toDiagnostics(
            selectedProvider: provider.name,
          ),
        },
        hasError: true,
      );
      return AssistantToolResult(
        success: false,
        message: classifiedError.message,
        data: AssistantToolResultData(<String, Object?>{
          'provider': provider.name,
          'rawError': error.toString(),
          'diagnostics': runtimeConfig.toDiagnostics(
            selectedProvider: provider.name,
          ),
        }),
        errorCode: classifiedError.errorCode,
        degraded: true,
        runtimeFailure: assistantToolRuntimeFailure(
          errorCode: classifiedError.errorCode,
          message: classifiedError.message,
          functionModule: name,
          stage: 'provider_request',
        ),
      );
    }
  }

  Future<AssistantToolResult> _sanitizeBrokerSearchResult({
    required RetrievalSearchRequest request,
    required RetrievalSearchResult result,
  }) async {
    final toolResult = result.toToolResult();
    final rawData = toolResult.data;
    if (rawData == null || rawData.isEmpty) return toolResult;
    final sanitizedData = Map<String, dynamic>.from(rawData);
    final normalizedPlans = request.queryPlans
        .map((item) => item.toJson().cast<String, dynamic>())
        .toList(growable: false);
    final singlePlanQuery = normalizedPlans.length == 1
        ? ((normalizedPlans.first['query'] as String?)?.trim() ?? '')
        : '';
    final queryNorm = request.arguments['queryNormalization'];
    final normalizedQuery = singlePlanQuery.isNotEmpty
        ? singlePlanQuery
        : queryNorm is Map
        ? ((queryNorm['normalizedQuery'] as String?)?.trim() ?? request.query)
        : request.query;
    final query = normalizedQuery.isNotEmpty ? normalizedQuery : request.query;
    final domainPolicy = await _loadDomainRetrievalPolicy(request.domainId);
    final timeContract = await _loadRetrievalTimeContract();
    final searchPlan = _resolveSingleSearchPlan(
      arguments: request.arguments,
      normalizedQuery: query,
      normalizedPlans: normalizedPlans,
    );
    final effectiveArguments = _withResolvedGeoArguments(
      arguments: _withResolvedTemporalArguments(
        arguments: request.arguments,
        searchPlan: searchPlan,
        query: query,
      ),
      searchPlan: searchPlan,
    );
    final effectiveSearchPlan = _withDomainPolicySearchPlanHints(
      searchPlan: _withResolvedGeoSearchPlan(
        searchPlan: searchPlan,
        arguments: effectiveArguments,
      ),
      domainPolicy: domainPolicy,
    );
    final effectiveQuery =
        (effectiveArguments['query'] as String?)?.trim().isNotEmpty == true
        ? (effectiveArguments['query'] as String).trim()
        : query;
    final timeConstraint = _resolveTimeConstraint(
      query: effectiveQuery,
      arguments: effectiveArguments,
      domainPolicy: domainPolicy,
      timeContract: timeContract,
    );
    final temporalGuard = _evaluateTemporalGuard(
      query: effectiveQuery,
      constraint: timeConstraint,
    );
    final authorityDomains = _resolveAuthorityDomains(
      arguments: effectiveArguments,
      domainPolicy: domainPolicy,
    );
    final retrievedAt = DateTime.now().toIso8601String();
    final dataView = BrokerWebSearchResultDataView(sanitizedData);
    final referenceCandidates = _referenceCandidatesFromResultData(
      data: dataView,
      searchPlan: searchPlan,
      retrievedAt: retrievedAt,
    );
    if (referenceCandidates.isNotEmpty) {
      final references = _decorateReferences(
        references: referenceCandidates,
        query: temporalGuard.searchQuery,
        authorityDomains: authorityDomains,
        timeConstraint: timeConstraint,
        searchPlan: effectiveSearchPlan,
        retrievedAt: retrievedAt,
      );
      final filteredReferences = _applyTaskFilters(
        references,
        searchPlan: effectiveSearchPlan,
      );
      if (filteredReferences.isNotEmpty) {
        sanitizedData['references'] = filteredReferences;
        sanitizedData['timeConstraint'] = timeConstraint.toJson();
        sanitizedData['temporalGuard'] = temporalGuard.toJson();
        sanitizedData['authorityDomains'] = authorityDomains;
        if (_stringValue(effectiveSearchPlan['id']).isNotEmpty) {
          sanitizedData['searchPlanId'] = _stringValue(
            effectiveSearchPlan['id'],
          );
        }
        if (_stringValue(effectiveSearchPlan['dimension']).isNotEmpty) {
          sanitizedData['dimension'] = _stringValue(
            effectiveSearchPlan['dimension'],
          );
        }
        sanitizedData.addAll(
          _buildEvidenceStats(
            references: filteredReferences,
            authorityDomains: authorityDomains,
            timeConstraint: timeConstraint,
            temporalGuard: temporalGuard,
          ),
        );
      }
    }
    return AssistantToolResult(
      success: toolResult.success,
      message: toolResult.message,
      data: AssistantToolResultData.fromJson(sanitizedData),
      errorCode: toolResult.errorCode,
      degraded: toolResult.degraded,
      runtimeFailure: toolResult.success
          ? null
          : assistantToolRuntimeFailure(
              errorCode: toolResult.errorCode,
              message: toolResult.message,
              functionModule: name,
              stage: 'broker_search',
            ),
    );
  }

  List<Map<String, dynamic>> _referenceCandidatesFromResultData({
    required BrokerWebSearchResultDataView data,
    required Map<String, dynamic> searchPlan,
    required String retrievedAt,
  }) {
    final refs = data.embeddedReferences;
    if (refs.isNotEmpty) return refs;
    final url = data.valueOf('url');
    if (url.isEmpty) return const <Map<String, dynamic>>[];
    final snippet = data.summaryOrSnippet;
    final title = data.valueOf('title');
    final source = data.valueOf('source');
    final sourceHost = data.valueOf('sourceHost');
    return <Map<String, dynamic>>[
      <String, dynamic>{
        'title': title.isNotEmpty ? title : url,
        'url': url,
        'source': source.isNotEmpty ? source : sourceHost,
        'snippet': snippet,
        'sourceTier': data.valueOf('sourceTier'),
        'publishedAt': data.valueOf('publishedAt'),
        'observedAt': data.valueOf('observedAt'),
        'searchPlanId': data.valueOf('searchPlanId').isNotEmpty
            ? data.valueOf('searchPlanId')
            : _stringValue(searchPlan['id']),
        'dimension': data.valueOf('dimension').isNotEmpty
            ? data.valueOf('dimension')
            : _stringValue(searchPlan['dimension']),
        'retrievedAt': retrievedAt,
      },
    ];
  }

  Map<String, dynamic> _buildEvidenceStats({
    required List<Map<String, dynamic>> references,
    required List<String> authorityDomains,
    required _SearchTimeConstraint timeConstraint,
    required _TemporalGuardAssessment temporalGuard,
  }) {
    final freshness = _evaluateFreshnessSignal(
      references: references,
      timeConstraint: timeConstraint,
    );
    final total = references.length;
    var authoritative = 0;
    for (final ref in references) {
      if (_referenceSatisfiesAuthority(
        ref,
        authorityDomains: authorityDomains,
      )) {
        authoritative += 1;
      }
    }
    final coverage = total <= 0 ? 0.0 : (total / 4).clamp(0.0, 1.0).toDouble();
    final authoritySatisfied = authorityDomains.isEmpty || authoritative > 0;
    final authorityScore = total <= 0
        ? 0.0
        : (authoritative / total).clamp(0.0, 1.0);
    final relevanceScore = total <= 0
        ? 0.0
        : references
                  .map(
                    (ref) => (ref['relevanceScore'] as num?)?.toDouble() ?? 0.0,
                  )
                  .reduce((a, b) => a + b) /
              total;
    final freshScore = _freshnessScore(
      freshness: freshness,
      timeConstraint: timeConstraint,
    );
    final qualityScore =
        (relevanceScore * 0.35 +
                authorityScore * 0.25 +
                freshScore * 0.2 +
                coverage * 0.2)
            .clamp(0.0, 1.0)
            .toDouble();
    final confidence = qualityScore;
    final retrievalInsufficient =
        temporalGuard.blocked ||
        (!authoritySatisfied && authorityDomains.isNotEmpty) ||
        ((timeConstraint.freshnessGuardRequired ||
                timeConstraint.isHistoricalLike) &&
            !freshness.satisfied);
    return <String, dynamic>{
      'freshnessHours': freshness.hours,
      'freshnessKnown': freshness.known,
      'freshnessSatisfied': freshness.satisfied,
      'freshScore': freshScore,
      'coverage': coverage,
      'confidence': confidence,
      'qualityScore': qualityScore,
      'authoritySatisfied': authoritySatisfied,
      'authorityScore': authorityScore,
      'relevanceScore': relevanceScore,
      'authoritativeCount': authoritative,
      'totalReferences': total,
      'retrievalInsufficient': retrievalInsufficient,
    };
  }

  _FreshnessSignal _evaluateFreshnessSignal({
    required List<Map<String, dynamic>> references,
    required _SearchTimeConstraint timeConstraint,
  }) {
    _FreshnessSignal? freshestKnown;
    for (final ref in references) {
      final signal = _resolveReferenceFreshnessSignal(
        ref,
        timeConstraint: timeConstraint,
      );
      if (!signal.known) {
        continue;
      }
      if (freshestKnown == null || signal.hours < freshestKnown.hours) {
        freshestKnown = signal;
      }
    }
    if (freshestKnown != null) {
      return freshestKnown;
    }
    return _FreshnessSignal(
      hours: _unknownFreshnessHours(timeConstraint),
      known: false,
      satisfied:
          !(timeConstraint.freshnessGuardRequired ||
              timeConstraint.isHistoricalLike),
    );
  }

  _FreshnessSignal _resolveReferenceFreshnessSignal(
    Map<String, dynamic> reference, {
    required _SearchTimeConstraint timeConstraint,
  }) {
    if (timeConstraint.isHistoricalLike) {
      return _resolveHistoricalWindowSignal(
        reference: reference,
        timeConstraint: timeConstraint,
      );
    }
    final timestamp = _resolvePublicationTimestamp(reference);
    if (timestamp == null) {
      return _FreshnessSignal(
        hours: _unknownFreshnessHours(timeConstraint),
        known: false,
        satisfied: !timeConstraint.freshnessGuardRequired,
      );
    }
    final hours = timeConstraint.referenceNow
        .difference(timestamp.toLocal())
        .inHours
        .clamp(0, 24 * 3650);
    return _FreshnessSignal(
      hours: hours,
      known: true,
      satisfied:
          !timeConstraint.freshnessGuardRequired ||
          hours <= timeConstraint.freshnessHoursMax,
    );
  }

  _FreshnessSignal _resolveHistoricalWindowSignal({
    required Map<String, dynamic> reference,
    required _SearchTimeConstraint timeConstraint,
  }) {
    final candidates = _resolveHistoricalDateCandidates(reference);
    if (candidates.isEmpty) {
      return _FreshnessSignal(
        hours: _unknownFreshnessHours(timeConstraint),
        known: false,
        satisfied: false,
      );
    }
    var matched = false;
    var bestDistance = 24 * 3650;
    for (final candidate in candidates) {
      if (!candidate.isBefore(timeConstraint.start) &&
          !candidate.isAfter(timeConstraint.end)) {
        matched = true;
        bestDistance = 0;
        break;
      }
      final distance = _distanceToRangeHours(
        candidate: candidate,
        start: timeConstraint.start,
        end: timeConstraint.end,
      );
      if (distance < bestDistance) {
        bestDistance = distance;
      }
    }
    return _FreshnessSignal(
      hours: bestDistance,
      known: true,
      satisfied: matched,
    );
  }

  int _distanceToRangeHours({
    required DateTime candidate,
    required DateTime start,
    required DateTime end,
  }) {
    if (candidate.isBefore(start)) {
      return start.difference(candidate).inHours.clamp(0, 24 * 3650);
    }
    if (candidate.isAfter(end)) {
      return candidate.difference(end).inHours.clamp(0, 24 * 3650);
    }
    return 0;
  }

  DateTime? _resolvePublicationTimestamp(Map<String, dynamic> reference) {
    final explicitFields = <String>[
      _stringValue(reference['observedAt']),
      _stringValue(reference['publishedAt']),
      _stringValue(reference['date']),
      _stringValue(reference['published']),
      _stringValue(reference['published_at']),
      _stringValue(reference['timestamp']),
      _stringValue(reference['time']),
    ];
    for (final raw in explicitFields) {
      final parsed = _parseDateTimeLoose(raw);
      if (parsed != null) {
        return parsed;
      }
    }
    return null;
  }

  List<DateTime> _resolveHistoricalDateCandidates(
    Map<String, dynamic> reference,
  ) {
    final out = <DateTime>[];
    final seen = <String>{};

    void add(DateTime? value) {
      if (value == null) {
        return;
      }
      final key = value.toIso8601String();
      if (seen.add(key)) {
        out.add(value);
      }
    }

    add(_parseDateTimeLoose(_stringValue(reference['observedAt'])));
    add(_parseDateTimeLoose(_stringValue(reference['publishedAt'])));
    add(_parseDateTimeLoose(_stringValue(reference['date'])));
    add(_parseDateTimeLoose(_stringValue(reference['published'])));
    add(_parseDateTimeLoose(_stringValue(reference['published_at'])));
    add(_parseDateTimeLoose(_stringValue(reference['timestamp'])));
    add(_parseDateTimeLoose(_stringValue(reference['time'])));
    return out;
  }

  DateTime? _parseDateTimeLoose(String raw) {
    if (raw.trim().isEmpty) {
      return null;
    }
    final parsed = DateTime.tryParse(raw.trim());
    if (parsed != null) {
      return parsed;
    }
    return null;
  }

  int _unknownFreshnessHours(_SearchTimeConstraint timeConstraint) {
    final fallback = timeConstraint.freshnessHoursMax > 0
        ? timeConstraint.freshnessHoursMax + 1
        : 24 * 3650;
    if (timeConstraint.isRealtimeLike && fallback < 9999) {
      return 9999;
    }
    return fallback;
  }

  double _freshnessScore({
    required _FreshnessSignal freshness,
    required _SearchTimeConstraint timeConstraint,
  }) {
    if (!freshness.known) {
      return (timeConstraint.freshnessGuardRequired ||
              timeConstraint.isHistoricalLike)
          ? 0.12
          : 0.35;
    }
    if (freshness.hours <= 0 ||
        freshness.hours <= timeConstraint.freshnessHoursMax) {
      return 1.0;
    }
    if (timeConstraint.freshnessHoursMax <= 0) {
      return 0.5;
    }
    return (timeConstraint.freshnessHoursMax / freshness.hours)
        .clamp(0.0, 1.0)
        .toDouble();
  }

  bool _referenceSatisfiesAuthority(
    Map<String, dynamic> reference, {
    required List<String> authorityDomains,
  }) {
    final sourceTier =
        (reference['sourceTier'] as String?)?.trim().toLowerCase() ?? '';
    if (sourceTier == 'authority') {
      return true;
    }
    final referenceAuthorityDomains =
        (reference['authorityDomains'] as List?)
            ?.whereType<String>()
            .map((domain) => domain.trim().toLowerCase())
            .where((domain) => domain.isNotEmpty)
            .toList(growable: false) ??
        const <String>[];
    if (referenceAuthorityDomains.isNotEmpty &&
        authorityDomains.any(referenceAuthorityDomains.contains)) {
      return true;
    }
    final url = (reference['url'] as String?)?.trim() ?? '';
    final host = Uri.tryParse(url)?.host.toLowerCase() ?? '';
    if (host.isEmpty) {
      return false;
    }
    return authorityDomains.any(
      (domain) => host == domain || host.endsWith('.$domain'),
    );
  }

  String _rewriteQueryWithInlineCalendarPoint(
    String query, {
    String referenceNowIso = '',
    String timezone = '',
  }) {
    return query;
  }

  _TemporalGuardAssessment _evaluateTemporalGuard({
    required String query,
    required _SearchTimeConstraint constraint,
  }) {
    return _TemporalGuardAssessment(searchQuery: query);
  }

  _SearchTimeConstraint _resolveTimeConstraint({
    required String query,
    required Map<String, dynamic> arguments,
    required _DomainRetrievalPolicy domainPolicy,
    required _RetrievalTimeContract timeContract,
  }) {
    final queryNormalization =
        (arguments['queryNormalization'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final temporalReference = _relativeTimeResolver.resolveReferenceContext(
      referenceNowIso: _firstNonEmpty(<String>[
        _stringValue(arguments['referenceNowIso']),
        _stringValue(queryNormalization['referenceNowIso']),
      ]),
      timezone: _firstNonEmpty(<String>[
        _stringValue(arguments['timezone']),
        _stringValue(queryNormalization['timezone']),
      ]),
    );
    final mergedArguments = <String, dynamic>{
      ...arguments,
      'timeScope': _firstNonEmpty(<String>[
        _stringValue(arguments['timeScope']),
        _stringValue(queryNormalization['timeScope']),
      ]),
      'timeRangeStart': _firstNonEmpty(<String>[
        _stringValue(arguments['timeRangeStart']),
        _stringValue(queryNormalization['timeRangeStart']),
      ]),
      'timeRangeEnd': _firstNonEmpty(<String>[
        _stringValue(arguments['timeRangeEnd']),
        _stringValue(queryNormalization['timeRangeEnd']),
      ]),
      'timePoint': _firstNonEmpty(<String>[
        _stringValue(arguments['timePoint']),
        _stringValue(queryNormalization['timePoint']),
      ]),
    };
    final explicitScope = _stringValue(mergedArguments['timeScope']);
    final explicitRange = _resolveRangeByExplicitBounds(mergedArguments);
    final calendarPointRange = _resolveRangeByCalendarPoint(
      arguments: mergedArguments,
      now: temporalReference.referenceNow,
      scope: explicitScope,
    );
    final resolvedCalendarRange = explicitRange ?? calendarPointRange;
    final explicitFreshness = (arguments['freshnessHoursMax'] as num?)?.toInt();
    final effectiveScope = _firstNonEmpty(<String>[
      resolvedCalendarRange?.scope ?? '',
      explicitScope,
      'unspecified',
    ]);
    final effectiveRange =
        resolvedCalendarRange ??
        _CalendarPointRange(
          scope: effectiveScope,
          range: _ResolvedTimeRange(
            start: temporalReference.referenceNow,
            end: temporalReference.referenceNow,
          ),
        );
    final temporalMode = _resolveTemporalMode(
      scope: effectiveScope,
      range: effectiveRange.range,
      referenceNow: temporalReference.referenceNow,
    );
    return _SearchTimeConstraint(
      scope: effectiveScope,
      start: effectiveRange.range.start,
      end: effectiveRange.range.end,
      freshnessHoursMax: explicitFreshness ?? 0,
      referenceNow: temporalReference.referenceNow,
      temporalMode: temporalMode,
    );
  }

  _CalendarPointRange? _resolveRangeByExplicitBounds(
    Map<String, dynamic> arguments,
  ) {
    final start = DateTime.tryParse(
      (arguments['timeRangeStart'] as String?)?.trim() ?? '',
    );
    final end = DateTime.tryParse(
      (arguments['timeRangeEnd'] as String?)?.trim() ?? '',
    );
    if (start == null || end == null || end.isBefore(start)) {
      return null;
    }
    final scope = (arguments['timeScope'] as String?)?.trim().isNotEmpty == true
        ? (arguments['timeScope'] as String).trim()
        : 'custom';
    return _CalendarPointRange(
      scope: scope,
      range: _ResolvedTimeRange(start: start, end: end),
    );
  }

  _CalendarPointRange? _resolveRangeByCalendarPoint({
    required Map<String, dynamic> arguments,
    required DateTime now,
    required String scope,
  }) {
    final normalizedScope = _normalizeCalendarScope(scope);
    final year = _asInt(arguments['timeYear']);
    final month = _asInt(arguments['timeMonth']);
    final day = _asInt(arguments['timeDay']);
    final fallbackPoint = _parseCalendarPoint(
      (arguments['timePoint'] as String?)?.trim() ?? '',
    );
    final y = year ?? fallbackPoint?.year;
    final m = month ?? fallbackPoint?.month;
    final d = day ?? fallbackPoint?.day;
    if (y == null || y <= 0) return null;
    if (m != null && (m < 1 || m > 12)) return null;
    if (d != null && (d < 1 || d > 31)) return null;
    if (y > now.year + 1) return null;

    if (normalizedScope == 'year_month_day' || d != null) {
      if (m == null || d == null) return null;
      final start = DateTime(y, m, d);
      if (start.year != y || start.month != m || start.day != d) return null;
      return _CalendarPointRange(
        scope: 'year_month_day',
        range: _ResolvedTimeRange(
          start: start,
          end: DateTime(y, m, d, 23, 59, 59, 999),
        ),
      );
    }
    if (normalizedScope == 'year_month' || m != null) {
      if (m == null) return null;
      final start = DateTime(y, m, 1);
      final end = DateTime(
        y,
        m + 1,
        1,
      ).subtract(const Duration(milliseconds: 1));
      return _CalendarPointRange(
        scope: 'year_month',
        range: _ResolvedTimeRange(start: start, end: end),
      );
    }
    return _CalendarPointRange(
      scope: 'year',
      range: _ResolvedTimeRange(
        start: DateTime(y, 1, 1),
        end: DateTime(y + 1, 1, 1).subtract(const Duration(milliseconds: 1)),
      ),
    );
  }

  String _normalizeCalendarScope(String scope) {
    switch (scope) {
      case 'yearly':
      case 'calendar_year':
        return 'year';
      case 'monthly':
      case 'calendar_month':
        return 'year_month';
      case 'daily':
      case 'calendar_day':
        return 'year_month_day';
      default:
        return scope;
    }
  }

  _CalendarPoint? _parseCalendarPoint(String raw) {
    if (raw.isEmpty) return null;
    final ymd = RegExp(
      r'^(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})(?:日)?$',
    ).firstMatch(raw);
    if (ymd != null) {
      return _CalendarPoint(
        year: int.tryParse(ymd.group(1) ?? ''),
        month: int.tryParse(ymd.group(2) ?? ''),
        day: int.tryParse(ymd.group(3) ?? ''),
      );
    }
    final ym = RegExp(r'^(\d{4})[-/年](\d{1,2})(?:月)?$').firstMatch(raw);
    if (ym != null) {
      return _CalendarPoint(
        year: int.tryParse(ym.group(1) ?? ''),
        month: int.tryParse(ym.group(2) ?? ''),
      );
    }
    final y = RegExp(r'^(\d{4})(?:年)?$').firstMatch(raw);
    if (y != null) {
      return _CalendarPoint(year: int.tryParse(y.group(1) ?? ''));
    }
    return null;
  }

  int? _asInt(Object? raw) {
    if (raw is int) return raw;
    if (raw is num) return raw.toInt();
    if (raw is String) return int.tryParse(raw.trim());
    return null;
  }

  String _resolveTemporalMode({
    required String scope,
    required _ResolvedTimeRange range,
    required DateTime referenceNow,
  }) {
    final dayFloor = _dayFloor(referenceNow);
    if (range.end.isBefore(dayFloor)) {
      return 'historical';
    }
    if (range.end.isAfter(referenceNow) || !range.start.isBefore(dayFloor)) {
      return 'realtime';
    }
    return 'passive';
  }

  DateTime _dayFloor(DateTime value) {
    return DateTime(value.year, value.month, value.day);
  }

  String _withTimeConstraintQuery({
    required String query,
    required _SearchTimeConstraint constraint,
  }) {
    return query;
  }

  String _buildSearchCacheKey({
    required String query,
    required Map<String, dynamic> arguments,
    required String domainId,
    required int count,
  }) {
    final provider = _stringValue(arguments['provider']);
    final referenceNowIso = _stringValue(arguments['referenceNowIso']);
    final timezone = _stringValue(arguments['timezone']);
    final timeScope = _stringValue(arguments['timeScope']);
    final timePoint = _stringValue(arguments['timePoint']);
    final timeRangeStart = _stringValue(arguments['timeRangeStart']);
    final timeRangeEnd = _stringValue(arguments['timeRangeEnd']);
    final contextConstraints =
        ((arguments['contextConstraints'] as List?) ?? const <Object?>[])
            .map((item) => item.toString().trim())
            .where((item) => item.isNotEmpty)
            .toList(growable: false);
    final parts = <String>[
      query.trim(),
      if (domainId.isNotEmpty) 'domain=$domainId',
      'count=$count',
      if (provider.isNotEmpty) 'provider=$provider',
      if (referenceNowIso.isNotEmpty) 'referenceNow=$referenceNowIso',
      if (timezone.isNotEmpty) 'timezone=$timezone',
      if (timeScope.isNotEmpty) 'timeScope=$timeScope',
      if (timePoint.isNotEmpty) 'timePoint=$timePoint',
      if (timeRangeStart.isNotEmpty) 'timeRangeStart=$timeRangeStart',
      if (timeRangeEnd.isNotEmpty) 'timeRangeEnd=$timeRangeEnd',
      if (contextConstraints.isNotEmpty)
        'context=${contextConstraints.join('|')}',
    ];
    return parts.join(' | ');
  }

  String _withDomainContextQuery({
    required String query,
    required Map<String, dynamic> arguments,
    required _DomainRetrievalPolicy domainPolicy,
  }) {
    return query;
  }

  List<String> _resolveAuthorityDomains({
    required Map<String, dynamic> arguments,
    required _DomainRetrievalPolicy domainPolicy,
  }) {
    final explicit =
        (arguments['authorityDomains'] as List?)
            ?.whereType<String>()
            .map((item) => item.trim().toLowerCase())
            .where((item) => item.isNotEmpty)
            .toSet()
            .toList(growable: false) ??
        const <String>[];
    if (explicit.isNotEmpty) return explicit;
    return domainPolicy.authorityDomains;
  }

  Future<_RetrievalTimeContract> _loadRetrievalTimeContract() async {
    const path = 'assets/assistant/config/retrieval_time_contract.json';
    try {
      final content = await _loadText(path);
      final decoded = jsonDecode(content);
      if (decoded is! Map) return const _RetrievalTimeContract();
      final map = decoded.cast<String, dynamic>();
      return _RetrievalTimeContract(
        defaultScope:
            (map['defaultScope'] as String?)?.trim().isNotEmpty == true
            ? (map['defaultScope'] as String).trim()
            : 'last_30d',
        defaultFreshnessHoursMax:
            (map['defaultFreshnessHoursMax'] as num?)?.toInt() ?? 72,
        supportedScopes:
            (map['supportedScopes'] as List?)
                ?.whereType<String>()
                .map((item) => item.trim())
                .where((item) => item.isNotEmpty)
                .toList(growable: false) ??
            const <String>[
              'latest',
              'today',
              'last_7d',
              'last_30d',
              'last_1y',
              'year_to_date',
              'year',
              'year_month',
              'year_month_day',
              'custom',
              'unspecified',
            ],
        windowHoursByScope: _toIntMap(map['windowHoursByScope']),
        freshnessHoursMaxByScope: _toIntMap(map['freshnessHoursMaxByScope']),
      );
    } catch (_) {
      return const _RetrievalTimeContract();
    }
  }

  Future<_DomainRetrievalPolicy> _loadDomainRetrievalPolicy(
    String domainId,
  ) async {
    if (domainId.trim().isEmpty) return const _DomainRetrievalPolicy();
    final path =
        'assets/assistant/skills/$domainId/config/retrieval_policy.json';
    try {
      final content = await _loadText(path);
      final decoded = jsonDecode(content);
      if (decoded is! Map) return const _DomainRetrievalPolicy();
      final map = decoded.cast<String, dynamic>();
      return _DomainRetrievalPolicy(
        defaultTimeScope: (map['defaultTimeScope'] as String?)?.trim() ?? '',
        defaultFreshnessHoursMax: (map['defaultFreshnessHoursMax'] as num?)
            ?.toInt(),
        maxSearchPlans: (map['maxSearchPlans'] as num?)?.toInt() ?? 2,
        minAcceptedRelevanceScore:
            (map['minAcceptedRelevanceScore'] as num?)?.toDouble() ?? 0.0,
        allowedTimeScopes:
            (map['allowedTimeScopes'] as List?)
                ?.whereType<String>()
                .map((item) => item.trim())
                .where((item) => item.isNotEmpty)
                .toList(growable: false) ??
            const <String>[],
        authorityDomains:
            (map['authorityDomains'] as List?)
                ?.whereType<String>()
                .map((item) => item.trim().toLowerCase())
                .where((item) => item.isNotEmpty)
                .toList(growable: false) ??
            const <String>[],
        contextConstraints:
            (map['contextConstraints'] as List?)
                ?.whereType<String>()
                .map((item) => item.trim())
                .where((item) => item.isNotEmpty)
                .toList(growable: false) ??
            const <String>[],
        negativeKeywords:
            (map['negativeKeywords'] as List?)
                ?.whereType<String>()
                .map((item) => item.trim())
                .where((item) => item.isNotEmpty)
                .toList(growable: false) ??
            const <String>[],
      );
    } catch (_) {
      return const _DomainRetrievalPolicy();
    }
  }

  Map<String, int> _toIntMap(Object? raw) {
    if (raw is! Map) return const <String, int>{};
    final out = <String, int>{};
    for (final entry in raw.entries) {
      final key = entry.key.toString().trim();
      final value = (entry.value as num?)?.toInt();
      if (key.isEmpty || value == null) continue;
      out[key] = value;
    }
    return out;
  }

  Future<String> _loadText(String path) async {
    final overrideLoader = _textLoader;
    if (overrideLoader != null) {
      return overrideLoader(path);
    }
    try {
      return await rootBundle.loadString(path);
    } catch (_) {
      final file = File(path);
      if (await file.exists()) {
        return await file.readAsString();
      }
      rethrow;
    }
  }

  Future<void> _logSearchInteraction({
    required String sessionId,
    required String runId,
    required String traceId,
    required Map<String, dynamic> payload,
    bool hasError = false,
  }) async {
    if (!_enableInteractionLogging) {
      return;
    }
    final entry = <String, dynamic>{
      'ts': DateTime.now().toIso8601String(),
      ...payload,
    };
    if (runId.isNotEmpty) {
      AppRunInteractionCollector.instance.add(runId: runId, interaction: entry);
    }
    await AppLogService.instance.writeEvent(
      logType: AppLogType.search,
      level: hasError ? AppLogLevel.error : AppLogLevel.info,
      context: AppLogContext(
        sessionId: sessionId,
        runId: runId,
        traceId: traceId,
        correlationId: runId,
        sourceDomain: 'assistant',
        sourceService: 'quwoquan_app',
        component: 'search_tool',
        target: 'search_provider',
        action: 'execute_tool',
      ),
      payload: entry,
      summaryPayload: <String, dynamic>{
        'kind': 'search',
        'provider': payload['provider'] ?? '',
        'hasError': hasError,
      },
      hasError: hasError,
    );
    _emitConsoleReadableSearchLog(entry, hasError: hasError);
  }

  void _emitConsoleReadableSearchLog(
    Map<String, dynamic> entry, {
    required bool hasError,
  }) {
    assert(() {
      final kind = (entry['kind'] as String?)?.trim() ?? 'search';
      final provider = (entry['provider'] as String?)?.trim() ?? 'unknown';
      final request =
          (entry['request'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      final response =
          (entry['response'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      final diagnostics =
          (entry['diagnostics'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      final error = (entry['error'] as String?)?.trim() ?? '';
      final searchPlanId = _consoleSearchPlanId(request, response);
      final header = StringBuffer('[AssistantSearch][$kind] ');
      header.write(hasError ? 'ERROR' : 'OK');
      header.write(' stage=retrieval_processing');
      header.write(' tool=web_search');
      header.write(' provider=$provider');
      if (searchPlanId.isNotEmpty) {
        header.write(' searchPlanId=$searchPlanId');
      }
      debugPrint(header.toString());
      for (final line in ConsolePrettyLogFormatter.renderSection(
        prefix: '[AssistantSearch] ',
        title: 'request',
        value: ConsolePrettyLogFormatter.normalizeJsonLikeValue(request),
      )) {
        debugPrint(line);
      }
      for (final line in ConsolePrettyLogFormatter.renderSection(
        prefix: '[AssistantSearch] ',
        title: 'response',
        value: ConsolePrettyLogFormatter.normalizeJsonLikeValue(response),
      )) {
        debugPrint(line);
      }
      if (diagnostics.isNotEmpty) {
        for (final line in ConsolePrettyLogFormatter.renderSection(
          prefix: '[AssistantSearch] ',
          title: 'diagnostics',
          value: ConsolePrettyLogFormatter.normalizeJsonLikeValue(diagnostics),
        )) {
          debugPrint(line);
        }
      }
      if (error.isNotEmpty) {
        for (final line in ConsolePrettyLogFormatter.renderSection(
          prefix: '[AssistantSearch] ',
          title: 'error',
          value: error,
        )) {
          debugPrint(line);
        }
      }
      return true;
    }());
  }

  String _consoleSearchPlanId(
    Map<String, dynamic> request,
    Map<String, dynamic> response,
  ) {
    for (final source in <Map<String, dynamic>>[request, response]) {
      final searchPlanId = (source['searchPlanId'] as String?)?.trim() ?? '';
      if (searchPlanId.isNotEmpty) {
        return searchPlanId;
      }
    }
    return '';
  }

  String _summarizeProviderResult({
    required AssistantSearchProvider provider,
    required Object? decoded,
  }) {
    switch (provider) {
      case AssistantSearchProvider.perplexity:
        return _summarizePerplexity(decoded);
      case AssistantSearchProvider.brave:
        return _summarizeBrave(decoded);
      case AssistantSearchProvider.openclawProxy:
        return _summarizeOpenclaw(decoded);
      case AssistantSearchProvider.serpapi:
        return _summarizeSerpApi(decoded);
      case AssistantSearchProvider.duckduckgo:
        return _summarizeDuckduckgo(decoded);
    }
  }

  List<Map<String, dynamic>> _extractReferences({
    required AssistantSearchProvider provider,
    required Object? decoded,
  }) {
    switch (provider) {
      case AssistantSearchProvider.brave:
        return _extractBraveReferences(decoded);
      case AssistantSearchProvider.duckduckgo:
        return _extractDuckduckgoReferences(decoded);
      case AssistantSearchProvider.perplexity:
        return _extractPerplexityReferences(decoded);
      case AssistantSearchProvider.serpapi:
        return _extractSerpApiReferences(decoded);
      case AssistantSearchProvider.openclawProxy:
        return _extractOpenclawReferences(decoded);
    }
  }

  /// 供应商最小 JSON fixture 测试用（与内部 `_extractReferences` 输出一致）。
  List<Map<String, dynamic>> extractReferencesForFixtureTest({
    required AssistantSearchProvider provider,
    required Object? decoded,
  }) {
    return _extractReferences(provider: provider, decoded: decoded);
  }

  List<Map<String, dynamic>> _extractBraveReferences(Object? decoded) {
    if (decoded is! Map) return const <Map<String, dynamic>>[];
    final results =
        ((decoded['web'] as Map?)?['results'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    return results
        .take(12)
        .map((item) {
          final n = NormalizedWebReference.fromBraveWebResult(item);
          return _normalizedReference(
            provider: AssistantSearchProvider.brave,
            title: n.title,
            url: n.url,
            snippet: n.snippet,
            raw: item,
          );
        })
        .where((item) => (item['url'] as String).isNotEmpty)
        .toList(growable: false);
  }

  List<Map<String, dynamic>> _extractDuckduckgoReferences(Object? decoded) {
    if (decoded is! Map) return const <Map<String, dynamic>>[];
    final organic =
        (decoded['organic_results'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    if (organic.isNotEmpty) {
      return organic
          .take(12)
          .map((item) {
            final n = NormalizedWebReference.fromSerpOrganicItem(item);
            return _normalizedReference(
              provider: AssistantSearchProvider.duckduckgo,
              title: n.title,
              url: n.url,
              snippet: n.snippet,
              raw: item,
            );
          })
          .where((item) => (item['url'] as String).isNotEmpty)
          .toList(growable: false);
    }
    final refs = <Map<String, dynamic>>[];
    final related =
        (decoded['RelatedTopics'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    for (final item in related.take(12)) {
      final n = NormalizedWebReference.fromDuckduckgoRelatedTopic(item);
      if (n.url.isNotEmpty) {
        refs.add(
          _normalizedReference(
            provider: AssistantSearchProvider.duckduckgo,
            title: n.title,
            url: n.url,
            snippet: n.snippet,
            raw: item,
          ),
        );
      }
    }
    return refs;
  }

  List<Map<String, dynamic>> _extractPerplexityReferences(Object? decoded) {
    if (decoded is! Map) return const <Map<String, dynamic>>[];
    final citations =
        (decoded['citations'] as List?)
            ?.whereType<String>()
            .map((item) => item.trim())
            .where((item) => item.isNotEmpty)
            .toList(growable: false) ??
        const <String>[];
    return citations
        .take(12)
        .map(
          (url) => _normalizedReference(
            provider: AssistantSearchProvider.perplexity,
            title: url,
            url: url,
            snippet: '',
          ),
        )
        .toList(growable: false);
  }

  List<Map<String, dynamic>> _extractSerpApiReferences(Object? decoded) {
    if (decoded is! Map) return const <Map<String, dynamic>>[];
    final organic =
        (decoded['organic_results'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    return organic
        .take(12)
        .map((item) {
          final n = NormalizedWebReference.fromSerpApiOrganic(item);
          return _normalizedReference(
            provider: AssistantSearchProvider.serpapi,
            title: n.title,
            url: n.url,
            snippet: n.snippet,
            raw: item,
          );
        })
        .where((item) => (item['url'] as String).isNotEmpty)
        .toList(growable: false);
  }

  List<Map<String, dynamic>> _extractOpenclawReferences(Object? decoded) {
    if (decoded is! Map) return const <Map<String, dynamic>>[];
    final rawRefs =
        (decoded['references'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    return rawRefs
        .take(12)
        .map(
          (item) => _normalizedReference(
            provider: AssistantSearchProvider.openclawProxy,
            title: (item['title'] as String?)?.trim() ?? '',
            url: (item['url'] as String?)?.trim() ?? '',
            snippet: (item['snippet'] as String?)?.trim() ?? '',
            raw: item,
          ),
        )
        .where((item) => (item['url'] as String).isNotEmpty)
        .toList(growable: false);
  }

  Map<String, dynamic> _normalizedReference({
    required AssistantSearchProvider provider,
    required String title,
    required String url,
    required String snippet,
    Map<String, dynamic>? raw,
  }) {
    final item = <String, dynamic>{
      'title': title,
      'url': url,
      'snippet': snippet,
      'provider': provider.name,
    };
    final metadata = raw;
    if (metadata == null || metadata.isEmpty) {
      return item;
    }
    final source = _stringValue(metadata['source']);
    if (source.isNotEmpty) {
      item['source'] = source;
    }
    final sourceHost = _stringValue(metadata['sourceHost']);
    if (sourceHost.isNotEmpty) {
      item['sourceHost'] = sourceHost;
    }
    final sourceTier = _stringValue(metadata['sourceTier']);
    if (sourceTier.isNotEmpty) {
      item['sourceTier'] = sourceTier;
    }
    final publishedAt = _stringValue(metadata['publishedAt']);
    if (publishedAt.isNotEmpty) {
      item['publishedAt'] = publishedAt;
    }
    final observedAt = _stringValue(metadata['observedAt']);
    if (observedAt.isNotEmpty) {
      item['observedAt'] = observedAt;
    }
    final providerDate = _firstNonEmpty(<String>[
      _stringValue(metadata['date']),
      _stringValue(metadata['published']),
      _stringValue(metadata['published_at']),
      _stringValue(metadata['timestamp']),
      _stringValue(metadata['time']),
    ]);
    if (providerDate.isNotEmpty) {
      item['date'] = providerDate;
    }
    final searchPlanId = _stringValue(metadata['searchPlanId']);
    if (searchPlanId.isNotEmpty) {
      item['searchPlanId'] = searchPlanId;
    }
    final dimension = _stringValue(metadata['dimension']);
    if (dimension.isNotEmpty) {
      item['dimension'] = dimension;
    }
    final relevanceScore = (metadata['relevanceScore'] as num?)?.toDouble();
    if (relevanceScore != null) {
      item['relevanceScore'] = relevanceScore;
    }
    final authorityDomains =
        (metadata['authorityDomains'] as List?)
            ?.whereType<String>()
            .map((value) => value.trim().toLowerCase())
            .where((value) => value.isNotEmpty)
            .toList(growable: false) ??
        const <String>[];
    if (authorityDomains.isNotEmpty) {
      item['authorityDomains'] = authorityDomains;
    }
    return item;
  }

  String _summarizePerplexity(Object? decoded) {
    if (decoded is! Map) return '';
    final choices = decoded['choices'];
    if (choices is! List || choices.isEmpty) return '';
    final first = choices.first;
    if (first is! Map) return '';
    final message = first['message'];
    if (message is! Map) return '';
    final content = (message['content'] as String?) ?? '';
    return _truncate(_compressWhitespace(content));
  }

  String _summarizeBrave(Object? decoded) {
    if (decoded is! Map) return '';
    final web = decoded['web'];
    if (web is! Map) return '';
    final results = web['results'];
    if (results is! List || results.isEmpty) return '';
    final snippets = <String>[];
    for (final item in results.take(3)) {
      if (item is! Map) continue;
      final title = (item['title'] as String?)?.trim() ?? '';
      final description = (item['description'] as String?)?.trim() ?? '';
      final combined = _compressWhitespace(
        [title, description].where((s) => s.isNotEmpty).join(' - '),
      );
      if (combined.isNotEmpty) {
        snippets.add(combined);
      }
    }
    if (snippets.isEmpty) return '';
    return _truncate(snippets.join('；'));
  }

  String _summarizeOpenclaw(Object? decoded) {
    if (decoded is! Map) {
      return _truncate(_compressWhitespace(decoded.toString()));
    }
    final message = (decoded['message'] as String?)?.trim() ?? '';
    if (message.isNotEmpty) {
      return _truncate(_compressWhitespace(message));
    }
    final data = decoded['data'];
    if (data is Map && data['summary'] is String) {
      return _truncate(_compressWhitespace((data['summary'] as String?) ?? ''));
    }
    return '';
  }

  String _summarizeDuckduckgo(Object? decoded) {
    if (decoded is! Map) return '';
    final organic = (decoded['organic_results'] as List?)
        ?.whereType<Map>()
        .toList();
    if (organic != null && organic.isNotEmpty) {
      final snippets = <String>[];
      for (final item in organic.take(4)) {
        final title = (item['title'] as String?)?.trim() ?? '';
        final snippet = (item['snippet'] as String?)?.trim() ?? '';
        final combined = _compressWhitespace(
          [title, snippet].where((s) => s.isNotEmpty).join(' - '),
        );
        if (combined.isNotEmpty) snippets.add(combined);
      }
      if (snippets.isNotEmpty) return _truncate(snippets.join('；'));
    }
    final abstractText = (decoded['AbstractText'] as String?)?.trim() ?? '';
    final heading = (decoded['Heading'] as String?)?.trim() ?? '';
    final abstractLine = _compressWhitespace(
      [heading, abstractText].where((s) => s.isNotEmpty).join(' - '),
    );
    if (abstractLine.isNotEmpty) return _truncate(abstractLine);
    return '';
  }

  String _summarizeSerpApi(Object? decoded) {
    if (decoded is! Map) return '';
    final answerBox = decoded['answer_box'];
    if (answerBox is Map) {
      final title = (answerBox['title'] as String?)?.trim() ?? '';
      final answer = (answerBox['answer'] as String?)?.trim() ?? '';
      final snippet = (answerBox['snippet'] as String?)?.trim() ?? '';
      final merged = _compressWhitespace(
        [title, answer, snippet].where((s) => s.isNotEmpty).join(' - '),
      );
      if (merged.isNotEmpty) return _truncate(merged);
    }
    final organic = decoded['organic_results'];
    if (organic is! List || organic.isEmpty) return '';
    final snippets = <String>[];
    for (final item in organic.take(4)) {
      if (item is! Map) continue;
      final title = (item['title'] as String?)?.trim() ?? '';
      final snippet = (item['snippet'] as String?)?.trim() ?? '';
      final merged = _compressWhitespace(
        [title, snippet].where((s) => s.isNotEmpty).join(' - '),
      );
      if (merged.isNotEmpty) {
        snippets.add(merged);
      }
    }
    if (snippets.isEmpty) return '';
    return _truncate(snippets.join('；'));
  }

  String _compressWhitespace(String input) {
    return input.replaceAll(RegExp(r'\s+'), ' ').trim();
  }

  String _truncate(String input, {int maxChars = 1200}) {
    if (input.length <= maxChars) return input;
    return '${input.substring(0, maxChars)}...';
  }

  AssistantSearchProvider? _resolveProvider({
    required String? raw,
    required _WebSearchRuntimeConfig config,
  }) {
    final normalized = (raw ?? '').trim().toLowerCase();
    final explicit = _parseProvider(normalized);
    if (explicit != null && _providerReady(explicit, config)) {
      return explicit;
    }
    final fallbackOrder = _preferredProviderOrder(config);
    for (final candidate in fallbackOrder) {
      if (_providerReady(candidate, config)) {
        return candidate;
      }
    }
    return null;
  }

  List<AssistantSearchProvider> _preferredProviderOrder(
    _WebSearchRuntimeConfig config,
  ) {
    final configuredDefault = _parseProvider(config.defaultProvider);
    final ordered = <AssistantSearchProvider>[
      if (configuredDefault != null &&
          configuredDefault != AssistantSearchProvider.duckduckgo)
        configuredDefault,
      if (_defaultProvider != AssistantSearchProvider.duckduckgo)
        _defaultProvider,
      AssistantSearchProvider.serpapi,
      AssistantSearchProvider.brave,
      AssistantSearchProvider.openclawProxy,
      AssistantSearchProvider.perplexity,
      if (configuredDefault == AssistantSearchProvider.duckduckgo)
        AssistantSearchProvider.duckduckgo,
      if (_defaultProvider == AssistantSearchProvider.duckduckgo)
        AssistantSearchProvider.duckduckgo,
      AssistantSearchProvider.duckduckgo,
    ];
    final seen = <AssistantSearchProvider>{};
    return ordered.where(seen.add).toList(growable: false);
  }

  bool _providerReady(
    AssistantSearchProvider provider,
    _WebSearchRuntimeConfig config,
  ) {
    switch (provider) {
      case AssistantSearchProvider.openclawProxy:
        return config.openclawBaseUrl.isNotEmpty;
      case AssistantSearchProvider.perplexity:
        return config.perplexityApiKey.isNotEmpty;
      case AssistantSearchProvider.brave:
        return config.braveApiKey.isNotEmpty;
      case AssistantSearchProvider.serpapi:
        return config.serpApiKey.isNotEmpty;
      case AssistantSearchProvider.duckduckgo:
        return true;
    }
  }

  Future<Object?> _runProviderSearch({
    required AssistantSearchProvider provider,
    required String query,
    required int count,
    required _WebSearchRuntimeConfig config,
  }) async {
    switch (provider) {
      case AssistantSearchProvider.brave:
        return _searchBrave(
          query: query,
          count: count,
          apiKey: config.braveApiKey,
        );
      case AssistantSearchProvider.perplexity:
        return _searchPerplexity(
          query: query,
          apiKey: config.perplexityApiKey,
          baseUrl: config.perplexityBaseUrl,
          model: config.perplexityModel,
        );
      case AssistantSearchProvider.openclawProxy:
        return _searchOpenClawProxy(
          query: query,
          count: count,
          baseUrl: config.openclawBaseUrl,
          token: config.openclawToken,
        );
      case AssistantSearchProvider.serpapi:
        return _searchSerpApi(
          query: query,
          count: count,
          apiKey: config.serpApiKey,
        );
      case AssistantSearchProvider.duckduckgo:
        return _searchDuckDuckGo(query: query);
    }
  }

  _ClassifiedSearchError _classifySearchError(Object error) {
    final text = error.toString();
    final normalized = text.toLowerCase();
    if (normalized.contains('(401)') ||
        normalized.contains('(403)') ||
        normalized.contains('unauthorized')) {
      return const _ClassifiedSearchError(
        errorCode: AssistantErrorCode.unauthorized,
        message: '搜索服务鉴权失败，请检查配置。',
      );
    }
    if (normalized.contains('(429)') || normalized.contains('rate limit')) {
      return const _ClassifiedSearchError(
        errorCode: AssistantErrorCode.rateLimited,
        message: '搜索服务当前限流，请稍后重试。',
      );
    }
    if (normalized.contains('timeout') ||
        normalized.contains('timed out') ||
        normalized.contains('socket') ||
        normalized.contains('connection') ||
        normalized.contains('network') ||
        normalized.contains('(500)') ||
        normalized.contains('(502)') ||
        normalized.contains('(503)') ||
        normalized.contains('(504)') ||
        normalized.contains('unavailable') ||
        normalized.contains('暂时不可用')) {
      return const _ClassifiedSearchError(
        errorCode: AssistantErrorCode.networkUnavailable,
        message: '搜索服务暂时不可用，已尝试自动恢复。',
      );
    }
    return const _ClassifiedSearchError(
      errorCode: AssistantErrorCode.executionFailed,
      message: '搜索失败，请稍后重试。',
    );
  }

  Future<Object?> _searchBrave({
    required String query,
    required int count,
    required String apiKey,
  }) async {
    if (apiKey.isEmpty) {
      throw Exception('Brave API key is missing');
    }
    final url = Uri.parse(
      'https://api.search.brave.com/res/v1/web/search',
    ).replace(queryParameters: <String, String>{'q': query, 'count': '$count'});
    final response = await _httpClient
        .get(
          url,
          headers: <String, String>{
            'Accept': 'application/json',
            'X-Subscription-Token': apiKey,
          },
        )
        .timeout(_networkTimeout);
    if (response.statusCode >= 400) {
      throw Exception('Brave search failed (${response.statusCode})');
    }
    return jsonDecode(response.body);
  }

  Future<Object?> _searchPerplexity({
    required String query,
    required String apiKey,
    required String baseUrl,
    required String model,
  }) async {
    if (apiKey.isEmpty) {
      throw Exception('Perplexity API key is missing');
    }
    final response = await _httpClient
        .post(
          Uri.parse(
            '${baseUrl.replaceAll(RegExp(r'/$'), '')}/chat/completions',
          ),
          headers: <String, String>{
            'Content-Type': 'application/json',
            'Authorization': 'Bearer $apiKey',
            if (baseUrl.contains('openrouter.ai'))
              'HTTP-Referer': AppPublicContentLinks.siteOriginForHttpHeaders(),
            if (baseUrl.contains('openrouter.ai'))
              'X-Title': 'Quwoquan Assistant Web Search',
          },
          body: jsonEncode(<String, dynamic>{
            'model': model,
            'messages': <Map<String, String>>[
              <String, String>{'role': 'user', 'content': query},
            ],
          }),
        )
        .timeout(_networkTimeout);
    if (response.statusCode >= 400) {
      throw Exception('Perplexity search failed (${response.statusCode})');
    }
    return jsonDecode(response.body);
  }

  Future<Object?> _searchOpenClawProxy({
    required String query,
    required int count,
    required String baseUrl,
    required String token,
  }) async {
    if (baseUrl.isEmpty) {
      throw Exception('OpenClaw proxy base URL is missing');
    }
    final url = Uri.parse('$baseUrl/v1/skills/invoke');
    final headers = <String, String>{'Content-Type': 'application/json'};
    if (token.isNotEmpty) {
      headers['Authorization'] = 'Bearer $token';
    }
    final response = await _httpClient
        .post(
          url,
          headers: headers,
          body: jsonEncode(<String, dynamic>{
            'skill_id': 'web.quick_search',
            'arguments': <String, dynamic>{
              'toolName': 'web_search',
              'toolArgs': <String, dynamic>{'query': query, 'count': count},
            },
          }),
        )
        .timeout(_networkTimeout);
    if (response.statusCode >= 400) {
      throw Exception('OpenClaw proxy search failed (${response.statusCode})');
    }
    return jsonDecode(response.body);
  }

  Future<Object?> _searchDuckDuckGo({required String query}) async {
    final cleanQuery = _stripSearchSuffixes(query);
    final response = await _httpClient
        .post(
          Uri.parse('https://html.duckduckgo.com/html/'),
          headers: const <String, String>{
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'QuwoquanAssistant/1.0',
          },
          body: 'q=${Uri.encodeComponent(cleanQuery)}&kl=cn-zh',
        )
        .timeout(const Duration(seconds: 12));
    if (response.statusCode >= 400) {
      throw Exception('DuckDuckGo search failed (${response.statusCode})');
    }
    return _parseDuckDuckGoHtml(response.body);
  }

  String _stripSearchSuffixes(String query) {
    return query
        .replaceAll(RegExp(r'\s*时间范围:\S+'), '')
        .replaceAll(RegExp(r'\s*上下文限定:.+$'), '')
        .trim();
  }

  Map<String, dynamic> _parseDuckDuckGoHtml(String html) {
    final results = <Map<String, dynamic>>[];
    final linkPattern = RegExp(
      r'<a[^>]+class="result__a"[^>]+href="([^"]*)"[^>]*>(.*?)</a>',
      dotAll: true,
    );
    final snippetPattern = RegExp(
      r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
      dotAll: true,
    );
    final linkMatches = linkPattern.allMatches(html).toList();
    final snippetMatches = snippetPattern.allMatches(html).toList();
    for (var i = 0; i < linkMatches.length && i < 10; i++) {
      var url = linkMatches[i].group(1) ?? '';
      if (url.contains('duckduckgo.com/l/?uddg=')) {
        final uddg = Uri.tryParse(url)?.queryParameters['uddg'];
        if (uddg != null && uddg.isNotEmpty) url = uddg;
      }
      url = Uri.decodeComponent(url);
      final title = _stripHtmlTags(linkMatches[i].group(2) ?? '');
      final snippet = i < snippetMatches.length
          ? _stripHtmlTags(snippetMatches[i].group(1) ?? '')
          : '';
      if (url.startsWith('http')) {
        results.add(<String, dynamic>{
          'title': title,
          'url': url,
          'snippet': snippet,
        });
      }
    }
    final abstractText = results.isNotEmpty
        ? results
              .take(3)
              .map((r) => '${r['title']} - ${r['snippet']}')
              .join('；')
        : '';
    return <String, dynamic>{
      'AbstractText': abstractText,
      'Heading': '',
      'RelatedTopics': <Object?>[],
      'organic_results': results,
      '_source': 'ddg_html',
    };
  }

  String _stripHtmlTags(String html) {
    return html
        .replaceAll(RegExp(r'<[^>]+>'), '')
        .replaceAll(RegExp(r'&amp;'), '&')
        .replaceAll(RegExp(r'&lt;'), '<')
        .replaceAll(RegExp(r'&gt;'), '>')
        .replaceAll(RegExp(r'&quot;'), '"')
        .replaceAll(RegExp(r'&#x27;|&#39;'), "'")
        .replaceAll(RegExp(r'\s+'), ' ')
        .trim();
  }

  Future<Object?> _searchSerpApi({
    required String query,
    required int count,
    required String apiKey,
  }) async {
    if (apiKey.isEmpty) {
      throw Exception('SerpApi key is missing');
    }
    final url = Uri.parse('https://serpapi.com/search.json').replace(
      queryParameters: <String, String>{
        'engine': 'google',
        'q': query,
        'api_key': apiKey,
        'hl': 'zh-cn',
        'gl': 'cn',
        'num': '$count',
      },
    );
    final response = await _httpClient
        .get(url, headers: const <String, String>{'Accept': 'application/json'})
        .timeout(_networkTimeout);
    if (response.statusCode >= 400) {
      throw Exception('SerpApi search failed (${response.statusCode})');
    }
    return jsonDecode(response.body);
  }

  Future<_WebSearchRuntimeConfig> _resolveRuntimeConfig() async {
    final profile = _resolveRuntimeConfigFromDisk
        ? await _loadSearchProfile()
        : const _WebSearchProfile();
    String brave = _braveApiKey.trim();
    String perplexity = _perplexityApiKey.trim();
    String serpapi = _serpApiKey.trim();
    String openclawBaseUrl = _openclawBaseUrl.trim();
    String openclawToken = _openclawToken.trim();
    String openrouter = '';

    final dotEnv = _resolveRuntimeConfigFromDisk
        ? await _loadRuntimeDotEnv()
        : const <String, String>{};
    if (brave.isEmpty) {
      brave = _resolveInterpolatedKey(profile.braveApiKeyRaw, dotEnv).trim();
    }
    if (perplexity.isEmpty) {
      perplexity = _resolveInterpolatedKey(
        profile.perplexityApiKeyRaw,
        dotEnv,
      ).trim();
    }
    if (openrouter.isEmpty) {
      openrouter = _resolveInterpolatedKey(
        profile.openrouterApiKeyRaw,
        dotEnv,
      ).trim();
    }
    if (serpapi.isEmpty) {
      serpapi = _resolveInterpolatedKey(profile.serpApiKeyRaw, dotEnv).trim();
    }
    if (brave.isEmpty) {
      brave =
          (Platform.environment['PERSONAL_ASSISTANT_BRAVE_API_KEY'] ??
                  Platform.environment['BRAVE_API_KEY'] ??
                  dotEnv['PERSONAL_ASSISTANT_BRAVE_API_KEY'] ??
                  dotEnv['BRAVE_API_KEY'] ??
                  '')
              .trim();
    }
    if (perplexity.isEmpty) {
      perplexity =
          (Platform.environment['PERSONAL_ASSISTANT_PERPLEXITY_API_KEY'] ??
                  Platform.environment['PERPLEXITY_API_KEY'] ??
                  dotEnv['PERSONAL_ASSISTANT_PERPLEXITY_API_KEY'] ??
                  dotEnv['PERPLEXITY_API_KEY'] ??
                  '')
              .trim();
    }
    openrouter =
        (Platform.environment['PERSONAL_ASSISTANT_OPENROUTER_API_KEY'] ??
                Platform.environment['OPENROUTER_API_KEY'] ??
                dotEnv['PERSONAL_ASSISTANT_OPENROUTER_API_KEY'] ??
                dotEnv['OPENROUTER_API_KEY'] ??
                '')
            .trim();
    if (serpapi.isEmpty) {
      serpapi =
          (Platform.environment['PERSONAL_ASSISTANT_SERPAPI_API_KEY'] ??
                  Platform.environment['SERPAPI_API_KEY'] ??
                  dotEnv['PERSONAL_ASSISTANT_SERPAPI_API_KEY'] ??
                  dotEnv['SERPAPI_API_KEY'] ??
                  '')
              .trim();
    }
    if (openclawBaseUrl.isEmpty) {
      openclawBaseUrl =
          (Platform.environment['PERSONAL_ASSISTANT_OPENCLAW_BASE_URL'] ??
                  dotEnv['PERSONAL_ASSISTANT_OPENCLAW_BASE_URL'] ??
                  '')
              .trim();
    }
    if (openclawToken.isEmpty) {
      openclawToken =
          (Platform.environment['PERSONAL_ASSISTANT_OPENCLAW_TOKEN'] ??
                  dotEnv['PERSONAL_ASSISTANT_OPENCLAW_TOKEN'] ??
                  '')
              .trim();
    }

    final resolvedPerplexity = _resolvePerplexityAuth(
      perplexityApiKey: perplexity,
      openrouterApiKey: openrouter,
      preferredBaseUrl: profile.perplexityBaseUrl,
      preferredModel: profile.perplexityModel,
    );
    return _WebSearchRuntimeConfig(
      defaultProvider: profile.provider,
      braveApiKey: brave,
      perplexityApiKey: resolvedPerplexity.apiKey,
      perplexityBaseUrl: resolvedPerplexity.baseUrl,
      perplexityModel: resolvedPerplexity.model,
      serpApiKey: serpapi,
      openclawBaseUrl: openclawBaseUrl,
      openclawToken: openclawToken,
    );
  }

  Future<Map<String, String>> _loadRuntimeDotEnv() async {
    final merged = <String, String>{};
    try {
      final assetEnv = await rootBundle.loadString('assistant/.env');
      merged.addAll(_parseDotEnv(assetEnv));
    } catch (_) {
      // ignore asset missing
    }
    try {
      final docDir = await getApplicationDocumentsDirectory();
      var basePath = docDir.path;
      if (basePath.endsWith('app_flutter')) {
        basePath = Directory(basePath).parent.path;
      }
      final localCandidates = <String>[
        '$basePath/assistant/.env',
        '$basePath/.personal_assistant/.env',
        '$basePath/.assistant/.env',
      ];
      for (final p in localCandidates) {
        final file = File(p);
        if (!await file.exists()) continue;
        final text = await file.readAsString();
        merged.addAll(_parseDotEnv(text));
      }
      final home = Platform.environment['HOME'] ?? '';
      if (home.trim().isNotEmpty) {
        final moltbotEnv = File('$home/.moltbot/.env');
        if (await moltbotEnv.exists()) {
          final text = await moltbotEnv.readAsString();
          merged.addAll(_parseDotEnv(text));
        }
        final clawdbotEnv = File('$home/.clawdbot/.env');
        if (await clawdbotEnv.exists()) {
          final text = await clawdbotEnv.readAsString();
          merged.addAll(_parseDotEnv(text));
        }
        final searxngEnv = File('$home/.serpapi/.env');
        if (await searxngEnv.exists()) {
          final text = await searxngEnv.readAsString();
          merged.addAll(_parseDotEnv(text));
        }
      }
    } catch (_) {
      // ignore runtime file loading failure
    }
    return merged;
  }

  Future<_WebSearchProfile> _loadSearchProfile() async {
    final candidates = <Map<String, dynamic>>[];
    try {
      final bundledText = await rootBundle.loadString('assistant/config.json');
      final decoded = jsonDecode(bundledText);
      if (decoded is Map<String, dynamic>) {
        candidates.add(decoded);
      }
    } catch (_) {
      // ignore bundled config read error
    }
    try {
      final docDir = await getApplicationDocumentsDirectory();
      var basePath = docDir.path;
      if (basePath.endsWith('app_flutter')) {
        basePath = Directory(basePath).parent.path;
      }
      final localCandidates = <String>[
        '$basePath/assistant/config.json',
        '$basePath/.personal_assistant/config.json',
        '$basePath/.assistant/config.json',
      ];
      for (final p in localCandidates) {
        final file = File(p);
        if (!await file.exists()) continue;
        final text = await file.readAsString();
        final decoded = jsonDecode(text);
        if (decoded is Map<String, dynamic>) {
          candidates.add(decoded);
        }
      }
    } catch (_) {
      // ignore local config read error
    }
    for (final root in candidates.reversed) {
      final profile = _extractSearchProfile(root);
      if (profile.isNotEmpty) return profile;
    }
    return const _WebSearchProfile();
  }

  _WebSearchProfile _extractSearchProfile(Map<String, dynamic> root) {
    final tools = root['tools'];
    if (tools is! Map) return const _WebSearchProfile();
    final web = tools['web'];
    if (web is! Map) return const _WebSearchProfile();
    final search = web['search'];
    if (search is! Map) return const _WebSearchProfile();
    final perplexity = search['perplexity'];
    Map<Object?, Object?> perplexityMap = const <Object?, Object?>{};
    if (perplexity is Map) {
      perplexityMap = Map<Object?, Object?>.from(perplexity);
    }
    return _WebSearchProfile(
      provider: (search['provider'] as String?)?.trim() ?? '',
      braveApiKeyRaw: (search['apiKey'] as String?)?.trim() ?? '',
      perplexityApiKeyRaw: (perplexityMap['apiKey'] as String?)?.trim() ?? '',
      openrouterApiKeyRaw:
          (search['openrouterApiKey'] as String?)?.trim() ?? '',
      serpApiKeyRaw: (search['serpApiKey'] as String?)?.trim() ?? '',
      perplexityBaseUrl: (perplexityMap['baseUrl'] as String?)?.trim() ?? '',
      perplexityModel: (perplexityMap['model'] as String?)?.trim() ?? '',
    );
  }

  Map<String, String> _parseDotEnv(String text) {
    final map = <String, String>{};
    final lines = const LineSplitter().convert(text);
    for (final line in lines) {
      final trimmed = line.trim();
      if (trimmed.isEmpty || trimmed.startsWith('#')) continue;
      final idx = trimmed.indexOf('=');
      if (idx <= 0) continue;
      final key = trimmed.substring(0, idx).trim();
      final value = trimmed.substring(idx + 1).trim();
      if (key.isNotEmpty) map[key] = value;
    }
    return map;
  }

  AssistantSearchProvider? _parseProvider(String raw) {
    final v = raw.trim().toLowerCase();
    if (v == 'brave') return AssistantSearchProvider.brave;
    if (v == 'perplexity') return AssistantSearchProvider.perplexity;
    if (v == 'openclaw_proxy') return AssistantSearchProvider.openclawProxy;
    if (v == 'serpapi') return AssistantSearchProvider.serpapi;
    if (v == 'duckduckgo' || v == 'ddg') {
      return AssistantSearchProvider.duckduckgo;
    }
    return null;
  }

  String _resolveInterpolatedKey(String raw, Map<String, String> dotEnv) {
    if (raw.isEmpty) return '';
    final envMatch = RegExp(r'^\$\{([A-Z0-9_]+)\}$').firstMatch(raw);
    if (envMatch == null) return raw;
    final envName = envMatch.group(1)!;
    return (Platform.environment[envName] ?? dotEnv[envName] ?? '').trim();
  }

  _PerplexityResolvedAuth _resolvePerplexityAuth({
    required String perplexityApiKey,
    required String openrouterApiKey,
    String preferredBaseUrl = '',
    String preferredModel = '',
  }) {
    if (perplexityApiKey.isNotEmpty) {
      return _PerplexityResolvedAuth(
        apiKey: '',
        baseUrl: preferredBaseUrl.isEmpty
            ? 'https://api.perplexity.ai'
            : preferredBaseUrl,
        model: preferredModel.isEmpty ? 'sonar-pro' : preferredModel,
      ).copyWith(apiKey: perplexityApiKey);
    }
    if (openrouterApiKey.isNotEmpty) {
      return _PerplexityResolvedAuth(
        apiKey: '',
        baseUrl: preferredBaseUrl.isEmpty
            ? 'https://openrouter.ai/api/v1'
            : preferredBaseUrl,
        model: preferredModel.isEmpty ? 'perplexity/sonar-pro' : preferredModel,
      ).copyWith(apiKey: openrouterApiKey);
    }
    return _PerplexityResolvedAuth(
      apiKey: '',
      baseUrl: preferredBaseUrl.isEmpty
          ? 'https://api.perplexity.ai'
          : preferredBaseUrl,
      model: preferredModel.isEmpty ? 'sonar-pro' : preferredModel,
    );
  }

  /// Executes multiple queries concurrently and merges references.
  Future<AssistantToolResult> _executeMultiQuery(
    Map<String, dynamic> arguments,
    List<Map<String, dynamic>> searchPlans,
  ) async {
    final domainId =
        ((arguments['domainId'] as String?)?.trim().isNotEmpty == true
            ? (arguments['domainId'] as String).trim()
            : (arguments['__domainId'] as String?)?.trim()) ??
        '';
    final domainPolicy = await _loadDomainRetrievalPolicy(domainId);
    final maxSearchPlans = domainPolicy.maxSearchPlans > 0
        ? domainPolicy.maxSearchPlans
        : 2;
    final allPlans = _normalizeSearchPlans(searchPlans)
        .take(maxSearchPlans)
        .map(
          (plan) => _withDomainPolicySearchPlanHints(
            searchPlan: plan,
            domainPolicy: domainPolicy,
          ),
        )
        .toList(growable: false);
    final allQueries = allPlans
        .map((plan) => (plan['query'] as String?)?.trim() ?? '')
        .where((query) => query.isNotEmpty)
        .toList(growable: false);
    final labels = allPlans
        .map((plan) => (plan['label'] as String?)?.trim() ?? '')
        .where((label) => label.isNotEmpty)
        .toList(growable: false);
    final dimensions = allPlans
        .map((plan) => (plan['dimension'] as String?)?.trim() ?? '')
        .where((dimension) => dimension.isNotEmpty)
        .toSet()
        .toList(growable: false);
    final futures = allPlans
        .map((plan) {
          final singleArgs = Map<String, dynamic>.from(arguments)
            ..['query'] = (plan['query'] as String?)?.trim() ?? ''
            ..['searchPlanId'] = (plan['id'] as String?)?.trim() ?? ''
            ..['searchPlanLabel'] = (plan['label'] as String?)?.trim() ?? ''
            ..['dimension'] = (plan['dimension'] as String?)?.trim() ?? ''
            ..['entityRefs'] = _stringList(plan['entityRefs'])
            ..['negativeKeywords'] = _stringList(plan['negativeKeywords'])
            ..['timeScope'] = (plan['timeScope'] as String?)?.trim() ?? ''
            ..['timeRangeStart'] =
                (plan['timeRangeStart'] as String?)?.trim() ?? ''
            ..['timeRangeEnd'] = (plan['timeRangeEnd'] as String?)?.trim() ?? ''
            ..['timePoint'] = (plan['timePoint'] as String?)?.trim() ?? ''
            ..['timezone'] = (plan['timezone'] as String?)?.trim() ?? ''
            ..remove('queryVariants')
            ..remove('searchPlans');
          return execute(AssistantToolArguments.fromJson(singleArgs));
        })
        .toList(growable: false);
    final results = await Future.wait(futures, eagerError: false);
    final mergedCandidates = <Map<String, dynamic>>[];
    final coveredDimensions = <String>{};
    String bestSummary = '';
    double bestQuality = 0.0;
    String bestProvider = '';
    var anySuccess = false;
    Map<String, dynamic> aggregateTimeConstraint = const <String, dynamic>{};
    List<String> aggregateAuthorityDomains = const <String>[];
    _TemporalGuardAssessment aggregateTemporalGuard =
        const _TemporalGuardAssessment(searchQuery: '');

    for (var i = 0; i < results.length; i++) {
      final r = results[i];
      final plan = i < allPlans.length
          ? allPlans[i]
          : const <String, dynamic>{};
      if (r.success) anySuccess = true;
      final data = r.data ?? const <String, dynamic>{};
      if (aggregateTimeConstraint.isEmpty && data['timeConstraint'] is Map) {
        aggregateTimeConstraint = (data['timeConstraint'] as Map)
            .cast<String, dynamic>();
      }
      if (aggregateAuthorityDomains.isEmpty &&
          data['authorityDomains'] is List) {
        aggregateAuthorityDomains = (data['authorityDomains'] as List)
            .whereType<String>()
            .map((item) => item.trim().toLowerCase())
            .where((item) => item.isNotEmpty)
            .toList(growable: false);
      }
      final temporalGuard = _temporalGuardFromData(data);
      if (temporalGuard.blocked ||
          (aggregateTemporalGuard.searchQuery.isEmpty &&
              (temporalGuard.applied ||
                  temporalGuard.searchQuery.isNotEmpty))) {
        aggregateTemporalGuard = temporalGuard;
      }
      final refs =
          (data['references'] as List?)
              ?.whereType<Map>()
              .map((e) => e.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      final filteredRefs = _applyTaskFilters(refs, searchPlan: plan);
      if (filteredRefs.isNotEmpty) {
        final dimension =
            (plan['dimension'] as String?)?.trim() ??
            (plan['label'] as String?)?.trim() ??
            '';
        if (dimension.isNotEmpty) {
          coveredDimensions.add(dimension);
        }
      }
      for (final ref in filteredRefs) {
        mergedCandidates.add(<String, dynamic>{
          ...ref,
          'rerankScore': _multiQueryReferenceScore(
            ref,
            searchPlan: plan,
            requestedDimensions: dimensions,
          ),
        });
      }
      final quality = (data['qualityScore'] as num?)?.toDouble() ?? 0.0;
      if (quality > bestQuality) {
        bestQuality = quality;
        bestSummary = (data['summary'] as String?)?.trim() ?? '';
        bestProvider = (data['provider'] as String?)?.trim() ?? '';
      }
    }

    if (!anySuccess) {
      return results.first;
    }

    final mergedRefs = _dedupeAndSortMergedReferences(mergedCandidates);
    final missingDimensions = dimensions
        .where((item) => item.isNotEmpty && !coveredDimensions.contains(item))
        .toList(growable: false);
    final rerankedQuality = _mergedQualityScore(mergedRefs);
    final mergedTimeConstraint =
        _timeConstraintFromJson(aggregateTimeConstraint) ??
        _SearchTimeConstraint(
          scope: 'unspecified',
          start: DateTime.now().subtract(const Duration(days: 30)),
          end: DateTime.now(),
          freshnessHoursMax: 72,
          referenceNow: DateTime.now(),
          temporalMode: 'passive',
        );
    if (aggregateTemporalGuard.searchQuery.isEmpty && allQueries.isNotEmpty) {
      aggregateTemporalGuard = _TemporalGuardAssessment(
        searchQuery: allQueries.first,
      );
    }
    final evidenceStats = _buildEvidenceStats(
      references: mergedRefs,
      authorityDomains: aggregateAuthorityDomains,
      timeConstraint: mergedTimeConstraint,
      temporalGuard: aggregateTemporalGuard,
    );
    final effectiveQuality = rerankedQuality > 0
        ? rerankedQuality
        : ((evidenceStats['qualityScore'] as num?)?.toDouble() ?? bestQuality);
    final effectiveSummary = _buildMultiQuerySummary(
      labels: labels,
      coveredDimensions: coveredDimensions.toList(growable: false),
      missingDimensions: missingDimensions,
      referenceCount: mergedRefs.length,
      fallbackSummary: bestSummary,
    );

    return AssistantToolResult(
      success: true,
      message:
          '并行检索完成（${labels.isNotEmpty ? labels.length : allQueries.length} 个方向），找到 ${mergedRefs.length} 条参考资料。',
      data: AssistantToolResultData(<String, Object?>{
        'provider': bestProvider,
        'summary': effectiveSummary,
        'references': mergedRefs.take(10).toList(growable: false),
        'timeConstraint': aggregateTimeConstraint,
        'temporalGuard': aggregateTemporalGuard.toJson(),
        'authorityDomains': aggregateAuthorityDomains,
        'queryCount': allQueries.length,
        'queryLabels': labels,
        'coveredDimensions': coveredDimensions.isNotEmpty
            ? coveredDimensions.toList(growable: false)
            : labels,
        'missingDimensions': missingDimensions,
        'searchPlans': allPlans,
        'referenceCount': mergedRefs.length,
        'totalReferences': mergedRefs.length,
        'rerankStats': <String, dynamic>{
          'candidateCount': mergedCandidates.length,
          'returnedCount': mergedRefs.length,
        },
        ...evidenceStats,
        'qualityScore': effectiveQuality,
        'retrievalInsufficient':
            evidenceStats['retrievalInsufficient'] == true ||
            missingDimensions.isNotEmpty,
        'message': '多路检索完成。',
      }),
    );
  }

  List<Map<String, dynamic>> _applyTaskFilters(
    List<Map<String, dynamic>> references, {
    Map<String, dynamic>? task,
    Map<String, dynamic>? searchPlan,
  }) {
    final effectivePlan = task ?? searchPlan ?? const <String, dynamic>{};
    final anchors = _stringList(
      effectivePlan['entityRefs'],
    ).map((item) => item.toLowerCase()).toList(growable: false);
    final negatives = _stringList(
      effectivePlan['negativeKeywords'],
    ).map((item) => item.toLowerCase()).toList(growable: false);
    final minAcceptedRelevanceScore =
        (effectivePlan['minAcceptedRelevanceScore'] as num?)?.toDouble() ?? 0.0;
    return references
        .where((ref) {
          final haystack =
              ('${ref['title'] ?? ''} ${ref['snippet'] ?? ''} ${ref['url'] ?? ''}')
                  .toLowerCase();
          if (anchors.isNotEmpty && !anchors.any(haystack.contains)) {
            return false;
          }
          if (negatives.isNotEmpty && negatives.any(haystack.contains)) {
            return false;
          }
          final relevanceScore = (ref['relevanceScore'] as num?)?.toDouble();
          if (minAcceptedRelevanceScore > 0 &&
              relevanceScore != null &&
              relevanceScore < minAcceptedRelevanceScore) {
            return false;
          }
          return true;
        })
        .toList(growable: false);
  }

  List<Map<String, dynamic>> _dedupeAndSortMergedReferences(
    List<Map<String, dynamic>> references,
  ) {
    final byUrl = <String, Map<String, dynamic>>{};
    for (final ref in references) {
      final url = (ref['url'] as String?)?.trim() ?? '';
      if (url.isEmpty) continue;
      final existing = byUrl[url];
      if (existing == null ||
          ((ref['rerankScore'] as num?)?.toDouble() ?? 0.0) >
              ((existing['rerankScore'] as num?)?.toDouble() ?? 0.0)) {
        byUrl[url] = ref;
      }
    }
    final deduped = byUrl.values.toList(growable: false);
    deduped.sort((a, b) {
      final rerankDelta =
          (((b['rerankScore'] as num?)?.toDouble() ?? 0.0) * 1000).round() -
          (((a['rerankScore'] as num?)?.toDouble() ?? 0.0) * 1000).round();
      if (rerankDelta != 0) return rerankDelta;
      final sourceSemanticDelta =
          (((b['sourceSemanticScore'] as num?)?.toDouble() ?? 0.0) * 1000)
              .round() -
          (((a['sourceSemanticScore'] as num?)?.toDouble() ?? 0.0) * 1000)
              .round();
      if (sourceSemanticDelta != 0) return sourceSemanticDelta;
      final authorityDelta =
          (((b['authorityScore'] as num?)?.toDouble() ?? 0.0) * 1000).round() -
          (((a['authorityScore'] as num?)?.toDouble() ?? 0.0) * 1000).round();
      if (authorityDelta != 0) return authorityDelta;
      final relevanceDelta =
          (((b['relevanceScore'] as num?)?.toDouble() ?? 0.0) * 1000).round() -
          (((a['relevanceScore'] as num?)?.toDouble() ?? 0.0) * 1000).round();
      if (relevanceDelta != 0) return relevanceDelta;
      return ((a['url'] as String?) ?? '').compareTo(
        (b['url'] as String?) ?? '',
      );
    });
    return deduped;
  }

  double _multiQueryReferenceScore(
    Map<String, dynamic> reference, {
    Map<String, dynamic>? task,
    Map<String, dynamic>? searchPlan,
    required List<String> requestedDimensions,
  }) {
    final effectivePlan = task ?? searchPlan ?? const <String, dynamic>{};
    final relevance = (reference['relevanceScore'] as num?)?.toDouble() ?? 0.0;
    final authority = (reference['authorityScore'] as num?)?.toDouble() ?? 0.0;
    final sourceSemantic =
        (reference['sourceSemanticScore'] as num?)?.toDouble() ??
        _estimateSourceSemanticScore(reference);
    final freshnessHours =
        (reference['freshnessHours'] as num?)?.toDouble() ?? 0.0;
    final freshnessScore = _freshnessScoreFromHours(freshnessHours);
    final dimension = (reference['dimension'] as String?)?.trim() ?? '';
    final dimensionBonus =
        requestedDimensions.isEmpty ||
            (dimension.isNotEmpty && requestedDimensions.contains(dimension))
        ? 1.0
        : 0.6;
    final anchorBonus = _stringList(effectivePlan['entityRefs']).isEmpty
        ? 1.0
        : 1.08;
    return (relevance * 0.38 +
            authority * 0.18 +
            freshnessScore * 0.16 +
            sourceSemantic * 0.2 +
            dimensionBonus * 0.08) *
        anchorBonus;
  }

  double _freshnessScoreFromHours(double freshnessHours) {
    if (freshnessHours <= 0) return 1.0;
    if (freshnessHours <= 24) return 1.0;
    if (freshnessHours <= 72) return 0.86;
    if (freshnessHours <= 168) return 0.72;
    if (freshnessHours <= 720) return 0.56;
    return 0.38;
  }

  double _mergedQualityScore(List<Map<String, dynamic>> references) {
    if (references.isEmpty) return 0.0;
    final top = references.take(3).toList(growable: false);
    return top
            .map((item) => (item['rerankScore'] as num?)?.toDouble() ?? 0.0)
            .reduce((a, b) => a + b) /
        top.length;
  }

  String _buildMultiQuerySummary({
    required List<String> labels,
    required List<String> coveredDimensions,
    required List<String> missingDimensions,
    required int referenceCount,
    required String fallbackSummary,
  }) {
    if (coveredDimensions.isNotEmpty && missingDimensions.isEmpty) {
      final joined = coveredDimensions.join('、');
      return '已按 $joined 这些方向交叉核对，当前收拢到 $referenceCount 条高相关资料。';
    }
    if (coveredDimensions.isNotEmpty && missingDimensions.isNotEmpty) {
      return '已确认 ${coveredDimensions.join("、")}，还缺 ${missingDimensions.join("、")}，先保留最相关的 $referenceCount 条资料。';
    }
    if (labels.isNotEmpty) {
      return '已按 ${labels.join("、")} 并行检索，当前保留 $referenceCount 条相关资料。';
    }
    return fallbackSummary;
  }

  List<Map<String, dynamic>> _normalizeSearchPlans(Object? raw) {
    final rawItems = raw is List ? raw : const <Object?>[];
    final normalized = <Map<String, dynamic>>[];
    final seen = <String>{};
    for (final item in rawItems) {
      final rawPlan = item is Map
          ? item.cast<String, dynamic>()
          : <String, dynamic>{'query': item.toString()};
      final query = _firstNonEmpty(<String>[
        _stringValue(rawPlan['query']),
        _stringValue(rawPlan['q']),
        _stringValue(rawPlan['text']),
      ]);
      if (query.isEmpty || !seen.add(query)) continue;
      final dimension = _firstNonEmpty(<String>[
        _stringValue(rawPlan['dimension']),
        _stringValue(rawPlan['dimensionCode']),
      ]);
      final label = _firstNonEmpty(<String>[
        _stringValue(rawPlan['label']),
        _stringValue(rawPlan['title']),
      ]);
      final normalizedPlan = Map<String, dynamic>.from(rawPlan);
      normalizedPlan['id'] = _stringValue(rawPlan['id']).isNotEmpty
          ? _stringValue(rawPlan['id'])
          : _normalizeSearchPlanId(
              query,
              preferred: dimension.isNotEmpty ? dimension : label,
            );
      normalizedPlan['query'] = query;
      if (dimension.isNotEmpty) normalizedPlan['dimension'] = dimension;
      if (label.isNotEmpty) normalizedPlan['label'] = label;
      normalized.add(normalizedPlan);
    }
    return normalized;
  }

  List<Map<String, dynamic>> _searchPlansFromSeeds(
    String mainQuery,
    List<String> variants,
  ) {
    final plans = <Map<String, dynamic>>[];
    final seen = <String>{};

    void addPlan(String query) {
      final normalized = query.trim();
      if (normalized.isEmpty || !seen.add(normalized)) return;
      plans.add(<String, dynamic>{'query': normalized, 'label': normalized});
    }

    if (mainQuery.isNotEmpty) {
      addPlan(mainQuery);
    }
    for (final variant in variants) {
      addPlan(variant);
    }
    return plans;
  }

  Map<String, dynamic> _resolveSingleSearchPlan({
    required Map<String, dynamic> arguments,
    required String normalizedQuery,
    required List<Map<String, dynamic>> normalizedPlans,
  }) {
    if (normalizedPlans.length == 1) {
      return normalizedPlans.first;
    }
    final explicitId = (arguments['searchPlanId'] as String?)?.trim() ?? '';
    final explicitLabel =
        (arguments['searchPlanLabel'] as String?)?.trim() ?? '';
    final explicitDimension = (arguments['dimension'] as String?)?.trim() ?? '';
    return <String, dynamic>{
      'id': explicitId.isNotEmpty
          ? explicitId
          : _normalizeSearchPlanId(
              normalizedQuery,
              preferred: explicitDimension.isNotEmpty
                  ? explicitDimension
                  : explicitLabel,
            ),
      'label': explicitLabel.isNotEmpty ? explicitLabel : normalizedQuery,
      if (explicitDimension.isNotEmpty) 'dimension': explicitDimension,
      if (_stringList(arguments['entityRefs']).isNotEmpty)
        'entityRefs': _stringList(arguments['entityRefs']),
      if (_stringList(arguments['negativeKeywords']).isNotEmpty)
        'negativeKeywords': _stringList(arguments['negativeKeywords']),
      if ((arguments['answerShape'] as String?)?.trim().isNotEmpty == true)
        'answerShape': (arguments['answerShape'] as String).trim(),
      if ((arguments['timeScope'] as String?)?.trim().isNotEmpty == true)
        'timeScope': (arguments['timeScope'] as String).trim(),
      if ((arguments['timeRangeStart'] as String?)?.trim().isNotEmpty == true)
        'timeRangeStart': (arguments['timeRangeStart'] as String).trim(),
      if ((arguments['timeRangeEnd'] as String?)?.trim().isNotEmpty == true)
        'timeRangeEnd': (arguments['timeRangeEnd'] as String).trim(),
      if ((arguments['timePoint'] as String?)?.trim().isNotEmpty == true)
        'timePoint': (arguments['timePoint'] as String).trim(),
      if ((arguments['timezone'] as String?)?.trim().isNotEmpty == true)
        'timezone': (arguments['timezone'] as String).trim(),
      if (arguments['resolvedGeoScope'] is Map)
        'resolvedGeoScope': (arguments['resolvedGeoScope'] as Map)
            .cast<String, dynamic>(),
    };
  }

  Map<String, dynamic> _withDomainPolicySearchPlanHints({
    required Map<String, dynamic> searchPlan,
    required _DomainRetrievalPolicy domainPolicy,
  }) {
    if (domainPolicy.negativeKeywords.isEmpty &&
        domainPolicy.minAcceptedRelevanceScore <= 0) {
      return searchPlan;
    }
    final mergedNegativeKeywords = <String>{
      ..._stringList(
        searchPlan['negativeKeywords'],
      ).map((item) => item.trim()).where((item) => item.isNotEmpty),
      ...domainPolicy.negativeKeywords,
    }.toList(growable: false);
    return <String, dynamic>{
      ...searchPlan,
      if (mergedNegativeKeywords.isNotEmpty)
        'negativeKeywords': mergedNegativeKeywords,
      if (domainPolicy.minAcceptedRelevanceScore > 0)
        'minAcceptedRelevanceScore': domainPolicy.minAcceptedRelevanceScore,
    };
  }

  Map<String, dynamic> _withResolvedTemporalArguments({
    required Map<String, dynamic> arguments,
    Map<String, dynamic>? searchPlan,
    required String query,
  }) {
    final effectivePlan = searchPlan ?? const <String, dynamic>{};
    final queryNormalization =
        (arguments['queryNormalization'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final mergedArguments = Map<String, dynamic>.from(arguments)
      ..['query'] = query;
    final mergedQueryNormalization = <String, dynamic>{
      ...queryNormalization,
      'normalizedQuery': query,
      'referenceNowIso': _firstNonEmpty(<String>[
        _stringValue(arguments['referenceNowIso']),
        _stringValue(queryNormalization['referenceNowIso']),
      ]),
      'timezone': _firstNonEmpty(<String>[
        _stringValue(effectivePlan['timezone']),
        _stringValue(arguments['timezone']),
        _stringValue(queryNormalization['timezone']),
      ]),
      'timeScope': _firstNonEmpty(<String>[
        _stringValue(effectivePlan['timeScope']),
        _stringValue(arguments['timeScope']),
        _stringValue(queryNormalization['timeScope']),
      ]),
      'timeRangeStart': _firstNonEmpty(<String>[
        _stringValue(effectivePlan['timeRangeStart']),
        _stringValue(arguments['timeRangeStart']),
        _stringValue(queryNormalization['timeRangeStart']),
      ]),
      'timeRangeEnd': _firstNonEmpty(<String>[
        _stringValue(effectivePlan['timeRangeEnd']),
        _stringValue(arguments['timeRangeEnd']),
        _stringValue(queryNormalization['timeRangeEnd']),
      ]),
      'timePoint': _firstNonEmpty(<String>[
        _stringValue(effectivePlan['timePoint']),
        _stringValue(arguments['timePoint']),
        _stringValue(queryNormalization['timePoint']),
      ]),
    };
    mergedArguments['queryNormalization'] = mergedQueryNormalization;
    mergedArguments['referenceNowIso'] =
        mergedQueryNormalization['referenceNowIso'];
    mergedArguments['timezone'] = mergedQueryNormalization['timezone'];
    mergedArguments['timeScope'] = mergedQueryNormalization['timeScope'];
    mergedArguments['timeRangeStart'] =
        mergedQueryNormalization['timeRangeStart'];
    mergedArguments['timeRangeEnd'] = mergedQueryNormalization['timeRangeEnd'];
    mergedArguments['timePoint'] = mergedQueryNormalization['timePoint'];
    return mergedArguments;
  }

  Map<String, dynamic> _withResolvedGeoArguments({
    required Map<String, dynamic> arguments,
    Map<String, dynamic>? searchPlan,
  }) {
    final effectivePlan = searchPlan ?? const <String, dynamic>{};
    final resolvedGeoScope = _resolvedGeoScopeFromArguments(
      arguments: arguments,
      searchPlan: effectivePlan,
    );
    if (!hasResolvedGeoScope(resolvedGeoScope)) {
      return arguments;
    }
    final mergedArguments = Map<String, dynamic>.from(arguments);
    final queryNormalization =
        (arguments['queryNormalization'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    if (queryNormalization.isNotEmpty) {
      mergedArguments['queryNormalization'] = <String, dynamic>{
        ...queryNormalization,
      };
    }
    mergedArguments['resolvedGeoScope'] = resolvedGeoScope.toJson();
    return mergedArguments;
  }

  Map<String, dynamic> _withResolvedGeoSearchPlan({
    required Map<String, dynamic> searchPlan,
    required Map<String, dynamic> arguments,
  }) {
    final resolvedGeoScope = _resolvedGeoScopeFromArguments(
      arguments: arguments,
      searchPlan: searchPlan,
    );
    if (!hasResolvedGeoScope(resolvedGeoScope)) {
      return searchPlan;
    }
    return <String, dynamic>{
      ...searchPlan,
      'resolvedGeoScope': resolvedGeoScope.toJson(),
    };
  }

  ResolvedGeoScope _resolvedGeoScopeFromArguments({
    required Map<String, dynamic> arguments,
    required Map<String, dynamic> searchPlan,
  }) {
    final rawScope =
        (searchPlan['resolvedGeoScope'] as Map?)?.cast<String, dynamic>() ??
        (arguments['resolvedGeoScope'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    if (rawScope.isEmpty) {
      return const ResolvedGeoScope();
    }
    return ResolvedGeoScope.fromJson(rawScope);
  }

  List<Map<String, dynamic>> _decorateReferences({
    required List<Map<String, dynamic>> references,
    required String query,
    required List<String> authorityDomains,
    required _SearchTimeConstraint timeConstraint,
    Map<String, dynamic>? searchPlan,
    required String retrievedAt,
  }) {
    final effectivePlan = searchPlan ?? const <String, dynamic>{};
    final normalizedRefs = references
        .map(SafeReferenceNormalizer.normalize)
        .whereType<Map<String, dynamic>>()
        .toList(growable: false);
    final decorated = normalizedRefs
        .map((ref) {
          final enrichedRef = _enrichReferenceTimestamps(
            reference: ref,
            retrievedAt: retrievedAt,
            timeConstraint: timeConstraint,
          );
          final url = (enrichedRef['url'] as String?)?.trim() ?? '';
          final host = Uri.tryParse(url)?.host.toLowerCase().trim() ?? '';
          final source =
              (enrichedRef['source'] as String?)?.trim().isNotEmpty == true
              ? (enrichedRef['source'] as String).trim()
              : host;
          final sourceTier =
              (enrichedRef['sourceTier'] as String?)?.trim().isNotEmpty == true
              ? (enrichedRef['sourceTier'] as String).trim()
              : _resolveSourceTier(
                  host: host,
                  authorityDomains: authorityDomains,
                );
          final freshnessSignal = _resolveReferenceFreshnessSignal(
            enrichedRef,
            timeConstraint: timeConstraint,
          );
          final freshnessHours =
              _intValue(enrichedRef['freshnessHours']) ?? freshnessSignal.hours;
          final authorityScore =
              (enrichedRef['authorityScore'] as num?)?.toDouble() ??
              _estimateAuthorityScore(
                sourceTier: sourceTier,
                host: host,
                authorityDomains: authorityDomains,
              );
          final relevanceScore =
              (enrichedRef['relevanceScore'] as num?)?.toDouble() ??
              _estimateReferenceRelevance(
                query: query,
                reference: enrichedRef,
                searchPlan: effectivePlan,
              );
          final sourceSemanticScore =
              (enrichedRef['sourceSemanticScore'] as num?)?.toDouble() ??
              _estimateSourceSemanticScore(enrichedRef);
          final resultRankScore = _singleQueryReferenceScore(
            relevanceScore: relevanceScore,
            authorityScore: authorityScore,
            freshnessScore: _freshnessScore(
              freshness: freshnessSignal,
              timeConstraint: timeConstraint,
            ),
            sourceSemanticScore: sourceSemanticScore,
          );
          return <String, dynamic>{
            ...enrichedRef,
            'source': source,
            'sourceHost': host,
            'sourceTier': sourceTier,
            'freshnessHours': freshnessHours,
            'freshnessKnown':
                enrichedRef['freshnessKnown'] == true || freshnessSignal.known,
            'freshnessSatisfied':
                enrichedRef['freshnessSatisfied'] == true ||
                freshnessSignal.satisfied,
            'authorityScore': authorityScore,
            'relevanceScore': relevanceScore,
            'sourceSemanticScore': sourceSemanticScore,
            'resultRankScore': resultRankScore,
            'searchPlanId': _stringValue(effectivePlan['id']),
            'searchPlanLabel': _stringValue(effectivePlan['label']),
            'dimension': _stringValue(effectivePlan['dimension']).isNotEmpty
                ? _stringValue(effectivePlan['dimension'])
                : _stringValue(effectivePlan['label']),
            if (_stringList(effectivePlan['entityRefs']).isNotEmpty)
              'entityRefs': _stringList(effectivePlan['entityRefs']),
            if (_stringList(effectivePlan['negativeKeywords']).isNotEmpty)
              'negativeKeywords': _stringList(
                effectivePlan['negativeKeywords'],
              ),
            'retrievedAt':
                (enrichedRef['retrievedAt'] as String?)?.trim().isNotEmpty ==
                    true
                ? (enrichedRef['retrievedAt'] as String).trim()
                : retrievedAt,
          };
        })
        .where((item) => (item['url'] as String?)?.trim().isNotEmpty == true)
        .toList(growable: true);
    decorated.sort(_referenceRankComparator);
    return decorated.toList(growable: false);
  }

  String _resolveSourceTier({
    required String host,
    required List<String> authorityDomains,
  }) {
    if (host.isEmpty) return 'web';
    for (final authority in authorityDomains) {
      if (host == authority || host.endsWith('.$authority')) {
        return 'authority';
      }
    }
    return 'web';
  }

  double _estimateAuthorityScore({
    required String sourceTier,
    required String host,
    required List<String> authorityDomains,
  }) {
    switch (sourceTier) {
      case 'authority':
        return 1.0;
      default:
        for (final authority in authorityDomains) {
          if (host == authority || host.endsWith('.$authority')) return 1.0;
        }
        return 0.45;
    }
  }

  double _estimateReferenceRelevance({
    required String query,
    required Map<String, dynamic> reference,
    required Map<String, dynamic> searchPlan,
  }) {
    final tokens = query
        .toLowerCase()
        .split(RegExp(r'[\s,，。；;:/]+'))
        .map((item) => item.trim())
        .where((item) => item.length >= 2)
        .toSet();
    final anchorTokens = _stringList(searchPlan['entityRefs'])
        .map((item) => item.toLowerCase())
        .where((item) => item.length >= 2)
        .toSet();
    final negativeTokens = _stringList(searchPlan['negativeKeywords'])
        .map((item) => item.toLowerCase())
        .where((item) => item.length >= 2)
        .toSet();
    final effectiveTokens = <String>{...tokens, ...anchorTokens};
    if (effectiveTokens.isEmpty) return 0.6;
    final haystack =
        ('${reference['title'] ?? ''} ${reference['snippet'] ?? ''} ${reference['url'] ?? ''}')
            .toLowerCase();
    var hits = 0;
    for (final token in effectiveTokens) {
      if (haystack.contains(token)) hits += 1;
    }
    final negativeHit = negativeTokens.any(haystack.contains);
    final baseScore = (hits / effectiveTokens.length)
        .clamp(0.2, 1.0)
        .toDouble();
    if (negativeHit) {
      return (baseScore * 0.35).clamp(0.1, 0.7).toDouble();
    }
    if (anchorTokens.isNotEmpty && anchorTokens.any(haystack.contains)) {
      return (baseScore + 0.12).clamp(0.2, 1.0).toDouble();
    }
    return baseScore;
  }

  Map<String, dynamic> _enrichReferenceTimestamps({
    required Map<String, dynamic> reference,
    required String retrievedAt,
    required _SearchTimeConstraint timeConstraint,
  }) {
    final enriched = Map<String, dynamic>.from(reference);
    final explicitObserved = _stringValue(reference['observedAt']);
    final explicitPublished = _stringValue(reference['publishedAt']);
    final providerDate = _firstNonEmpty(<String>[
      _stringValue(reference['date']),
      _stringValue(reference['published']),
      _stringValue(reference['published_at']),
      _stringValue(reference['timestamp']),
      _stringValue(reference['time']),
    ]);
    final derivedPublished = _firstNonEmpty(<String>[
      explicitPublished,
      explicitObserved,
      providerDate,
    ]);
    final derivedObserved = _firstNonEmpty(<String>[
      explicitObserved,
      explicitPublished,
      providerDate,
    ]);
    if (derivedPublished.isNotEmpty) {
      enriched['publishedAt'] = derivedPublished;
    }
    if (derivedObserved.isNotEmpty) {
      enriched['observedAt'] = derivedObserved;
    }
    if ((enriched['retrievedAt'] as String?)?.trim().isNotEmpty != true &&
        retrievedAt.trim().isNotEmpty) {
      enriched['retrievedAt'] = retrievedAt.trim();
    }
    return enriched;
  }

  double _estimateSourceSemanticScore(Map<String, dynamic> reference) {
    final url = _stringValue(reference['url']).toLowerCase();
    final path = Uri.tryParse(url)?.path.toLowerCase() ?? url;
    final haystack =
        '${_stringValue(reference['title'])} ${_stringValue(reference['snippet'])} $path'
            .toLowerCase();
    var score = 0.5;
    if (path.endsWith('.pdf')) {
      score -= 0.45;
    }
    const positiveTokens = <String>[
      'news',
      'analysis',
      'recap',
      'summary',
      'live',
      'update',
      'insight',
      'coverage',
      'breaking',
      '快讯',
      '解读',
      '综述',
      '收评',
      '午评',
      '盘后',
      '盘前',
      '报道',
      '总结',
    ];
    const negativeTokens = <String>[
      '.pdf',
      'announcement',
      'notice',
      'prospectus',
      'offering',
      'appendix',
      'annex',
      '招股书',
      '说明书',
      '公告',
      '附录',
      '章程',
    ];
    if (positiveTokens.any(haystack.contains)) {
      score += 0.24;
    }
    if (negativeTokens.any(haystack.contains)) {
      score -= 0.32;
    }
    return score.clamp(0.05, 1.0).toDouble();
  }

  double _singleQueryReferenceScore({
    required double relevanceScore,
    required double authorityScore,
    required double freshnessScore,
    required double sourceSemanticScore,
  }) {
    return (relevanceScore * 0.4 +
            authorityScore * 0.18 +
            freshnessScore * 0.18 +
            sourceSemanticScore * 0.24)
        .clamp(0.0, 1.0)
        .toDouble();
  }

  int _referenceRankComparator(Map<String, dynamic> a, Map<String, dynamic> b) {
    final rankDelta =
        (((b['resultRankScore'] as num?)?.toDouble() ?? 0.0) * 1000).round() -
        (((a['resultRankScore'] as num?)?.toDouble() ?? 0.0) * 1000).round();
    if (rankDelta != 0) {
      return rankDelta;
    }
    final authorityDelta =
        (((b['authorityScore'] as num?)?.toDouble() ?? 0.0) * 1000).round() -
        (((a['authorityScore'] as num?)?.toDouble() ?? 0.0) * 1000).round();
    if (authorityDelta != 0) {
      return authorityDelta;
    }
    final relevanceDelta =
        (((b['relevanceScore'] as num?)?.toDouble() ?? 0.0) * 1000).round() -
        (((a['relevanceScore'] as num?)?.toDouble() ?? 0.0) * 1000).round();
    if (relevanceDelta != 0) {
      return relevanceDelta;
    }
    return _stringValue(a['url']).compareTo(_stringValue(b['url']));
  }

  String _normalizeSearchPlanId(String query, {String preferred = ''}) {
    final base = preferred.trim().isNotEmpty ? preferred.trim() : query.trim();
    final normalized = base
        .toLowerCase()
        .replaceAll(RegExp(r'[^\w\u4e00-\u9fa5]+'), '_')
        .replaceAll(RegExp(r'_+'), '_')
        .replaceAll(RegExp(r'^_|_$'), '');
    return normalized.isNotEmpty ? normalized : 'search_plan';
  }

  int? _intValue(Object? value) {
    if (value is num) return value.toInt();
    return int.tryParse(value?.toString() ?? '');
  }

  String _firstNonEmpty(List<String> candidates) {
    for (final candidate in candidates) {
      if (candidate.trim().isNotEmpty) {
        return candidate.trim();
      }
    }
    return '';
  }

  String _stringValue(Object? value) => value?.toString().trim() ?? '';

  List<String> _stringList(Object? value) {
    if (value is List) {
      return value
          .map((item) => item.toString().trim())
          .where((item) => item.isNotEmpty)
          .toList(growable: false);
    }
    return const <String>[];
  }

  String _insufficientRetrievalMessage({
    required _TemporalGuardAssessment temporalGuard,
    required Map<String, dynamic> evidenceStats,
    required _SearchTimeConstraint timeConstraint,
  }) {
    return '';
  }

  _TemporalGuardAssessment _temporalGuardFromData(Map<String, dynamic> data) {
    final raw = (data['temporalGuard'] as Map?)?.cast<String, dynamic>();
    if (raw == null || raw.isEmpty) {
      return const _TemporalGuardAssessment(searchQuery: '');
    }
    return _TemporalGuardAssessment(
      searchQuery: (raw['searchQuery'] as String?)?.trim() ?? '',
      applied: raw['applied'] == true,
      blocked: raw['blocked'] == true,
      reason: (raw['reason'] as String?)?.trim() ?? '',
      conflictingDateTokens: _stringList(raw['conflictingDateTokens']),
    );
  }

  _SearchTimeConstraint? _timeConstraintFromJson(Map<String, dynamic> raw) {
    if (raw.isEmpty) {
      return null;
    }
    final start = DateTime.tryParse(
      (raw['timeRangeStart'] as String?)?.trim() ?? '',
    );
    final end = DateTime.tryParse(
      (raw['timeRangeEnd'] as String?)?.trim() ?? '',
    );
    if (start == null || end == null) {
      return null;
    }
    return _SearchTimeConstraint(
      scope: (raw['scope'] as String?)?.trim() ?? 'unspecified',
      start: start,
      end: end,
      freshnessHoursMax: (raw['freshnessHoursMax'] as num?)?.toInt() ?? 72,
      referenceNow:
          DateTime.tryParse(
            (raw['referenceNowIso'] as String?)?.trim() ?? '',
          ) ??
          end,
      temporalMode: (raw['temporalMode'] as String?)?.trim().isNotEmpty == true
          ? (raw['temporalMode'] as String).trim()
          : 'passive',
    );
  }

  Future<_BackupSearchResult?> _tryFallbackSearch({
    required AssistantSearchProvider primaryProvider,
    required String query,
    required int count,
    required _WebSearchRuntimeConfig config,
  }) async {
    final candidates = _preferredProviderOrder(config);
    for (final candidate in candidates) {
      if (candidate == primaryProvider) continue;
      if (!_providerReady(candidate, config)) continue;
      try {
        final decoded = await _runProviderSearch(
          provider: candidate,
          query: query,
          count: count,
          config: config,
        );
        final summary = _summarizeProviderResult(
          provider: candidate,
          decoded: decoded,
        );
        if (summary.trim().isEmpty) continue;
        return _BackupSearchResult(
          providerLabel: candidate.name,
          summary: summary,
          raw: decoded,
        );
      } catch (_) {
        continue;
      }
    }
    return null;
  }
}

class _BackupSearchResult {
  const _BackupSearchResult({
    required this.providerLabel,
    required this.summary,
    required this.raw,
  });

  final String providerLabel;
  final String summary;
  final Object? raw;
}

class _WebSearchRuntimeConfig {
  const _WebSearchRuntimeConfig({
    required this.defaultProvider,
    required this.braveApiKey,
    required this.perplexityApiKey,
    required this.perplexityBaseUrl,
    required this.perplexityModel,
    required this.serpApiKey,
    required this.openclawBaseUrl,
    required this.openclawToken,
  });

  final String defaultProvider;
  final String braveApiKey;
  final String perplexityApiKey;
  final String perplexityBaseUrl;
  final String perplexityModel;
  final String serpApiKey;
  final String openclawBaseUrl;
  final String openclawToken;

  Map<String, dynamic> toDiagnostics({String selectedProvider = ''}) {
    return <String, dynamic>{
      'defaultProvider': defaultProvider,
      'selectedProvider': selectedProvider,
      'hasBraveKey': braveApiKey.isNotEmpty,
      'hasPerplexityKey': perplexityApiKey.isNotEmpty,
      'hasSerpApiKey': serpApiKey.isNotEmpty,
      'hasOpenClawBaseUrl': openclawBaseUrl.isNotEmpty,
      'perplexityBaseUrl': perplexityBaseUrl,
      'perplexityModel': perplexityModel,
    };
  }
}

class _PerplexityResolvedAuth {
  const _PerplexityResolvedAuth({
    required this.apiKey,
    required this.baseUrl,
    required this.model,
  });

  final String apiKey;
  final String baseUrl;
  final String model;

  _PerplexityResolvedAuth copyWith({
    String? apiKey,
    String? baseUrl,
    String? model,
  }) {
    return _PerplexityResolvedAuth(
      apiKey: apiKey ?? this.apiKey,
      baseUrl: baseUrl ?? this.baseUrl,
      model: model ?? this.model,
    );
  }
}

class _WebSearchProfile {
  const _WebSearchProfile({
    this.provider = '',
    this.braveApiKeyRaw = '',
    this.perplexityApiKeyRaw = '',
    this.openrouterApiKeyRaw = '',
    this.serpApiKeyRaw = '',
    this.perplexityBaseUrl = '',
    this.perplexityModel = '',
  });

  final String provider;
  final String braveApiKeyRaw;
  final String perplexityApiKeyRaw;
  final String openrouterApiKeyRaw;
  final String serpApiKeyRaw;
  final String perplexityBaseUrl;
  final String perplexityModel;

  bool get isNotEmpty =>
      provider.isNotEmpty ||
      braveApiKeyRaw.isNotEmpty ||
      perplexityApiKeyRaw.isNotEmpty ||
      openrouterApiKeyRaw.isNotEmpty ||
      serpApiKeyRaw.isNotEmpty ||
      perplexityBaseUrl.isNotEmpty ||
      perplexityModel.isNotEmpty;
}

class _SearchTimeConstraint {
  const _SearchTimeConstraint({
    required this.scope,
    required this.start,
    required this.end,
    required this.freshnessHoursMax,
    required this.referenceNow,
    this.temporalMode = 'passive',
  });

  final String scope;
  final DateTime start;
  final DateTime end;
  final int freshnessHoursMax;
  final DateTime referenceNow;
  final String temporalMode;

  bool get isRealtimeLike => temporalMode == 'realtime';

  bool get isHistoricalLike => temporalMode == 'historical';

  bool get freshnessGuardRequired =>
      isRealtimeLike && freshnessHoursMax > 0 && freshnessHoursMax < 24 * 30;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'scope': scope,
      'timeRangeStart': start.toIso8601String(),
      'timeRangeEnd': end.toIso8601String(),
      'freshnessHoursMax': freshnessHoursMax,
      'referenceNowIso': referenceNow.toIso8601String(),
      'temporalMode': temporalMode,
    };
  }
}

class _TemporalGuardAssessment {
  const _TemporalGuardAssessment({
    required this.searchQuery,
    this.applied = false,
    this.blocked = false,
    this.reason = '',
    this.conflictingDateTokens = const <String>[],
  });

  final String searchQuery;
  final bool applied;
  final bool blocked;
  final String reason;
  final List<String> conflictingDateTokens;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'searchQuery': searchQuery,
      'applied': applied,
      'blocked': blocked,
      'reason': reason,
      'conflictingDateTokens': conflictingDateTokens,
    };
  }
}

class _FreshnessSignal {
  const _FreshnessSignal({
    required this.hours,
    required this.known,
    required this.satisfied,
  });

  final int hours;
  final bool known;
  final bool satisfied;
}

class _ResolvedTimeRange {
  const _ResolvedTimeRange({required this.start, required this.end});

  final DateTime start;
  final DateTime end;
}

class _RetrievalTimeContract {
  const _RetrievalTimeContract({
    this.defaultScope = 'last_30d',
    this.defaultFreshnessHoursMax = 72,
    this.supportedScopes = const <String>[
      'latest',
      'today',
      'last_7d',
      'last_30d',
      'last_1y',
      'year_to_date',
      'year',
      'year_month',
      'year_month_day',
      'custom',
      'unspecified',
    ],
    this.windowHoursByScope = const <String, int>{
      'latest': 24,
      'last_7d': 24 * 7,
      'last_30d': 24 * 30,
      'last_1y': 24 * 365,
    },
    this.freshnessHoursMaxByScope = const <String, int>{
      'latest': 6,
      'today': 12,
      'last_7d': 72,
      'last_30d': 24 * 30,
      'last_1y': 24 * 365,
      'year_to_date': 24 * 180,
      'year': 24 * 365 * 5,
      'year_month': 24 * 365 * 3,
      'year_month_day': 24 * 365 * 2,
    },
  });

  final String defaultScope;
  final int defaultFreshnessHoursMax;
  final List<String> supportedScopes;
  final Map<String, int> windowHoursByScope;
  final Map<String, int> freshnessHoursMaxByScope;
}

class _DomainRetrievalPolicy {
  const _DomainRetrievalPolicy({
    this.defaultTimeScope = '',
    this.defaultFreshnessHoursMax,
    this.maxSearchPlans = 2,
    this.minAcceptedRelevanceScore = 0.0,
    this.allowedTimeScopes = const <String>[],
    this.authorityDomains = const <String>[],
    this.contextConstraints = const <String>[],
    this.negativeKeywords = const <String>[],
  });

  final String defaultTimeScope;
  final int? defaultFreshnessHoursMax;
  final int maxSearchPlans;
  final double minAcceptedRelevanceScore;
  final List<String> allowedTimeScopes;
  final List<String> authorityDomains;
  final List<String> contextConstraints;
  final List<String> negativeKeywords;
}

class _CalendarPointRange {
  const _CalendarPointRange({required this.scope, required this.range});

  final String scope;
  final _ResolvedTimeRange range;
}

class _CalendarPoint {
  const _CalendarPoint({this.year, this.month, this.day});

  final int? year;
  final int? month;
  final int? day;
}

class _ClassifiedSearchError {
  const _ClassifiedSearchError({
    required this.errorCode,
    required this.message,
  });

  final AssistantErrorCode errorCode;
  final String message;
}
