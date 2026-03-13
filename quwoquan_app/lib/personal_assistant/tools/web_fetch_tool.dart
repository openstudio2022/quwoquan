import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/personal_assistant/retrieval/retrieval_broker.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_schema.dart';

/// Fetches a URL and extracts readable text content as markdown.
///
/// Handles timeouts, content-length limits, and HTML-to-text conversion
/// with a lightweight built-in extractor (no external dependency).
class WebFetchTool implements AssistantTool {
  WebFetchTool({
    http.Client? client,
    RetrievalBroker? broker,
  }) : _client = client ?? http.Client(),
       _broker = broker;

  final http.Client _client;
  final RetrievalBroker? _broker;
  static const Duration _timeout = Duration(seconds: 12);
  static const int _defaultMaxChars = 10000;
  static const int _absoluteMaxChars = 50000;

  @override
  String get name => 'web_fetch';

  @override
  String get description => 'Fetch URL content and convert to readable markdown.';

  @override
  Future<AssistantToolResult> execute(Map<String, dynamic> arguments) async {
    final broker = _broker;
    if (broker != null) {
      final result = await broker.fetch(
        RetrievalFetchRequest.fromToolArguments(arguments),
      );
      return result.toToolResult();
    }
    final url = (arguments['url'] as String?)?.trim() ?? '';
    if (url.isEmpty) {
      return const AssistantToolResult(
        success: false,
        message: 'Missing required parameter: url',
        errorCode: AssistantErrorCode.invalidArguments,
      );
    }

    final maxChars = (arguments['maxChars'] as int?)
            ?.clamp(100, _absoluteMaxChars) ??
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
      final isText = contentType.contains('text/') ||
          contentType.contains('application/json') ||
          contentType.contains('application/xml');

      if (!isHtml && !isText) {
        return AssistantToolResult(
          success: false,
          message: 'Unsupported content type: $contentType',
          errorCode: AssistantErrorCode.executionFailed,
          data: <String, dynamic>{'contentType': contentType},
        );
      }

      final rawBody = response.body;
      final title = isHtml ? _extractTitle(rawBody) : '';
      final bodyText = isHtml ? _htmlToPlainText(rawBody) : rawBody;
      final truncated = bodyText.length > maxChars;
      final content = truncated ? bodyText.substring(0, maxChars) : bodyText;
      final charCount = content.length;
      final sourceHost = uri.host.toLowerCase().trim();
      final queryTaskId = (arguments['queryTaskId'] as String?)?.trim() ?? '';
      final dimension = (arguments['dimension'] as String?)?.trim() ?? '';
      final snippet = content.length <= 180 ? content : '${content.substring(0, 180)}...';

      if (kDebugMode) {
        debugPrint('[WebFetchTool] OK: $url ($charCount chars, truncated=$truncated)');
      }

      return AssistantToolResult(
        success: true,
        message: '已阅读 $charCount 字内容${truncated ? "（已截断）" : ""}',
        data: <String, dynamic>{
          'url': url,
          'title': title,
          'content': content,
          'summary': snippet,
          'charCount': charCount,
          'truncated': truncated,
          'contentType': contentType,
          'sourceHost': sourceHost,
          'sourceTier': 'page',
          'queryTaskId': queryTaskId,
          'dimension': dimension,
          'references': <Map<String, dynamic>>[
            <String, dynamic>{
              'title': title.isNotEmpty ? title : url,
              'url': url,
              'source': sourceHost,
              'sourceHost': sourceHost,
              'sourceTier': 'page',
              'snippet': snippet,
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
      RegExp(r'<(script|style|noscript)[^>]*>[\s\S]*?</\1>', caseSensitive: false),
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
}
