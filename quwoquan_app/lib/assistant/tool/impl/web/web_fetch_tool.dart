import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/assistant/retrieval/domain/retrieval_broker.dart';
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
  Future<AssistantToolResult> execute(Map<String, dynamic> arguments) async {
    final broker = _broker;
    if (broker != null) {
      final request = RetrievalFetchRequest.fromToolArguments(arguments);
      final result = await broker.fetch(request);
      return _sanitizeBrokerFetchResult(request: request, result: result);
    }
    final url = (arguments['url'] as String?)?.trim() ?? '';
    if (url.isEmpty) {
      return const AssistantToolResult(
        success: false,
        message: 'Missing required parameter: url',
        errorCode: AssistantErrorCode.invalidArguments,
      );
    }

    final maxChars =
        (arguments['maxChars'] as int?)?.clamp(100, _absoluteMaxChars) ??
        _defaultMaxChars;

    try {
      final uri = Uri.parse(url);
      if (!uri.hasScheme || (!uri.isScheme('http') && !uri.isScheme('https'))) {
        return const AssistantToolResult(
          success: false,
          message: 'Invalid URL scheme: only http/https supported',
          errorCode: AssistantErrorCode.invalidArguments,
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
        return AssistantToolResult(
          success: false,
          message: _statusCodeToMessage(response.statusCode, url),
          errorCode: errorCode,
          degraded: errorCode != AssistantErrorCode.invalidArguments,
          data: <String, dynamic>{
            'statusCode': response.statusCode,
            'retryable': _isRetryableStatusCode(response.statusCode),
          },
        );
      }

      final contentType = response.headers['content-type'] ?? '';
      final isHtml = contentType.contains('text/html');
      final isText =
          contentType.contains('text/') ||
          contentType.contains('application/json') ||
          contentType.contains('application/xml');

      if (!isHtml && !isText) {
        return AssistantToolResult(
          success: false,
          message: 'Unsupported content type: $contentType',
          errorCode: AssistantErrorCode.unsupportedTarget,
          degraded: true,
          data: <String, dynamic>{'contentType': contentType},
        );
      }

      final rawBody = _decodeResponseBody(response);
      final title = isHtml ? _extractTitle(rawBody) : '';
      final bodyText = isHtml ? _htmlToPlainText(rawBody) : rawBody;
      final truncated = bodyText.length > maxChars;
      final content = truncated ? bodyText.substring(0, maxChars) : bodyText;
      final charCount = content.length;
      final sourceHost = uri.host.toLowerCase().trim();
      final queryTaskId = (arguments['queryTaskId'] as String?)?.trim() ?? '';
      final dimension = (arguments['dimension'] as String?)?.trim() ?? '';
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
      return AssistantToolResult(
        success: true,
        message: '已阅读 $charCount 字内容${truncated ? "（已截断）" : ""}',
        data: <String, dynamic>{
          'url': canonicalUrl,
          'title': canonicalTitle,
          'source': canonicalSource,
          'content': content,
          'summary': snippet,
          'charCount': charCount,
          'truncated': truncated,
          'contentType': contentType,
          'sourceHost': canonicalSourceHost,
          'sourceTier': 'page',
          'queryTaskId': queryTaskId,
          'dimension': dimension,
          'references': safeReference == null
              ? const <Map<String, dynamic>>[]
              : <Map<String, dynamic>>[
                  <String, dynamic>{
                    ...safeReference,
                    'sourceTier': 'page',
                    'queryTaskId': queryTaskId,
                    'dimension': dimension,
                    'retrievedAt': DateTime.now().toIso8601String(),
                  },
                ],
        },
      );
    } on FormatException {
      return AssistantToolResult(
        success: false,
        message: 'Invalid URL format: $url',
        errorCode: AssistantErrorCode.invalidArguments,
      );
    } on TimeoutException {
      if (kDebugMode) {
        debugPrint('[WebFetchTool] timeout: $url');
      }
      return const AssistantToolResult(
        success: false,
        message: '网页加载超时，请稍后重试',
        errorCode: AssistantErrorCode.networkUnavailable,
        degraded: true,
      );
    } on http.ClientException catch (e) {
      if (kDebugMode) {
        debugPrint('[WebFetchTool] client error: $url — $e');
      }
      return AssistantToolResult(
        success: false,
        message: '网页读取失败，网络连接异常',
        errorCode: AssistantErrorCode.networkUnavailable,
        degraded: true,
        data: <String, dynamic>{'detail': e.message},
      );
    } catch (e) {
      if (kDebugMode) {
        debugPrint('[WebFetchTool] error: $url — $e');
      }
      return AssistantToolResult(
        success: false,
        message: '网页读取失败: $e',
        errorCode: AssistantErrorCode.executionFailed,
        degraded: true,
      );
    }
  }

  AssistantToolResult _sanitizeBrokerFetchResult({
    required RetrievalFetchRequest request,
    required RetrievalFetchResult result,
  }) {
    final toolResult = result.toToolResult();
    final rawData = toolResult.data;
    if (rawData == null || rawData.isEmpty) return toolResult;
    final sanitizedData = Map<String, dynamic>.from(rawData);
    final references = _sanitizeBrokerFetchReferences(
      data: sanitizedData,
      fallbackUrl: request.url,
      queryTaskId: (request.arguments['queryTaskId'] as String?)?.trim() ?? '',
      dimension: (request.arguments['dimension'] as String?)?.trim() ?? '',
    );
    if (references.isNotEmpty) {
      final primary = references.first;
      sanitizedData['references'] = references;
      sanitizedData['url'] = (primary['url'] as String?)?.trim() ?? request.url;
      sanitizedData['title'] = (primary['title'] as String?)?.trim() ?? '';
      sanitizedData['source'] = (primary['source'] as String?)?.trim() ?? '';
      sanitizedData['sourceHost'] =
          (primary['sourceHost'] as String?)?.trim() ?? '';
      sanitizedData['summary'] = (primary['snippet'] as String?)?.trim() ?? '';
      sanitizedData['queryTaskId'] =
          (primary['queryTaskId'] as String?)?.trim() ??
          ((sanitizedData['queryTaskId'] as String?)?.trim() ?? '');
      sanitizedData['dimension'] =
          (primary['dimension'] as String?)?.trim() ??
          ((sanitizedData['dimension'] as String?)?.trim() ?? '');
      sanitizedData['sourceTier'] =
          (primary['sourceTier'] as String?)?.trim().isNotEmpty == true
          ? (primary['sourceTier'] as String).trim()
          : ((sanitizedData['sourceTier'] as String?)?.trim().isNotEmpty == true
                ? (sanitizedData['sourceTier'] as String).trim()
                : 'page');
    }
    return AssistantToolResult(
      success: toolResult.success,
      message: toolResult.message,
      data: sanitizedData,
      errorCode: toolResult.errorCode,
      degraded: toolResult.degraded,
    );
  }

  List<Map<String, dynamic>> _sanitizeBrokerFetchReferences({
    required Map<String, dynamic> data,
    required String fallbackUrl,
    required String queryTaskId,
    required String dimension,
  }) {
    final view = BrokerWebFetchResultDataView(data);
    final rawRefs = view.referenceMaps;
    final normalizedRefs = rawRefs
        .map(
          (item) => _normalizeFetchReference(
            raw: item,
            fallbackUrl: fallbackUrl,
            fallbackTitle: view.title,
            fallbackSource: view.source.isNotEmpty
                ? view.source
                : view.sourceHost,
            fallbackSnippet:
                (item['snippet'] as String?)?.trim().isNotEmpty == true
                ? (item['snippet'] as String).trim()
                : (view.summary.isNotEmpty
                      ? view.summary
                      : _snippetOfFetchContent(view.content)),
            queryTaskId:
                (item['queryTaskId'] as String?)?.trim().isNotEmpty == true
                ? (item['queryTaskId'] as String).trim()
                : queryTaskId,
            dimension: (item['dimension'] as String?)?.trim().isNotEmpty == true
                ? (item['dimension'] as String).trim()
                : dimension,
            sourceTier:
                (item['sourceTier'] as String?)?.trim().isNotEmpty == true
                ? (item['sourceTier'] as String).trim()
                : (view.sourceTier.isNotEmpty ? view.sourceTier : 'page'),
            retrievedAt:
                (item['retrievedAt'] as String?)?.trim().isNotEmpty == true
                ? (item['retrievedAt'] as String).trim()
                : DateTime.now().toIso8601String(),
          ),
        )
        .whereType<Map<String, dynamic>>()
        .toList(growable: false);
    if (normalizedRefs.isNotEmpty) return normalizedRefs;
    final fallback = _normalizeFetchReference(
      raw: const <String, dynamic>{},
      fallbackUrl: view.url.isNotEmpty ? view.url : fallbackUrl,
      fallbackTitle: view.title,
      fallbackSource: view.source.isNotEmpty ? view.source : view.sourceHost,
      fallbackSnippet: view.summary.isNotEmpty
          ? view.summary
          : _snippetOfFetchContent(view.content),
      queryTaskId: queryTaskId,
      dimension: dimension,
      sourceTier: view.sourceTier.isNotEmpty ? view.sourceTier : 'page',
      retrievedAt: DateTime.now().toIso8601String(),
    );
    return fallback == null
        ? const <Map<String, dynamic>>[]
        : <Map<String, dynamic>>[fallback];
  }

  Map<String, dynamic>? _normalizeFetchReference({
    required Map<String, dynamic> raw,
    required String fallbackUrl,
    required String fallbackTitle,
    required String fallbackSource,
    required String fallbackSnippet,
    required String queryTaskId,
    required String dimension,
    required String sourceTier,
    required String retrievedAt,
  }) {
    final normalized = SafeReferenceNormalizer.normalize(<String, dynamic>{
      ...raw,
      'url': (raw['url'] as String?)?.trim().isNotEmpty == true
          ? (raw['url'] as String).trim()
          : fallbackUrl,
      'title': (raw['title'] as String?)?.trim().isNotEmpty == true
          ? (raw['title'] as String).trim()
          : fallbackTitle,
      'source': (raw['source'] as String?)?.trim().isNotEmpty == true
          ? (raw['source'] as String).trim()
          : fallbackSource,
      'snippet': (raw['snippet'] as String?)?.trim().isNotEmpty == true
          ? (raw['snippet'] as String).trim()
          : fallbackSnippet,
    });
    if (normalized == null) return null;
    return <String, dynamic>{
      ...raw,
      ...normalized,
      'sourceTier': sourceTier,
      'queryTaskId': queryTaskId,
      'dimension': dimension,
      'retrievedAt': retrievedAt,
    };
  }

  String _snippetOfFetchContent(Object? raw) {
    final content = raw?.toString().trim() ?? '';
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

  bool _isRetryableStatusCode(int statusCode) {
    return statusCode == 429 || statusCode >= 500;
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
