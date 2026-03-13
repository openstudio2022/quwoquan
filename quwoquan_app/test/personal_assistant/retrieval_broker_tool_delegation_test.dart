import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/personal_assistant/retrieval/retrieval_broker.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_schema.dart';
import 'package:quwoquan_app/personal_assistant/tools/web_fetch_tool.dart';
import 'package:quwoquan_app/personal_assistant/tools/websearch_tool.dart';

class _FakeRetrievalBroker implements RetrievalBroker {
  RetrievalSearchRequest? lastSearchRequest;
  RetrievalFetchRequest? lastFetchRequest;

  @override
  Future<RetrievalFetchResult> fetch(RetrievalFetchRequest request) async {
    lastFetchRequest = request;
    return const RetrievalFetchResult(
      success: true,
      message: 'fetch ok',
      data: <String, dynamic>{'url': 'https://example.com', 'content': 'hello'},
    );
  }

  @override
  Future<RetrievalSearchResult> search(RetrievalSearchRequest request) async {
    lastSearchRequest = request;
    return const RetrievalSearchResult(
      success: true,
      message: 'search ok',
      data: <String, dynamic>{
        'provider': 'fake',
        'references': <Map<String, dynamic>>[],
      },
    );
  }
}

void main() {
  group('RetrievalBroker bootstrap delegation', () {
    test('WebSearchTool 可委派给 broker', () async {
      final broker = _FakeRetrievalBroker();
      final tool = WebSearchTool(broker: broker);

      final result = await tool.execute(<String, dynamic>{
        'query': '深圳天气',
        'count': 3,
      });

      expect(result.success, isTrue);
      expect(result.message, equals('search ok'));
      expect(broker.lastSearchRequest?.query, equals('深圳天气'));
      expect(broker.lastSearchRequest?.count, equals(3));
    });

    test('WebFetchTool 可委派给 broker', () async {
      final broker = _FakeRetrievalBroker();
      final tool = WebFetchTool(broker: broker);

      final result = await tool.execute(<String, dynamic>{
        'url': 'https://example.com',
        'maxChars': 1200,
      });

      expect(result.success, isTrue);
      expect(result.message, equals('fetch ok'));
      expect(broker.lastFetchRequest?.url, equals('https://example.com'));
      expect(broker.lastFetchRequest?.maxChars, equals(1200));
    });

    test('broker result 可回转为 AssistantToolResult', () {
      const searchResult = RetrievalSearchResult(
        success: false,
        message: 'rate limited',
        errorCode: AssistantErrorCode.rateLimited,
        degraded: true,
      );

      final toolResult = searchResult.toToolResult();
      expect(toolResult.errorCode, AssistantErrorCode.rateLimited);
      expect(toolResult.degraded, isTrue);
    });
  });
}
