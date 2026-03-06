import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/personal_assistant/tools/tool_schema.dart';

/// Fetches a URL and extracts readable text content as markdown.
///
/// Handles timeouts, content-length limits, and HTML-to-text conversion
/// with a lightweight built-in extractor (no external dependency).
class WebFetchTool implements AssistantTool {
  WebFetchTool({http.Client? client}) : _client = client ?? http.Client();

  final http.Client _client;
  static const Duration _timeout = Duration(seconds: 12);
  static const int _defaultMaxChars = 10000;
  static const int _absoluteMaxChars = 50000;

  @override
  String get name => 'web_fetch';

  @override
  String get description => 'Fetch URL content and convert to readable markdown.';

  @override
  Future<AssistantToolResult> execute(Map<String, dynamic> arguments) async {
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
        return AssistantToolResult(
          success: false,
          message: 'HTTP ${response.statusCode} fetching $url',
          errorCode: AssistantErrorCode.executionFailed,
          data: <String, dynamic>{'statusCode': response.statusCode},
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
          'charCount': charCount,
          'truncated': truncated,
          'contentType': contentType,
        },
      );
    } on FormatException {
      return AssistantToolResult(
        success: false,
        message: 'Invalid URL format: $url',
        errorCode: AssistantErrorCode.invalidArguments,
      );
    } catch (e) {
      final isTimeout = e.toString().contains('TimeoutException');
      if (kDebugMode) {
        debugPrint('[WebFetchTool] error: $url — $e');
      }
      return AssistantToolResult(
        success: false,
        message: isTimeout ? '网页加载超时，请稍后重试' : '网页读取失败: $e',
        errorCode: isTimeout
            ? AssistantErrorCode.networkUnavailable
            : AssistantErrorCode.executionFailed,
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
