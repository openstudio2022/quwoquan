import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/personal_assistant/contracts/query_task_contract.dart';
import 'package:quwoquan_app/personal_assistant/retrieval/retrieval_broker.dart';
import 'package:path_provider/path_provider.dart';
import 'package:quwoquan_app/personal_assistant/observability/logging/app_log_models.dart';
import 'package:quwoquan_app/personal_assistant/observability/logging/app_log_service.dart';
import 'package:quwoquan_app/personal_assistant/observability/logging/app_run_interaction_collector.dart';
import 'package:quwoquan_app/personal_assistant/tools/search_cache.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_schema.dart';

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
       _defaultProvider = defaultProvider ?? AssistantSearchProvider.duckduckgo,
       _searchCache = searchCache ?? SearchResultCache(),
       _broker = broker;

  final String _braveApiKey;
  final String _perplexityApiKey;
  final String _serpApiKey;
  final String _openclawBaseUrl;
  final String _openclawToken;
  final AssistantSearchProvider _defaultProvider;
  final SearchResultCache _searchCache;
  final RetrievalBroker? _broker;
  static const Duration _networkTimeout = Duration(seconds: 8);

  /// Access to the search cache for external reset (e.g. new session).
  SearchResultCache get searchCache => _searchCache;

  @override
  String get name => 'web_search';

  @override
  String get description => 'Search web content for latest information.';

  @override
  Future<AssistantToolResult> execute(Map<String, dynamic> arguments) async {
    final broker = _broker;
    if (broker != null) {
      final result = await broker.search(
        RetrievalSearchRequest.fromToolArguments(arguments),
      );
      return result.toToolResult();
    }
    final rawQuery = (arguments['query'] as String?)?.trim() ?? '';
    final queryTasks = _normalizeQueryTasks(arguments['queryTasks']);
    final variants =
        (arguments['queryVariants'] as List?)
            ?.whereType<String>()
            .map((v) => v.trim())
            .where((v) => v.isNotEmpty)
            .toList(growable: false) ??
        const <String>[];
    if (queryTasks.length >= 2) {
      return _executeMultiQuery(arguments, queryTasks);
    }
    if (queryTasks.isEmpty && variants.isNotEmpty) {
      final variantTasks = _queryTasksFromSeeds(rawQuery, variants);
      if (variantTasks.length >= 2) {
        return _executeMultiQuery(arguments, variantTasks);
      }
    }
    final singleTaskQuery = queryTasks.length == 1
        ? ((queryTasks.first['query'] as String?)?.trim() ?? '')
        : '';
    final queryNorm = arguments['queryNormalization'];
    final normalizedQuery = singleTaskQuery.isNotEmpty
        ? singleTaskQuery
        : queryNorm is Map
        ? ((queryNorm['normalizedQuery'] as String?)?.trim() ?? rawQuery)
        : rawQuery;
    final query = normalizedQuery.isNotEmpty ? normalizedQuery : rawQuery;
    final queryTask = _resolveSingleQueryTask(
      arguments: arguments,
      normalizedQuery: query,
      normalizedTasks: queryTasks,
    );
    final domainId =
        ((arguments['domainId'] as String?)?.trim().isNotEmpty == true
            ? (arguments['domainId'] as String).trim()
            : (arguments['__domainId'] as String?)?.trim()) ??
        '';
    final sessionId = (arguments['__sessionId'] as String?)?.trim() ?? '';
    final runId = (arguments['__runId'] as String?)?.trim() ?? '';
    final traceId = (arguments['__traceId'] as String?)?.trim() ?? '';
    final count = (arguments['count'] as int?) ?? 5;
    if (query.isEmpty) {
      return const AssistantToolResult(
        success: false,
        message: 'Missing query',
        errorCode: AssistantErrorCode.invalidArguments,
      );
    }

    // Check search cache before hitting the network
    final cached = _searchCache.get(query);
    if (cached != null) {
      final cachedData = <String, dynamic>{...cached};
      final cachedRefs =
          (cachedData['references'] as List?)
              ?.whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      if (cachedRefs.isNotEmpty) {
        cachedData['references'] = _decorateReferences(
          references: cachedRefs,
          query: query,
          authorityDomains:
              (cachedData['authorityDomains'] as List?)
                  ?.whereType<String>()
                  .toList(growable: false) ??
              const <String>[],
          timeConstraint: _SearchTimeConstraint(
            scope: 'cached',
            start: DateTime.now(),
            end: DateTime.now(),
            freshnessHoursMax:
                (cachedData['freshnessHours'] as num?)?.toInt() ?? 72,
          ),
          queryTask: queryTask,
          retrievedAt: DateTime.now().toIso8601String(),
        );
      }
      return AssistantToolResult(
        success: true,
        message: cachedData['message'] as String? ?? '检索结果（缓存）',
        data: <String, dynamic>{...cachedData, 'cacheHit': true},
      );
    }

    final runtimeConfig = await _resolveRuntimeConfig();
    final timeContract = await _loadRetrievalTimeContract();
    final domainPolicy = await _loadDomainRetrievalPolicy(domainId);
    final timeConstraint = _resolveTimeConstraint(
      arguments: arguments,
      domainPolicy: domainPolicy,
      timeContract: timeContract,
    );
    final baseScopedQuery = _withTimeConstraintQuery(
      query: query,
      constraint: timeConstraint,
    );
    final scopedQuery = _withDomainContextQuery(
      query: baseScopedQuery,
      arguments: arguments,
      domainPolicy: domainPolicy,
    );
    final authorityDomains = _resolveAuthorityDomains(
      arguments: arguments,
      domainPolicy: domainPolicy,
    );
    final provider = _resolveProvider(
      raw: arguments['provider'] as String?,
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
            'count': count,
            'providerHint': (arguments['provider'] as String?) ?? '',
            'timeConstraint': timeConstraint.toJson(),
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
            'Web search error: 未发现可用搜索 provider。默认使用 Brave（BRAVE_API_KEY 或 PERSONAL_ASSISTANT_BRAVE_API_KEY），'
            '其次 Perplexity（PERPLEXITY_API_KEY / OPENROUTER_API_KEY / PERSONAL_ASSISTANT_PERPLEXITY_API_KEY）。'
            '支持 SerpApi（SERPAPI_API_KEY / PERSONAL_ASSISTANT_SERPAPI_API_KEY）。'
            'OpenClaw 仅作为可选代理，不是默认依赖。若以上 key 都未配置，将自动回退到 DuckDuckGo 公共检索。',
        data: <String, dynamic>{'diagnostics': runtimeConfig.toDiagnostics()},
        errorCode: AssistantErrorCode.invalidArguments,
        degraded: true,
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
      final enrichedReferences = _decorateReferences(
        references: references,
        query: query,
        authorityDomains: authorityDomains,
        timeConstraint: timeConstraint,
        queryTask: queryTask,
        retrievedAt: DateTime.now().toIso8601String(),
      );
      final evidenceStats = _buildEvidenceStats(
        references: enrichedReferences,
        authorityDomains: authorityDomains,
        timeConstraint: timeConstraint,
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
            'count': count,
            'providerHint': (arguments['provider'] as String?) ?? '',
            'timeConstraint': timeConstraint.toJson(),
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
      // 权威域内无任何匹配时，标记为信息不足，让 LLM 降级回复而非用无关内容糊弄用户。
      final primaryAuthorityScore =
          (evidenceStats['authorityScore'] as double?) ?? 0.0;
      final primaryAuthCount =
          (evidenceStats['authoritativeCount'] as int?) ?? 0;
      final primaryIsLowQuality =
          primaryAuthCount == 0 &&
          primaryAuthorityScore == 0.0 &&
          authorityDomains.isNotEmpty;
      if (primaryIsLowQuality) {
        return AssistantToolResult(
          success: false,
          message:
              '检索完成但信息不足：返回结果与目标领域（${authorityDomains.join('/')}）无关联，建议降级回复。',
          errorCode: AssistantErrorCode.executionFailed,
          data: <String, dynamic>{
            'provider': provider.name,
            'summary': summary,
            'references': enrichedReferences,
            'timeConstraint': timeConstraint.toJson(),
            'authorityDomains': authorityDomains,
            if (domainId.isNotEmpty) 'domainId': domainId,
            if (_stringValue(queryTask['id']).isNotEmpty)
              'queryTaskId': _stringValue(queryTask['id']),
            if (_stringValue(queryTask['dimension']).isNotEmpty)
              'dimension': _stringValue(queryTask['dimension']),
            ...evidenceStats,
            'raw': decoded,
            'diagnostics': runtimeConfig.toDiagnostics(
              selectedProvider: provider.name,
            ),
          },
        );
      }
      final resultData = <String, dynamic>{
        'provider': provider.name,
        'summary': summary,
        'references': enrichedReferences,
        'timeConstraint': timeConstraint.toJson(),
        'authorityDomains': authorityDomains,
        if (domainId.isNotEmpty) 'domainId': domainId,
        if (_stringValue(queryTask['id']).isNotEmpty)
          'queryTaskId': _stringValue(queryTask['id']),
        if (_stringValue(queryTask['dimension']).isNotEmpty)
          'dimension': _stringValue(queryTask['dimension']),
        ...evidenceStats,
        'raw': decoded,
        'diagnostics': runtimeConfig.toDiagnostics(
          selectedProvider: provider.name,
        ),
        'message': message,
      };
      _searchCache.put(query, resultData);
      return AssistantToolResult(
        success: true,
        message: message,
        data: resultData,
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
        final enrichedFallbackReferences = _decorateReferences(
          references: fallbackReferences,
          query: query,
          authorityDomains: authorityDomains,
          timeConstraint: timeConstraint,
          queryTask: queryTask,
          retrievedAt: DateTime.now().toIso8601String(),
        );
        final evidenceStats = _buildEvidenceStats(
          references: enrichedFallbackReferences,
          authorityDomains: authorityDomains,
          timeConstraint: timeConstraint,
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
              'count': count,
              'fallbackFrom': provider.name,
              'timeConstraint': timeConstraint.toJson(),
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
        // 当权威域内无任何匹配结果时，标记为检索信息不足，让 LLM 知道需要降级。
        final fallbackAuthorityScore =
            (evidenceStats['authorityScore'] as double?) ?? 0.0;
        final fallbackAuthCount =
            (evidenceStats['authoritativeCount'] as int?) ?? 0;
        final fallbackIsLowQuality =
            fallbackAuthCount == 0 &&
            fallbackAuthorityScore == 0.0 &&
            authorityDomains.isNotEmpty;
        if (fallbackIsLowQuality) {
          return AssistantToolResult(
            success: false,
            message:
                '检索完成但信息不足：返回结果与目标领域（${authorityDomains.join('/')}）无关联，建议降级回复。',
            errorCode: AssistantErrorCode.executionFailed,
            data: <String, dynamic>{
              'provider': fallback.providerLabel,
              'summary': fallback.summary,
              'references': enrichedFallbackReferences,
              'timeConstraint': timeConstraint.toJson(),
              'authorityDomains': authorityDomains,
              if (domainId.isNotEmpty) 'domainId': domainId,
              if (_stringValue(queryTask['id']).isNotEmpty)
                'queryTaskId': _stringValue(queryTask['id']),
              if (_stringValue(queryTask['dimension']).isNotEmpty)
                'dimension': _stringValue(queryTask['dimension']),
              ...evidenceStats,
              'raw': fallback.raw,
              'fallbackFrom': provider.name,
              'primaryError': error.toString(),
              'diagnostics': runtimeConfig.toDiagnostics(
                selectedProvider: fallback.providerLabel,
              ),
            },
          );
        }
        return AssistantToolResult(
          success: true,
          message: fallbackMessage,
          data: <String, dynamic>{
            'provider': fallback.providerLabel,
            'summary': fallback.summary,
            'references': enrichedFallbackReferences,
            'timeConstraint': timeConstraint.toJson(),
            'authorityDomains': authorityDomains,
            if (domainId.isNotEmpty) 'domainId': domainId,
            if (_stringValue(queryTask['id']).isNotEmpty)
              'queryTaskId': _stringValue(queryTask['id']),
            if (_stringValue(queryTask['dimension']).isNotEmpty)
              'dimension': _stringValue(queryTask['dimension']),
            ...evidenceStats,
            'raw': fallback.raw,
            'fallbackFrom': provider.name,
            'primaryError': error.toString(),
            'diagnostics': runtimeConfig.toDiagnostics(
              selectedProvider: fallback.providerLabel,
            ),
          },
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
            'count': count,
            'timeConstraint': timeConstraint.toJson(),
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
        data: <String, dynamic>{
          'provider': provider.name,
          'retryable': classifiedError.retryable,
          'rawError': error.toString(),
          'diagnostics': runtimeConfig.toDiagnostics(
            selectedProvider: provider.name,
          ),
        },
        errorCode: classifiedError.errorCode,
        degraded: true,
      );
    }
  }

  Map<String, dynamic> _buildEvidenceStats({
    required List<Map<String, dynamic>> references,
    required List<String> authorityDomains,
    required _SearchTimeConstraint timeConstraint,
  }) {
    final freshnessHours = _estimateFreshnessHours(
      references: references,
      timeConstraint: timeConstraint,
    );
    final total = references.length;
    var authoritative = 0;
    for (final ref in references) {
      final url = (ref['url'] as String?)?.trim() ?? '';
      final host = Uri.tryParse(url)?.host.toLowerCase() ?? '';
      if (host.isEmpty) continue;
      if (authorityDomains.any((d) => host == d || host.endsWith('.$d'))) {
        authoritative += 1;
      }
    }
    final coverage = total <= 0 ? 0.0 : (total / 4).clamp(0.0, 1.0).toDouble();
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
    // Layer 3 综合质量评分：相关性(0.35) + 权威性(0.25) + 时效性(0.2) + 覆盖量(0.2)
    final freshScore = freshnessHours <= timeConstraint.freshnessHoursMax
        ? 1.0
        : (timeConstraint.freshnessHoursMax / freshnessHours).clamp(0.0, 1.0);
    final qualityScore =
        (relevanceScore * 0.35 +
                authorityScore * 0.25 +
                freshScore * 0.2 +
                coverage * 0.2)
            .clamp(0.0, 1.0)
            .toDouble();
    // 保留向后兼容的 confidence 字段
    final confidence = qualityScore;
    return <String, dynamic>{
      'freshnessHours': freshnessHours,
      'freshScore': freshScore,
      'coverage': coverage,
      'confidence': confidence,
      'qualityScore': qualityScore,
      'authorityScore': authorityScore,
      'relevanceScore': relevanceScore,
      'authoritativeCount': authoritative,
      'totalReferences': total,
    };
  }

  double _estimateFreshnessHours({
    required List<Map<String, dynamic>> references,
    required _SearchTimeConstraint timeConstraint,
  }) {
    final now = DateTime.now();
    final candidates = <double>[];
    for (final ref in references) {
      final observedAt = (ref['observedAt'] as String?)?.trim() ?? '';
      final publishedAt = (ref['publishedAt'] as String?)?.trim() ?? '';
      DateTime? ts;
      if (observedAt.isNotEmpty) {
        ts = DateTime.tryParse(observedAt);
      }
      ts ??= DateTime.tryParse(publishedAt);
      if (ts == null) {
        final snippet = (ref['snippet'] as String?)?.trim() ?? '';
        ts = _parseDateFromText(snippet);
      }
      if (ts == null) continue;
      final hours = now.difference(ts.toLocal()).inMinutes / 60.0;
      if (hours.isFinite && hours >= 0) {
        candidates.add(hours);
      }
    }
    if (candidates.isNotEmpty) {
      candidates.sort();
      return candidates.first;
    }
    // No explicit date signal: keep conservative for realtime scopes.
    if (timeConstraint.isRealtimeLike) {
      return 9999;
    }
    return timeConstraint.freshnessHoursMax.toDouble();
  }

  DateTime? _parseDateFromText(String text) {
    if (text.isEmpty) return null;
    final iso = RegExp(
      r'(20\d{2})[-/年\.](\d{1,2})[-/月\.](\d{1,2})',
    ).firstMatch(text);
    if (iso == null) return null;
    final y = int.tryParse(iso.group(1) ?? '');
    final m = int.tryParse(iso.group(2) ?? '');
    final d = int.tryParse(iso.group(3) ?? '');
    if (y == null || m == null || d == null) return null;
    return DateTime(y, m, d);
  }

  _SearchTimeConstraint _resolveTimeConstraint({
    required Map<String, dynamic> arguments,
    required _DomainRetrievalPolicy domainPolicy,
    required _RetrievalTimeContract timeContract,
  }) {
    final now = DateTime.now();
    final explicitScope =
        (arguments['timeScope'] as String?)?.trim().toLowerCase() ?? '';
    final explicitFreshness = (arguments['freshnessHoursMax'] as num?)?.toInt();
    final startRaw = (arguments['timeRangeStart'] as String?)?.trim() ?? '';
    final endRaw = (arguments['timeRangeEnd'] as String?)?.trim() ?? '';
    final start = DateTime.tryParse(startRaw);
    final end = DateTime.tryParse(endRaw);
    final allowedScopes = domainPolicy.allowedTimeScopes.isEmpty
        ? timeContract.supportedScopes
        : domainPolicy.allowedTimeScopes;
    var scope = explicitScope.isNotEmpty
        ? explicitScope
        : domainPolicy.defaultTimeScope;
    if (scope.isEmpty) {
      scope = timeContract.defaultScope;
    }
    if (!allowedScopes.contains(scope)) {
      scope =
          domainPolicy.defaultTimeScope.isNotEmpty &&
              allowedScopes.contains(domainPolicy.defaultTimeScope)
          ? domainPolicy.defaultTimeScope
          : (allowedScopes.isNotEmpty
                ? allowedScopes.first
                : timeContract.defaultScope);
    }
    if (start != null && end != null && !end.isBefore(start)) {
      final maxHours =
          explicitFreshness ??
          domainPolicy.defaultFreshnessHoursMax ??
          timeContract.freshnessHoursMaxByScope[scope] ??
          now.difference(start).inHours.clamp(1, 24 * 366);
      return _SearchTimeConstraint(
        scope: scope,
        start: start,
        end: end,
        freshnessHoursMax: maxHours,
      );
    }
    final calendarPointRange = _resolveRangeByCalendarPoint(
      arguments: arguments,
      now: now,
      scope: scope,
    );
    if (calendarPointRange != null) {
      final maxHours =
          explicitFreshness ??
          domainPolicy.defaultFreshnessHoursMax ??
          timeContract.freshnessHoursMaxByScope[calendarPointRange.scope] ??
          now
              .difference(calendarPointRange.range.start)
              .inHours
              .clamp(24, 24 * 3650);
      return _SearchTimeConstraint(
        scope: calendarPointRange.scope,
        start: calendarPointRange.range.start,
        end: calendarPointRange.range.end,
        freshnessHoursMax: maxHours,
      );
    }
    final resolvedRange = _resolveRangeByScope(
      scope: scope,
      now: now,
      timeContract: timeContract,
    );
    final maxHours =
        explicitFreshness ??
        domainPolicy.defaultFreshnessHoursMax ??
        timeContract.freshnessHoursMaxByScope[scope] ??
        timeContract.defaultFreshnessHoursMax;
    return _SearchTimeConstraint(
      scope: scope,
      start: resolvedRange.start,
      end: resolvedRange.end,
      freshnessHoursMax: maxHours,
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

  int? _asInt(dynamic raw) {
    if (raw is int) return raw;
    if (raw is num) return raw.toInt();
    if (raw is String) return int.tryParse(raw.trim());
    return null;
  }

  _ResolvedTimeRange _resolveRangeByScope({
    required String scope,
    required DateTime now,
    required _RetrievalTimeContract timeContract,
  }) {
    final configuredHours = timeContract.windowHoursByScope[scope];
    if (configuredHours != null && configuredHours > 0) {
      return _ResolvedTimeRange(
        start: now.subtract(Duration(hours: configuredHours)),
        end: now,
      );
    }
    if (scope == 'today') {
      return _ResolvedTimeRange(
        start: DateTime(now.year, now.month, now.day),
        end: now,
      );
    }
    if (scope == 'year_to_date') {
      return _ResolvedTimeRange(start: DateTime(now.year, 1, 1), end: now);
    }
    return _ResolvedTimeRange(
      start: now.subtract(const Duration(days: 30)),
      end: now,
    );
  }

  String _withTimeConstraintQuery({
    required String query,
    required _SearchTimeConstraint constraint,
  }) {
    final start = constraint.start.toIso8601String().substring(0, 10);
    final end = constraint.end.toIso8601String().substring(0, 10);
    return '$query 时间范围:$start..$end';
  }

  String _withDomainContextQuery({
    required String query,
    required Map<String, dynamic> arguments,
    required _DomainRetrievalPolicy domainPolicy,
  }) {
    final contextConstraints =
        (arguments['contextConstraints'] as List?)
            ?.whereType<String>()
            .map((item) => item.trim())
            .where((item) => item.isNotEmpty)
            .toList(growable: false) ??
        const <String>[];
    final scopedHints = <String>[
      ...contextConstraints,
      ...domainPolicy.contextConstraints,
    ];
    if (scopedHints.isEmpty) return query;
    final hintText = scopedHints.toSet().join(' ');
    return '$query 上下文限定:$hintText';
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
    const path =
        'assets/personal_assistant/config/retrieval_time_contract.json';
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
        'assets/personal_assistant/skills/$domainId/config/retrieval_policy.json';
    try {
      final content = await _loadText(path);
      final decoded = jsonDecode(content);
      if (decoded is! Map) return const _DomainRetrievalPolicy();
      final map = decoded.cast<String, dynamic>();
      return _DomainRetrievalPolicy(
        defaultTimeScope: (map['defaultTimeScope'] as String?)?.trim() ?? '',
        defaultFreshnessHoursMax: (map['defaultFreshnessHoursMax'] as num?)
            ?.toInt(),
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
      );
    } catch (_) {
      return const _DomainRetrievalPolicy();
    }
  }

  Map<String, int> _toIntMap(dynamic raw) {
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
  }

  String _summarizeProviderResult({
    required AssistantSearchProvider provider,
    required dynamic decoded,
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
    required dynamic decoded,
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

  List<Map<String, dynamic>> _extractBraveReferences(dynamic decoded) {
    if (decoded is! Map) return const <Map<String, dynamic>>[];
    final results =
        ((decoded['web'] as Map?)?['results'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    return results
        .take(12)
        .map(
          (item) => <String, dynamic>{
            'title': (item['title'] as String?)?.trim() ?? '',
            'url': (item['url'] as String?)?.trim() ?? '',
            'snippet': (item['description'] as String?)?.trim() ?? '',
            'provider': AssistantSearchProvider.brave.name,
          },
        )
        .where((item) => (item['url'] as String).isNotEmpty)
        .toList(growable: false);
  }

  List<Map<String, dynamic>> _extractDuckduckgoReferences(dynamic decoded) {
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
          .map(
            (item) => <String, dynamic>{
              'title': (item['title'] as String?)?.trim() ?? '',
              'url': (item['url'] as String?)?.trim() ?? '',
              'snippet': (item['snippet'] as String?)?.trim() ?? '',
              'provider': AssistantSearchProvider.duckduckgo.name,
            },
          )
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
      final text = (item['Text'] as String?)?.trim() ?? '';
      final url = (item['FirstURL'] as String?)?.trim() ?? '';
      if (url.isNotEmpty) {
        refs.add(<String, dynamic>{
          'title': text,
          'url': url,
          'snippet': text,
          'provider': AssistantSearchProvider.duckduckgo.name,
        });
      }
    }
    return refs;
  }

  List<Map<String, dynamic>> _extractPerplexityReferences(dynamic decoded) {
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
          (url) => <String, dynamic>{
            'title': url,
            'url': url,
            'snippet': '',
            'provider': AssistantSearchProvider.perplexity.name,
          },
        )
        .toList(growable: false);
  }

  List<Map<String, dynamic>> _extractSerpApiReferences(dynamic decoded) {
    if (decoded is! Map) return const <Map<String, dynamic>>[];
    final organic =
        (decoded['organic_results'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    return organic
        .take(12)
        .map(
          (item) => <String, dynamic>{
            'title': (item['title'] as String?)?.trim() ?? '',
            'url': (item['link'] as String?)?.trim() ?? '',
            'snippet': (item['snippet'] as String?)?.trim() ?? '',
            'provider': AssistantSearchProvider.serpapi.name,
          },
        )
        .where((item) => (item['url'] as String).isNotEmpty)
        .toList(growable: false);
  }

  List<Map<String, dynamic>> _extractOpenclawReferences(dynamic decoded) {
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
          (item) => <String, dynamic>{
            'title': (item['title'] as String?)?.trim() ?? '',
            'url': (item['url'] as String?)?.trim() ?? '',
            'snippet': (item['snippet'] as String?)?.trim() ?? '',
            'provider': AssistantSearchProvider.openclawProxy.name,
          },
        )
        .where((item) => (item['url'] as String).isNotEmpty)
        .toList(growable: false);
  }

  String _summarizePerplexity(dynamic decoded) {
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

  String _summarizeBrave(dynamic decoded) {
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

  String _summarizeOpenclaw(dynamic decoded) {
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

  String _summarizeDuckduckgo(dynamic decoded) {
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

  String _summarizeSerpApi(dynamic decoded) {
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
    if (normalized == 'brave') return AssistantSearchProvider.brave;
    if (normalized == 'perplexity') return AssistantSearchProvider.perplexity;
    if (normalized == 'openclaw_proxy') {
      return AssistantSearchProvider.openclawProxy;
    }
    if (normalized == 'serpapi') {
      return AssistantSearchProvider.serpapi;
    }
    if (normalized == 'duckduckgo' || normalized == 'ddg') {
      return AssistantSearchProvider.duckduckgo;
    }
    final configuredDefault = _parseProvider(config.defaultProvider);
    final fallbackOrder = <AssistantSearchProvider>[
      ...?configuredDefault == null
          ? null
          : <AssistantSearchProvider>[configuredDefault],
      _defaultProvider,
      AssistantSearchProvider.serpapi,
      AssistantSearchProvider.duckduckgo,
      AssistantSearchProvider.brave,
      AssistantSearchProvider.perplexity,
    ];
    for (final candidate in fallbackOrder) {
      if (_providerReady(candidate, config)) return candidate;
    }
    return null;
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

  Future<dynamic> _runProviderSearch({
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
        retryable: false,
      );
    }
    if (normalized.contains('(429)') || normalized.contains('rate limit')) {
      return const _ClassifiedSearchError(
        errorCode: AssistantErrorCode.rateLimited,
        message: '搜索服务当前限流，请稍后重试。',
        retryable: true,
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
        retryable: true,
      );
    }
    return const _ClassifiedSearchError(
      errorCode: AssistantErrorCode.executionFailed,
      message: '搜索失败，请稍后重试。',
      retryable: false,
    );
  }

  Future<dynamic> _searchBrave({
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
    final response = await http
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

  Future<dynamic> _searchPerplexity({
    required String query,
    required String apiKey,
    required String baseUrl,
    required String model,
  }) async {
    if (apiKey.isEmpty) {
      throw Exception('Perplexity API key is missing');
    }
    final response = await http
        .post(
          Uri.parse(
            '${baseUrl.replaceAll(RegExp(r'/$'), '')}/chat/completions',
          ),
          headers: <String, String>{
            'Content-Type': 'application/json',
            'Authorization': 'Bearer $apiKey',
            if (baseUrl.contains('openrouter.ai'))
              'HTTP-Referer': 'https://quwoquan.app',
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

  Future<dynamic> _searchOpenClawProxy({
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
    final response = await http
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

  Future<dynamic> _searchDuckDuckGo({required String query}) async {
    final cleanQuery = _stripSearchSuffixes(query);
    final response = await http
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
      'RelatedTopics': <dynamic>[],
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

  Future<dynamic> _searchSerpApi({
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
    final response = await http
        .get(url, headers: const <String, String>{'Accept': 'application/json'})
        .timeout(_networkTimeout);
    if (response.statusCode >= 400) {
      throw Exception('SerpApi search failed (${response.statusCode})');
    }
    return jsonDecode(response.body);
  }

  Future<_WebSearchRuntimeConfig> _resolveRuntimeConfig() async {
    final profile = await _loadSearchProfile();
    String brave = _braveApiKey.trim();
    String perplexity = _perplexityApiKey.trim();
    String serpapi = _serpApiKey.trim();
    String openclawBaseUrl = _openclawBaseUrl.trim();
    String openclawToken = _openclawToken.trim();
    String openrouter = '';

    final dotEnv = await _loadRuntimeDotEnv();
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
      final assetEnv = await rootBundle.loadString('personal_assistant/.env');
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
        '$basePath/.personal_assistant/.env',
        '$basePath/personal_assistant/.env',
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
      final bundledText = await rootBundle.loadString(
        'personal_assistant/config.json',
      );
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
        '$basePath/.personal_assistant/config.json',
        '$basePath/personal_assistant/config.json',
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
    Map<dynamic, dynamic> perplexityMap = const <dynamic, dynamic>{};
    if (perplexity is Map) {
      perplexityMap = perplexity;
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
    List<Map<String, dynamic>> queryTasks,
  ) async {
    final allTasks = _normalizeQueryTasks(queryTasks);
    final allQueries = allTasks
        .map((task) => (task['query'] as String?)?.trim() ?? '')
        .where((query) => query.isNotEmpty)
        .toList(growable: false);
    final labels = allTasks
        .map((task) => (task['label'] as String?)?.trim() ?? '')
        .where((label) => label.isNotEmpty)
        .toList(growable: false);
    final dimensions = allTasks
        .map((task) => (task['dimension'] as String?)?.trim() ?? '')
        .where((dimension) => dimension.isNotEmpty)
        .toSet()
        .toList(growable: false);
    final futures = allTasks
        .map((task) {
          final singleArgs = Map<String, dynamic>.from(arguments)
            ..['query'] = (task['query'] as String?)?.trim() ?? ''
            ..['queryTaskId'] = (task['id'] as String?)?.trim() ?? ''
            ..['queryTaskLabel'] = (task['label'] as String?)?.trim() ?? ''
            ..['dimension'] = (task['dimension'] as String?)?.trim() ?? ''
            ..['entityAnchors'] = _stringList(task['entityAnchors'])
            ..['negativeKeywords'] = _stringList(task['negativeKeywords'])
            ..remove('queryVariants')
            ..remove('queryTasks');
          return execute(singleArgs);
        })
        .toList(growable: false);
    final results = await Future.wait(futures, eagerError: false);
    final mergedCandidates = <Map<String, dynamic>>[];
    final coveredDimensions = <String>{};
    String bestSummary = '';
    double bestQuality = 0.0;
    String bestProvider = '';
    var anySuccess = false;

    for (var i = 0; i < results.length; i++) {
      final r = results[i];
      final task = i < allTasks.length
          ? allTasks[i]
          : const <String, dynamic>{};
      if (r.success) anySuccess = true;
      final data = r.data ?? const <String, dynamic>{};
      final refs =
          (data['references'] as List?)
              ?.whereType<Map>()
              .map((e) => e.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      final filteredRefs = _applyTaskFilters(refs, task: task);
      if (filteredRefs.isNotEmpty) {
        final dimension =
            (task['dimension'] as String?)?.trim() ??
            (task['label'] as String?)?.trim() ??
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
            task: task,
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
    final effectiveQuality = rerankedQuality > 0
        ? rerankedQuality
        : bestQuality;
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
      data: <String, dynamic>{
        'provider': bestProvider,
        'summary': effectiveSummary,
        'references': mergedRefs.take(10).toList(growable: false),
        'qualityScore': effectiveQuality,
        'queryCount': allQueries.length,
        'queryLabels': labels,
        'coveredDimensions': coveredDimensions.isNotEmpty
            ? coveredDimensions.toList(growable: false)
            : labels,
        'missingDimensions': missingDimensions,
        'queryTasks': allTasks,
        'referenceCount': mergedRefs.length,
        'totalReferences': mergedRefs.length,
        'rerankStats': <String, dynamic>{
          'candidateCount': mergedCandidates.length,
          'returnedCount': mergedRefs.length,
        },
        'message': '多路检索完成。',
      },
    );
  }

  List<Map<String, dynamic>> _applyTaskFilters(
    List<Map<String, dynamic>> references, {
    required Map<String, dynamic> task,
  }) {
    final anchors = _stringList(
      task['entityAnchors'],
    ).map((item) => item.toLowerCase()).toList(growable: false);
    final negatives = _stringList(
      task['negativeKeywords'],
    ).map((item) => item.toLowerCase()).toList(growable: false);
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
    required Map<String, dynamic> task,
    required List<String> requestedDimensions,
  }) {
    final relevance = (reference['relevanceScore'] as num?)?.toDouble() ?? 0.0;
    final authority = (reference['authorityScore'] as num?)?.toDouble() ?? 0.0;
    final freshnessHours =
        (reference['freshnessHours'] as num?)?.toDouble() ?? 0.0;
    final freshnessScore = _freshnessScore(freshnessHours);
    final dimension = (reference['dimension'] as String?)?.trim() ?? '';
    final dimensionBonus =
        requestedDimensions.isEmpty ||
            (dimension.isNotEmpty && requestedDimensions.contains(dimension))
        ? 1.0
        : 0.6;
    final anchorBonus = _stringList(task['entityAnchors']).isEmpty ? 1.0 : 1.08;
    return (relevance * 0.5 +
            authority * 0.22 +
            freshnessScore * 0.18 +
            dimensionBonus * 0.1) *
        anchorBonus;
  }

  double _freshnessScore(double freshnessHours) {
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

  List<Map<String, dynamic>> _normalizeQueryTasks(Object? raw) {
    final tasks = QueryTask.normalizeList(raw);
    final normalized = <Map<String, dynamic>>[];
    final seen = <String>{};
    for (final task in tasks) {
      final query = task.query.trim();
      if (query.isEmpty || !seen.add(query)) continue;
      final normalizedTask = Map<String, dynamic>.from(task.toJson());
      normalizedTask['id'] = task.id.trim().isNotEmpty
          ? task.id.trim()
          : _normalizeQueryTaskId(
              query,
              preferred: task.dimensionCode.isNotEmpty
                  ? task.dimensionCode
                  : task.label,
            );
      normalizedTask['query'] = query;
      normalized.add(normalizedTask);
    }
    return normalized;
  }

  List<Map<String, dynamic>> _queryTasksFromSeeds(
    String mainQuery,
    List<String> variants,
  ) {
    final tasks = <Map<String, dynamic>>[];
    final seen = <String>{};

    void addTask(String query) {
      final normalized = query.trim();
      if (normalized.isEmpty || !seen.add(normalized)) return;
      tasks.add(<String, dynamic>{'query': normalized, 'label': normalized});
    }

    if (mainQuery.isNotEmpty) {
      addTask(mainQuery);
    }
    for (final variant in variants) {
      addTask(variant);
    }
    return tasks;
  }

  Map<String, dynamic> _resolveSingleQueryTask({
    required Map<String, dynamic> arguments,
    required String normalizedQuery,
    required List<Map<String, dynamic>> normalizedTasks,
  }) {
    if (normalizedTasks.length == 1) {
      return normalizedTasks.first;
    }
    final explicitId = (arguments['queryTaskId'] as String?)?.trim() ?? '';
    final explicitLabel =
        (arguments['queryTaskLabel'] as String?)?.trim() ?? '';
    final explicitDimension = (arguments['dimension'] as String?)?.trim() ?? '';
    return <String, dynamic>{
      'id': explicitId.isNotEmpty
          ? explicitId
          : _normalizeQueryTaskId(
              normalizedQuery,
              preferred: explicitDimension.isNotEmpty
                  ? explicitDimension
                  : explicitLabel,
            ),
      'label': explicitLabel.isNotEmpty ? explicitLabel : normalizedQuery,
      if (explicitDimension.isNotEmpty) 'dimension': explicitDimension,
      if (_stringList(arguments['entityAnchors']).isNotEmpty)
        'entityAnchors': _stringList(arguments['entityAnchors']),
      if (_stringList(arguments['negativeKeywords']).isNotEmpty)
        'negativeKeywords': _stringList(arguments['negativeKeywords']),
      if ((arguments['answerShape'] as String?)?.trim().isNotEmpty == true)
        'answerShape': (arguments['answerShape'] as String).trim(),
    };
  }

  List<Map<String, dynamic>> _decorateReferences({
    required List<Map<String, dynamic>> references,
    required String query,
    required List<String> authorityDomains,
    required _SearchTimeConstraint timeConstraint,
    required Map<String, dynamic> queryTask,
    required String retrievedAt,
  }) {
    return references
        .map((ref) {
          final url = (ref['url'] as String?)?.trim() ?? '';
          final host = Uri.tryParse(url)?.host.toLowerCase().trim() ?? '';
          final source = (ref['source'] as String?)?.trim().isNotEmpty == true
              ? (ref['source'] as String).trim()
              : host;
          final sourceTier =
              (ref['sourceTier'] as String?)?.trim().isNotEmpty == true
              ? (ref['sourceTier'] as String).trim()
              : _resolveSourceTier(
                  host: host,
                  authorityDomains: authorityDomains,
                );
          final freshnessHours =
              _intValue(ref['freshnessHours']) ??
              _estimateReferenceFreshnessHours(
                ref,
                timeConstraint: timeConstraint,
              );
          final authorityScore =
              (ref['authorityScore'] as num?)?.toDouble() ??
              _estimateAuthorityScore(
                sourceTier: sourceTier,
                host: host,
                authorityDomains: authorityDomains,
              );
          final relevanceScore =
              (ref['relevanceScore'] as num?)?.toDouble() ??
              _estimateReferenceRelevance(
                query: query,
                reference: ref,
                queryTask: queryTask,
              );
          return <String, dynamic>{
            ...ref,
            'source': source,
            'sourceHost': host,
            'sourceTier': sourceTier,
            'freshnessHours': freshnessHours,
            'authorityScore': authorityScore,
            'relevanceScore': relevanceScore,
            'queryTaskId': _stringValue(queryTask['id']),
            'queryTaskLabel': _stringValue(queryTask['label']),
            'dimension': _stringValue(queryTask['dimension']).isNotEmpty
                ? _stringValue(queryTask['dimension'])
                : _stringValue(queryTask['label']),
            if (_stringList(queryTask['entityAnchors']).isNotEmpty)
              'entityAnchors': _stringList(queryTask['entityAnchors']),
            if (_stringList(queryTask['negativeKeywords']).isNotEmpty)
              'negativeKeywords': _stringList(queryTask['negativeKeywords']),
            'retrievedAt':
                (ref['retrievedAt'] as String?)?.trim().isNotEmpty == true
                ? (ref['retrievedAt'] as String).trim()
                : retrievedAt,
          };
        })
        .where((item) => (item['url'] as String?)?.trim().isNotEmpty == true)
        .toList(growable: false);
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

  int _estimateReferenceFreshnessHours(
    Map<String, dynamic> reference, {
    required _SearchTimeConstraint timeConstraint,
  }) {
    final now = DateTime.now();
    final observedAt = (reference['observedAt'] as String?)?.trim() ?? '';
    final publishedAt = (reference['publishedAt'] as String?)?.trim() ?? '';
    DateTime? timestamp;
    if (observedAt.isNotEmpty) {
      timestamp = DateTime.tryParse(observedAt);
    }
    timestamp ??= DateTime.tryParse(publishedAt);
    timestamp ??= _parseDateFromText(
      (reference['snippet'] as String?)?.trim() ?? '',
    );
    if (timestamp == null) {
      return timeConstraint.freshnessHoursMax;
    }
    return now.difference(timestamp.toLocal()).inHours.clamp(0, 24 * 3650);
  }

  double _estimateReferenceRelevance({
    required String query,
    required Map<String, dynamic> reference,
    required Map<String, dynamic> queryTask,
  }) {
    final tokens = query
        .toLowerCase()
        .split(RegExp(r'[\s,，。；;:/]+'))
        .map((item) => item.trim())
        .where((item) => item.length >= 2)
        .toSet();
    final anchorTokens = _stringList(queryTask['entityAnchors'])
        .map((item) => item.toLowerCase())
        .where((item) => item.length >= 2)
        .toSet();
    final negativeTokens = _stringList(queryTask['negativeKeywords'])
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

  String _normalizeQueryTaskId(String query, {String preferred = ''}) {
    final base = preferred.trim().isNotEmpty ? preferred.trim() : query.trim();
    final normalized = base
        .toLowerCase()
        .replaceAll(RegExp(r'[^\w\u4e00-\u9fa5]+'), '_')
        .replaceAll(RegExp(r'_+'), '_')
        .replaceAll(RegExp(r'^_|_$'), '');
    return normalized.isNotEmpty ? normalized : 'query_task';
  }

  int? _intValue(Object? value) {
    if (value is num) return value.toInt();
    return int.tryParse(value?.toString() ?? '');
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

  Future<_BackupSearchResult?> _tryFallbackSearch({
    required AssistantSearchProvider primaryProvider,
    required String query,
    required int count,
    required _WebSearchRuntimeConfig config,
  }) async {
    final candidates = <AssistantSearchProvider>[
      AssistantSearchProvider.brave,
      AssistantSearchProvider.perplexity,
      AssistantSearchProvider.openclawProxy,
      AssistantSearchProvider.serpapi,
      AssistantSearchProvider.duckduckgo,
    ];
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
  final dynamic raw;
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
  });

  final String scope;
  final DateTime start;
  final DateTime end;
  final int freshnessHoursMax;

  bool get isRealtimeLike =>
      scope == 'latest' || scope == 'today' || scope == 'last_7d';

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'scope': scope,
      'timeRangeStart': start.toIso8601String(),
      'timeRangeEnd': end.toIso8601String(),
      'freshnessHoursMax': freshnessHoursMax,
    };
  }
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
    this.allowedTimeScopes = const <String>[],
    this.authorityDomains = const <String>[],
    this.contextConstraints = const <String>[],
  });

  final String defaultTimeScope;
  final int? defaultFreshnessHoursMax;
  final List<String> allowedTimeScopes;
  final List<String> authorityDomains;
  final List<String> contextConstraints;
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
    required this.retryable,
  });

  final AssistantErrorCode errorCode;
  final String message;
  final bool retryable;
}
