import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/assistant/debug/console_pretty_log_formatter.dart';
import 'package:quwoquan_app/assistant/retrieval/domain/retrieval_broker.dart';
import 'package:quwoquan_app/assistant/tool/impl/web/web_fetch_tool_contract.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';
import 'package:quwoquan_app/assistant/tool/runtime/safe_reference_normalizer.dart';

/// Fetches a URL and extracts readable text content as markdown.
///
/// Handles timeouts, content-length limits, and HTML-to-text conversion
/// with a lightweight built-in extractor (no external dependency).
class WebFetchTool implements AssistantTool {
  WebFetchTool({http.Client? client, RetrievalBroker? broker})
    : _client = client ?? http.Client(),
      _broker = broker;

  final http.Client _client;
  final RetrievalBroker? _broker;
  static const Duration _timeout = Duration(seconds: 12);
  static const int _defaultMaxChars = 10000;
  static const int _absoluteMaxChars = 50000;

  @override
  String get name => 'web_fetch';

  @override
  String get description =>
      'Fetch URL content and convert to readable markdown.';

  @override
  Future<AssistantToolResult> execute(AssistantToolArguments arguments) async {
    final request = WebFetchToolArgs.fromAssistantArguments(arguments);
    final broker = _broker;
    if (broker != null) {
      final result = await broker.fetch(request.toRetrievalFetchRequest());
      return _sanitizeBrokerFetchResult(request: request, result: result);
    }
    final url = request.url.trim();
    if (url.isEmpty) {
      return AssistantToolResult(
        success: false,
        message: 'Missing required parameter: url',
        errorCode: AssistantErrorCode.invalidArguments,
        runtimeFailure: assistantToolRuntimeFailure(
          errorCode: AssistantErrorCode.invalidArguments,
          message: 'Missing required parameter: url',
          functionModule: name,
          stage: 'argument_validation',
        ),
      );
    }

    final maxChars =
        request.maxChars?.clamp(100, _absoluteMaxChars) ?? _defaultMaxChars;

    try {
      final uri = Uri.parse(url);
      if (!uri.hasScheme || (!uri.isScheme('http') && !uri.isScheme('https'))) {
        return AssistantToolResult(
          success: false,
          message: 'Invalid URL scheme: only http/https supported',
          errorCode: AssistantErrorCode.invalidArguments,
          runtimeFailure: assistantToolRuntimeFailure(
            errorCode: AssistantErrorCode.invalidArguments,
            message: 'Invalid URL scheme: only http/https supported',
            functionModule: name,
            stage: 'argument_validation',
          ),
        );
      }

      final response = await _client
          .get(uri, headers: _buildHeaders())
          .timeout(_timeout);

      if (response.statusCode != 200) {
        if (kDebugMode) {
          debugPrint('[WebFetchTool] HTTP ${response.statusCode}: $url');
        }
        final errorCode = _statusCodeToErrorCode(response.statusCode);
        _emitConsoleReadableFetchLog(
          request: <String, dynamic>{
            'url': url,
            'method': 'GET',
            'headers': _buildHeaders(),
            'maxChars': maxChars,
          },
          response: <String, dynamic>{
            'statusCode': response.statusCode,
            'headers': response.headers,
            'body': _decodeResponseBody(response),
          },
          hasError: true,
        );
        return AssistantToolResult(
          success: false,
          message: _statusCodeToMessage(response.statusCode, url),
          errorCode: errorCode,
          degraded: errorCode != AssistantErrorCode.invalidArguments,
          data: WebFetchFailurePayload(
            statusCode: response.statusCode,
          ).toResultData(),
          runtimeFailure: assistantToolRuntimeFailure(
            errorCode: errorCode,
            message: _statusCodeToMessage(response.statusCode, url),
            functionModule: name,
            stage: 'http_response',
          ),
        );
      }

      final contentType = response.headers['content-type'] ?? '';
      final isHtml = contentType.contains('text/html');
      final isText =
          contentType.contains('text/') ||
          contentType.contains('application/json') ||
          contentType.contains('application/xml');

      if (!isHtml && !isText) {
        _emitConsoleReadableFetchLog(
          request: <String, dynamic>{
            'url': url,
            'method': 'GET',
            'headers': _buildHeaders(),
            'maxChars': maxChars,
          },
          response: <String, dynamic>{
            'statusCode': response.statusCode,
            'headers': response.headers,
            'contentType': contentType,
          },
          hasError: true,
          error: 'Unsupported content type: $contentType',
        );
        return AssistantToolResult(
          success: false,
          message: 'Unsupported content type: $contentType',
          errorCode: AssistantErrorCode.unsupportedTarget,
          degraded: true,
          data: WebFetchFailurePayload(contentType: contentType).toResultData(),
          runtimeFailure: assistantToolRuntimeFailure(
            errorCode: AssistantErrorCode.unsupportedTarget,
            message: 'Unsupported content type: $contentType',
            functionModule: name,
            stage: 'content_type_validation',
          ),
        );
      }

      final rawBody = _decodeResponseBody(response);
      final title = isHtml ? _extractTitle(rawBody) : '';
      final bodyText = isHtml ? _htmlToPlainText(rawBody) : rawBody;
      final truncated = bodyText.length > maxChars;
      final content = truncated ? bodyText.substring(0, maxChars) : bodyText;
      final charCount = content.length;
      final sourceHost = uri.host.toLowerCase().trim();
      final searchPlanId = request.searchPlanId.trim();
      final dimension = request.dimension.trim();
      final snippet = content.length <= 180
          ? content
          : '${content.substring(0, 180)}...';

      if (kDebugMode) {
        debugPrint(
          '[WebFetchTool] OK: $url ($charCount chars, truncated=$truncated)',
        );
      }

      final safeReference = SafeReferenceNormalizer.normalize(<String, dynamic>{
        'title': title,
        'url': url,
        'source': sourceHost,
        'snippet': snippet,
      });
      final canonicalUrl = (safeReference?['url'] as String?)?.trim() ?? url;
      final canonicalTitle =
          (safeReference?['title'] as String?)?.trim() ?? title;
      final canonicalSource =
          (safeReference?['source'] as String?)?.trim() ?? sourceHost;
      final canonicalSourceHost =
          (safeReference?['sourceHost'] as String?)?.trim() ?? sourceHost;
      final retrievedAt = DateTime.now().toIso8601String();
      final references = safeReference == null
          ? const <WebFetchReference>[]
          : <WebFetchReference>[
              WebFetchReference.fromJson(<String, Object?>{
                ...safeReference,
                'sourceTier': 'page',
                'searchPlanId': searchPlanId,
                'dimension': dimension,
                'retrievedAt': retrievedAt,
              }),
            ];
      final payload = WebFetchToolSuccessPayload(
        url: canonicalUrl,
        title: canonicalTitle,
        source: canonicalSource,
        content: content,
        summary: snippet,
        charCount: charCount,
        truncated: truncated,
        contentType: contentType,
        sourceHost: canonicalSourceHost,
        sourceTier: 'page',
        searchPlanId: searchPlanId,
        dimension: dimension,
        references: references,
      );
      _emitConsoleReadableFetchLog(
        request: <String, dynamic>{
          'url': url,
          'method': 'GET',
          'headers': _buildHeaders(),
          'maxChars': maxChars,
          if (searchPlanId.isNotEmpty) 'searchPlanId': searchPlanId,
          if (dimension.isNotEmpty) 'dimension': dimension,
        },
        response: <String, dynamic>{
          'statusCode': response.statusCode,
          'headers': response.headers,
          'payload': payload.toResultData(),
        },
        hasError: false,
      );
      return AssistantToolResult(
        success: true,
        message: '已阅读 $charCount 字内容${truncated ? "（已截断）" : ""}',
        data: payload.toResultData(),
      );
    } on FormatException {
      _emitConsoleReadableFetchLog(
        request: <String, dynamic>{'url': url, 'maxChars': maxChars},
        response: const <String, dynamic>{},
        hasError: true,
        error: 'Invalid URL format',
      );
      return AssistantToolResult(
        success: false,
        message: 'Invalid URL format: $url',
        errorCode: AssistantErrorCode.invalidArguments,
        runtimeFailure: assistantToolRuntimeFailure(
          errorCode: AssistantErrorCode.invalidArguments,
          message: 'Invalid URL format: $url',
          functionModule: name,
          stage: 'argument_validation',
        ),
      );
    } on TimeoutException {
      if (kDebugMode) {
        debugPrint('[WebFetchTool] timeout: $url');
      }
      _emitConsoleReadableFetchLog(
        request: <String, dynamic>{'url': url, 'maxChars': maxChars},
        response: const <String, dynamic>{},
        hasError: true,
        error: 'timeout',
      );
      return AssistantToolResult(
        success: false,
        message: '网页加载超时，请稍后重试',
        errorCode: AssistantErrorCode.networkUnavailable,
        degraded: true,
        runtimeFailure: assistantToolRuntimeFailure(
          errorCode: AssistantErrorCode.networkUnavailable,
          message: '网页加载超时，请稍后重试',
          functionModule: name,
          stage: 'http_timeout',
        ),
      );
    } on http.ClientException catch (e) {
      if (kDebugMode) {
        debugPrint('[WebFetchTool] client error: $url — $e');
      }
      _emitConsoleReadableFetchLog(
        request: <String, dynamic>{'url': url, 'maxChars': maxChars},
        response: const <String, dynamic>{},
        hasError: true,
        error: e.toString(),
      );
      return AssistantToolResult(
        success: false,
        message: '网页读取失败，网络连接异常',
        errorCode: AssistantErrorCode.networkUnavailable,
        degraded: true,
        data: WebFetchFailurePayload(detail: e.message).toResultData(),
        runtimeFailure: assistantToolRuntimeFailure(
          errorCode: AssistantErrorCode.networkUnavailable,
          message: '网页读取失败，网络连接异常',
          functionModule: name,
          stage: 'http_client',
        ),
      );
    } catch (e) {
      if (kDebugMode) {
        debugPrint('[WebFetchTool] error: $url — $e');
      }
      _emitConsoleReadableFetchLog(
        request: <String, dynamic>{'url': url, 'maxChars': maxChars},
        response: const <String, dynamic>{},
        hasError: true,
        error: e.toString(),
      );
      return AssistantToolResult(
        success: false,
        message: '网页读取失败: $e',
        errorCode: AssistantErrorCode.executionFailed,
        degraded: true,
        runtimeFailure: assistantToolRuntimeFailure(
          errorCode: AssistantErrorCode.executionFailed,
          message: '网页读取失败: $e',
          functionModule: name,
          stage: 'unexpected_exception',
        ),
      );
    }
  }

