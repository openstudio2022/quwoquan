import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:quwoquan_app/personal_assistant/observability/logging/app_log_models.dart';
import 'package:quwoquan_app/personal_assistant/observability/logging/app_log_service.dart';
import 'package:quwoquan_app/personal_assistant/observability/logging/app_run_interaction_collector.dart';
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
       _defaultProvider = defaultProvider ?? AssistantSearchProvider.duckduckgo;

  final String _braveApiKey;
  final String _perplexityApiKey;
  final String _serpApiKey;
  final String _openclawBaseUrl;
  final String _openclawToken;
  final AssistantSearchProvider _defaultProvider;
  static const Duration _networkTimeout = Duration(seconds: 8);

  @override
  String get name => 'web_search';

  @override
  String get description => 'Search web content for latest information.';

  @override
  Future<AssistantToolResult> execute(Map<String, dynamic> arguments) async {
    final query = (arguments['query'] as String?)?.trim() ?? '';
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
    final runtimeConfig = await _resolveRuntimeConfig();
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
            'query': query,
            'count': count,
            'providerHint': (arguments['provider'] as String?) ?? '',
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
        query: query,
        count: count,
        config: runtimeConfig,
      );
      final summary = _summarizeProviderResult(
        provider: provider,
        decoded: decoded,
      );
      await _logSearchInteraction(
        sessionId: sessionId,
        runId: runId,
        traceId: traceId,
        payload: <String, dynamic>{
          'kind': 'search',
          'provider': provider.name,
          'request': <String, dynamic>{
            'query': query,
            'count': count,
            'providerHint': (arguments['provider'] as String?) ?? '',
          },
          'response': <String, dynamic>{'summary': summary, 'raw': decoded},
          'diagnostics': runtimeConfig.toDiagnostics(
            selectedProvider: provider.name,
          ),
        },
      );
      final message = summary.isEmpty ? '检索成功，但未获得可用摘要。' : '检索结果：$summary';
      return AssistantToolResult(
        success: true,
        message: message,
        data: <String, dynamic>{
          'provider': provider.name,
          'summary': summary,
          'raw': decoded,
          'diagnostics': runtimeConfig.toDiagnostics(
            selectedProvider: provider.name,
          ),
        },
      );
    } catch (error) {
      final fallback = await _tryFallbackSearch(
        primaryProvider: provider,
        query: query,
        count: count,
        config: runtimeConfig,
      );
      if (fallback != null) {
        await _logSearchInteraction(
          sessionId: sessionId,
          runId: runId,
          traceId: traceId,
          payload: <String, dynamic>{
            'kind': 'search',
            'provider': fallback.providerLabel,
            'request': <String, dynamic>{
              'query': query,
              'count': count,
              'fallbackFrom': provider.name,
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
        return AssistantToolResult(
          success: true,
          message: fallbackMessage,
          data: <String, dynamic>{
            'provider': fallback.providerLabel,
            'summary': fallback.summary,
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
          'request': <String, dynamic>{'query': query, 'count': count},
          'error': error.toString(),
          'diagnostics': runtimeConfig.toDiagnostics(
            selectedProvider: provider.name,
          ),
        },
        hasError: true,
      );
      return AssistantToolResult(
        success: false,
        message: 'Web search error: $error',
        data: <String, dynamic>{
          'provider': provider.name,
          'diagnostics': runtimeConfig.toDiagnostics(
            selectedProvider: provider.name,
          ),
        },
        errorCode: AssistantErrorCode.networkUnavailable,
        degraded: true,
      );
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
    final abstractText = (decoded['AbstractText'] as String?)?.trim() ?? '';
    final heading = (decoded['Heading'] as String?)?.trim() ?? '';
    final abstractLine = _compressWhitespace(
      [heading, abstractText].where((s) => s.isNotEmpty).join(' - '),
    );
    if (abstractLine.isNotEmpty) {
      return _truncate(abstractLine);
    }
    final related = decoded['RelatedTopics'];
    if (related is! List || related.isEmpty) return '';
    final snippets = <String>[];
    for (final item in related.take(4)) {
      if (item is Map) {
        final text = (item['Text'] as String?)?.trim() ?? '';
        if (text.isNotEmpty) {
          snippets.add(_compressWhitespace(text));
          continue;
        }
        final topics = item['Topics'];
        if (topics is List) {
          for (final topic in topics.take(2)) {
            if (topic is! Map) continue;
            final nested = (topic['Text'] as String?)?.trim() ?? '';
            if (nested.isNotEmpty) {
              snippets.add(_compressWhitespace(nested));
            }
          }
        }
      }
    }
    if (snippets.isEmpty) return '';
    return _truncate(snippets.join('；'));
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

  String _truncate(String input, {int maxChars = 220}) {
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
    final url = Uri.parse('https://api.duckduckgo.com/').replace(
      queryParameters: <String, String>{
        'q': query,
        'format': 'json',
        'no_html': '1',
        'skip_disambig': '1',
      },
    );
    final response = await http
        .get(url, headers: const <String, String>{'Accept': 'application/json'})
        .timeout(_networkTimeout);
    if (response.statusCode >= 400) {
      throw Exception('DuckDuckGo search failed (${response.statusCode})');
    }
    return jsonDecode(response.body);
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
    if (!_looksLikeWeatherQuery(query)) return null;
    final weather = await _queryPublicWeather(query);
    if (weather == null || weather.summary.trim().isEmpty) return null;
    return weather;
  }

  bool _looksLikeWeatherQuery(String query) {
    final lowered = query.toLowerCase();
    return lowered.contains('天气') ||
        lowered.contains('气温') ||
        lowered.contains('降雨') ||
        lowered.contains('预报') ||
        lowered.contains('temperature') ||
        lowered.contains('weather');
  }

  Future<_BackupSearchResult?> _queryPublicWeather(String query) async {
    final city = _extractCityName(query);
    if (city.isEmpty) return null;
    try {
      final url = Uri.parse('https://wttr.in/$city').replace(
        queryParameters: <String, String>{'format': 'j1', 'lang': 'zh'},
      );
      final response = await http.get(url).timeout(_networkTimeout);
      if (response.statusCode >= 400) return null;
      final decoded = jsonDecode(response.body);
      if (decoded is! Map) return null;
      final current = (decoded['current_condition'] as List?)?.firstOrNull;
      if (current is! Map) return null;
      final tempC = (current['temp_C'] as String?)?.trim() ?? '';
      final feelsLike = (current['FeelsLikeC'] as String?)?.trim() ?? '';
      final weatherList = current['lang_zh'] as List?;
      String weatherDesc = '';
      if (weatherList is List && weatherList.isNotEmpty) {
        final first = weatherList.first;
        if (first is Map) {
          weatherDesc = (first['value'] as String?)?.trim() ?? '';
        }
      }
      final humidity = (current['humidity'] as String?)?.trim() ?? '';
      final summary = _compressWhitespace(
        '$city 当前天气${weatherDesc.isEmpty ? "" : "：$weatherDesc"}'
        '${tempC.isEmpty ? "" : "，气温 $tempC°C"}'
        '${feelsLike.isEmpty ? "" : "，体感 $feelsLike°C"}'
        '${humidity.isEmpty ? "" : "，湿度 $humidity%"}',
      );
      if (summary.isEmpty) return null;
      return _BackupSearchResult(
        providerLabel: 'public_weather_wttr',
        summary: summary,
        raw: decoded,
      );
    } catch (_) {
      return null;
    }
  }

  String _extractCityName(String query) {
    final text = query.trim();
    final cityWithSuffix = RegExp(
      r'([\u4e00-\u9fa5]{2,8}(?:市|区|县))',
    ).firstMatch(text)?.group(1);
    if (cityWithSuffix != null && cityWithSuffix.trim().isNotEmpty) {
      return cityWithSuffix.trim();
    }
    final citySimple = RegExp(
      r'([\u4e00-\u9fa5]{2,6})天气',
    ).firstMatch(text)?.group(1);
    if (citySimple != null && citySimple.trim().isNotEmpty) {
      return citySimple.trim();
    }
    return '';
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
