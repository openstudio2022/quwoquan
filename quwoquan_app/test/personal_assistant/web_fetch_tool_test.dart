import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_schema.dart';
import 'package:quwoquan_app/personal_assistant/tools/web_fetch_tool.dart';

void main() {
  group('WebFetchTool', () {
    late WebFetchTool tool;

    test('name and description', () {
      tool = WebFetchTool();
      expect(tool.name, 'web_fetch');
      expect(tool.description, isNotEmpty);
    });

    test('rejects empty url', () async {
      tool = WebFetchTool();
      final result = await tool.execute(<String, dynamic>{});
      expect(result.success, false);
      expect(result.errorCode, AssistantErrorCode.invalidArguments);
    });

    test('rejects non-http scheme', () async {
      tool = WebFetchTool();
      final result = await tool.execute(<String, dynamic>{'url': 'ftp://example.com'});
      expect(result.success, false);
      expect(result.errorCode, AssistantErrorCode.invalidArguments);
    });

    test('fetches HTML and extracts title + text', () async {
      final mockClient = MockClient((request) async {
        return http.Response(
          '<html><head><title>Test Page</title></head>'
          '<body><p>Hello world</p><script>var x=1;</script></body></html>',
          200,
          headers: {'content-type': 'text/html; charset=utf-8'},
        );
      });
      tool = WebFetchTool(client: mockClient);
      final result = await tool.execute(<String, dynamic>{
        'url': 'https://example.com/page',
      });
      expect(result.success, true);
      expect(result.data?['title'], 'Test Page');
      expect(result.data?['content'], contains('Hello world'));
      expect(result.data?['content'], isNot(contains('var x=1')));
      expect(result.data?['url'], 'https://example.com/page');
      expect(result.data?['charCount'], isA<int>());
    });

    test('fetches JSON content', () async {
      final mockClient = MockClient((request) async {
        return http.Response(
          jsonEncode({'weather': 'sunny', 'temp': 25}),
          200,
          headers: {'content-type': 'application/json'},
        );
      });
      tool = WebFetchTool(client: mockClient);
      final result = await tool.execute(<String, dynamic>{
        'url': 'https://api.example.com/data',
      });
      expect(result.success, true);
      expect(result.data?['content'], contains('sunny'));
    });

    test('respects maxChars truncation', () async {
      final longBody = 'A' * 500;
      final mockClient = MockClient((request) async {
        return http.Response(
          longBody,
          200,
          headers: {'content-type': 'text/plain'},
        );
      });
      tool = WebFetchTool(client: mockClient);
      final result = await tool.execute(<String, dynamic>{
        'url': 'https://example.com/long',
        'maxChars': 100,
      });
      expect(result.success, true);
      expect(result.data?['truncated'], true);
      expect(result.data?['charCount'], 100);
    });

    test('handles non-200 status', () async {
      final mockClient = MockClient((request) async {
        return http.Response('Not found', 404);
      });
      tool = WebFetchTool(client: mockClient);
      final result = await tool.execute(<String, dynamic>{
        'url': 'https://example.com/missing',
      });
      expect(result.success, false);
      expect(result.data?['statusCode'], 404);
    });

    test('handles unsupported content type', () async {
      final mockClient = MockClient((request) async {
        return http.Response(
          'binary data',
          200,
          headers: {'content-type': 'application/octet-stream'},
        );
      });
      tool = WebFetchTool(client: mockClient);
      final result = await tool.execute(<String, dynamic>{
        'url': 'https://example.com/file.bin',
      });
      expect(result.success, false);
      expect(result.message, contains('Unsupported content type'));
    });

    test('decodes HTML entities', () async {
      final mockClient = MockClient((request) async {
        return http.Response(
          '<html><body><p>Tom &amp; Jerry &lt;3&gt;</p></body></html>',
          200,
          headers: {'content-type': 'text/html'},
        );
      });
      tool = WebFetchTool(client: mockClient);
      final result = await tool.execute(<String, dynamic>{
        'url': 'https://example.com/entities',
      });
      expect(result.success, true);
      expect(result.data?['content'], contains('Tom & Jerry'));
    });

    test('requiredOutputPaths are present on success', () async {
      final mockClient = MockClient((request) async {
        return http.Response(
          '<html><body>Content</body></html>',
          200,
          headers: {'content-type': 'text/html'},
        );
      });
      tool = WebFetchTool(client: mockClient);
      final result = await tool.execute(<String, dynamic>{
        'url': 'https://example.com',
      });
      expect(result.success, true);
      final data = result.data!;
      expect(data.containsKey('url'), true);
      expect(data.containsKey('content'), true);
    });
  });
}