  void _emitConsoleReadableFetchLog({
    required Map<String, dynamic> request,
    required Map<String, dynamic> response,
    required bool hasError,
    String error = '',
  }) {
    assert(() {
      final searchPlanId = (request['searchPlanId'] as String?)?.trim() ?? '';
      final header = StringBuffer('[AssistantSearch][fetch] ');
      header.write(hasError ? 'ERROR' : 'OK');
      header.write(' stage=retrieval_processing');
      header.write(' tool=web_fetch');
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
      if (error.trim().isNotEmpty) {
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

  AssistantToolResult _sanitizeBrokerFetchResult({
    required WebFetchToolArgs request,
    required RetrievalFetchResult result,
  }) {
    final brokerPayload = result.payloadOrNull;
    if (brokerPayload == null) {
      final toolResult = result.toToolResult();
      if (toolResult.success || toolResult.runtimeFailure != null) {
        return toolResult;
      }
      return AssistantToolResult(
        success: toolResult.success,
        message: toolResult.message,
        data: toolResult.data,
        errorCode: toolResult.errorCode,
        degraded: toolResult.degraded,
        runtimeFailure: assistantToolRuntimeFailure(
          errorCode: toolResult.errorCode,
          message: toolResult.message,
          functionModule: name,
          stage: 'broker_fetch',
        ),
      );
    }
    final sanitizedPayload = _sanitizeBrokerFetchPayload(
      request: request,
      payload: brokerPayload,
    );
    return AssistantToolResult(
      success: result.success,
      message: result.message,
      data: sanitizedPayload.toResultData(),
      errorCode: result.errorCode,
      degraded: result.degraded,
      runtimeFailure: result.success
          ? null
          : assistantToolRuntimeFailure(
              errorCode: result.errorCode,
              message: result.message,
              functionModule: name,
              stage: 'broker_fetch',
            ),
    );
  }

  WebFetchToolSuccessPayload _sanitizeBrokerFetchPayload({
    required WebFetchToolArgs request,
    required RetrievalFetchResultPayload payload,
  }) {
    final fallbackSnippet = payload.summary.trim().isNotEmpty
        ? payload.summary.trim()
        : _snippetOfFetchContent(payload.content);
    final normalizedRefs = payload.references
        .map(
          (item) => _normalizeFetchReference(
            raw: WebFetchReference.fromRetrievalReference(item),
            fallbackUrl: payload.url.trim().isNotEmpty
                ? payload.url
                : request.url,
            fallbackTitle: payload.title,
            fallbackSource: payload.source.trim().isNotEmpty
                ? payload.source
                : payload.sourceHost,
            fallbackSnippet: item.snippet.trim().isNotEmpty
                ? item.snippet
                : fallbackSnippet,
            searchPlanId: item.searchPlanId.trim().isNotEmpty
                ? item.searchPlanId
                : (payload.searchPlanId.trim().isNotEmpty
                      ? payload.searchPlanId
                      : request.searchPlanId),
            dimension: item.dimension.trim().isNotEmpty
                ? item.dimension
                : (payload.dimension.trim().isNotEmpty
                      ? payload.dimension
                      : request.dimension),
            sourceTier: item.sourceTier.trim().isNotEmpty
                ? item.sourceTier
                : (payload.sourceTier.trim().isNotEmpty
                      ? payload.sourceTier
                      : 'page'),
            retrievedAt: item.retrievedAt.trim().isNotEmpty
                ? item.retrievedAt
                : DateTime.now().toIso8601String(),
          ),
        )
        .whereType<WebFetchReference>()
        .toList(growable: false);
    final references = normalizedRefs.isNotEmpty
        ? normalizedRefs
        : (() {
            final fallback = _normalizeFetchReference(
              raw: const WebFetchReference(),
              fallbackUrl: payload.url.trim().isNotEmpty
                  ? payload.url
                  : request.url,
              fallbackTitle: payload.title,
              fallbackSource: payload.source.trim().isNotEmpty
                  ? payload.source
                  : payload.sourceHost,
              fallbackSnippet: fallbackSnippet,
              searchPlanId: payload.searchPlanId.trim().isNotEmpty
                  ? payload.searchPlanId
                  : request.searchPlanId,
              dimension: payload.dimension.trim().isNotEmpty
                  ? payload.dimension
                  : request.dimension,
              sourceTier: payload.sourceTier.trim().isNotEmpty
                  ? payload.sourceTier
                  : 'page',
              retrievedAt: DateTime.now().toIso8601String(),
            );
            return fallback == null
                ? const <WebFetchReference>[]
                : <WebFetchReference>[fallback];
          })();
    final primary = references.isNotEmpty ? references.first : null;
    return WebFetchToolSuccessPayload(
      url: primary?.url.trim().isNotEmpty == true
          ? primary!.url
          : (payload.url.trim().isNotEmpty ? payload.url : request.url),
      title: primary?.title.trim().isNotEmpty == true
          ? primary!.title
          : payload.title,
      source: primary?.source.trim().isNotEmpty == true
          ? primary!.source
          : payload.source,
      content: payload.content,
      summary: primary?.snippet.trim().isNotEmpty == true
          ? primary!.snippet
          : fallbackSnippet,
      charCount: payload.charCount ?? payload.content.length,
      truncated: payload.truncated,
      contentType: payload.contentType,
      sourceHost: primary?.sourceHost.trim().isNotEmpty == true
          ? primary!.sourceHost
          : payload.sourceHost,
      sourceTier: primary?.sourceTier.trim().isNotEmpty == true
          ? primary!.sourceTier
          : (payload.sourceTier.trim().isNotEmpty
                ? payload.sourceTier
                : 'page'),
      searchPlanId: primary?.searchPlanId.trim().isNotEmpty == true
          ? primary!.searchPlanId
          : (payload.searchPlanId.trim().isNotEmpty
                ? payload.searchPlanId
                : request.searchPlanId),
      dimension: primary?.dimension.trim().isNotEmpty == true
          ? primary!.dimension
          : (payload.dimension.trim().isNotEmpty
                ? payload.dimension
                : request.dimension),
      references: references,
    );
  }

  WebFetchReference? _normalizeFetchReference({
    required WebFetchReference raw,
    required String fallbackUrl,
    required String fallbackTitle,
    required String fallbackSource,
    required String fallbackSnippet,
    required String searchPlanId,
    required String dimension,
    required String sourceTier,
    required String retrievedAt,
  }) {
    final normalized = SafeReferenceNormalizer.normalize(<String, dynamic>{
      'url': raw.url.trim().isNotEmpty ? raw.url.trim() : fallbackUrl,
      'title': raw.title.trim().isNotEmpty ? raw.title.trim() : fallbackTitle,
      'source': raw.source.trim().isNotEmpty
          ? raw.source.trim()
          : fallbackSource,
      'snippet': raw.snippet.trim().isNotEmpty
          ? raw.snippet.trim()
          : fallbackSnippet,
    });
    if (normalized == null) return null;
    return WebFetchReference.fromJson(<String, Object?>{
      ...normalized,
      'sourceTier': sourceTier,
      'searchPlanId': searchPlanId,
      'dimension': dimension,
      'retrievedAt': retrievedAt,
    });
  }

  String _snippetOfFetchContent(String raw) {
    final content = raw.trim();
    if (content.isEmpty) return '';
    if (content.length <= 180) return content;
    return '${content.substring(0, 180)}...';
  }

  Map<String, String> _buildHeaders() => <String, String>{
    'User-Agent':
        'Mozilla/5.0 (compatible; QuwoquanBot/1.0; +https://quwoquan.com)',
    'Accept': 'text/html,application/xhtml+xml,text/plain,application/json',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
  };

  AssistantErrorCode _statusCodeToErrorCode(int statusCode) {
    if (statusCode == 401 || statusCode == 403) {
      return AssistantErrorCode.unauthorized;
    }
    if (statusCode == 429) {
      return AssistantErrorCode.rateLimited;
    }
    if (statusCode >= 500) {
      return AssistantErrorCode.networkUnavailable;
    }
    return AssistantErrorCode.executionFailed;
  }

  String _statusCodeToMessage(int statusCode, String url) {
    if (statusCode == 401 || statusCode == 403) {
      return '目标页面拒绝访问：$url';
    }
    if (statusCode == 404) {
      return '目标页面不存在：$url';
    }
    if (statusCode == 429) {
      return '目标站点请求过于频繁，请稍后重试';
    }
    if (statusCode >= 500) {
      return '目标站点暂时不可用，请稍后重试';
    }
    return 'HTTP $statusCode fetching $url';
  }

  static String _extractTitle(String html) {
    final match = RegExp(
      r'<title[^>]*>(.*?)</title>',
      caseSensitive: false,
      dotAll: true,
    ).firstMatch(html);
    if (match == null) return '';
    return _decodeEntities(match.group(1)?.trim() ?? '');
  }

  static String _htmlToPlainText(String html) {
    var text = html;
    text = text.replaceAll(
      RegExp(
        r'<(script|style|noscript)[^>]*>[\s\S]*?</\1>',
        caseSensitive: false,
      ),
      '',
    );
    text = text.replaceAll(RegExp(r'<!--[\s\S]*?-->'), '');
    text = text.replaceAll(
      RegExp(
        r'</(p|div|h[1-6]|li|tr|blockquote|section|article|header|footer|nav|aside)>',
        caseSensitive: false,
      ),
      '\n',
    );
    text = text.replaceAll(RegExp(r'<br\s*/?>', caseSensitive: false), '\n');
    text = text.replaceAll(RegExp(r'<[^>]+>'), '');
    text = _decodeEntities(text);
    text = text.replaceAll(RegExp(r'[ \t]+'), ' ');
    text = text.replaceAll(RegExp(r'\n{3,}'), '\n\n');
    return text.trim();
  }

  static String _decodeEntities(String text) {
    var result = text
        .replaceAll('&amp;', '&')
        .replaceAll('&lt;', '<')
        .replaceAll('&gt;', '>')
        .replaceAll('&quot;', '"')
        .replaceAll('&#39;', "'")
        .replaceAll('&apos;', "'")
        .replaceAll('&nbsp;', ' ');
    result = result.replaceAllMapped(RegExp(r'&#(\d+);'), (m) {
      final code = int.tryParse(m.group(1) ?? '');
      return code != null ? String.fromCharCode(code) : m.group(0)!;
    });
    result = result.replaceAllMapped(RegExp(r'&#x([0-9a-fA-F]+);'), (m) {
      final code = int.tryParse(m.group(1) ?? '', radix: 16);
      return code != null ? String.fromCharCode(code) : m.group(0)!;
    });
    return result;
  }

  String _decodeResponseBody(http.Response response) {
    final contentType = response.headers['content-type'] ?? '';
    final headerCharset = RegExp(
      r'charset=([^\s;]+)',
      caseSensitive: false,
    ).firstMatch(contentType)?.group(1);
    final preview = ascii.decode(
      response.bodyBytes.take(2048).toList(growable: false),
      allowInvalid: true,
    );
    final metaCharset = RegExp(
      "<meta[^>]+charset=[\"']?([^\"'>\\s]+)",
      caseSensitive: false,
    ).firstMatch(preview)?.group(1);
    final charset = (headerCharset ?? metaCharset ?? 'utf-8').toLowerCase();
    final encoding =
        Encoding.getByName(charset) ??
        (charset.contains('utf') ? utf8 : latin1);
    try {
      return encoding.decode(response.bodyBytes);
    } catch (_) {
      return utf8.decode(response.bodyBytes, allowMalformed: true);
    }
  }
}
