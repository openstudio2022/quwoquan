import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/retrieval/domain/retrieval_broker.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';
import 'package:quwoquan_app/assistant/tool/impl/web/web_fetch_tool.dart';
import 'package:quwoquan_app/assistant/tool/impl/web/websearch_tool.dart';

class _FakeRetrievalBroker implements RetrievalBroker {
  RetrievalSearchRequest? lastSearchRequest;
  RetrievalFetchRequest? lastFetchRequest;
  RetrievalSearchResult searchResult = RetrievalSearchResult(
    success: true,
    message: 'search ok',
    data: AssistantToolResultData.fromJson(<String, dynamic>{
      'provider': 'fake',
      'references': <Map<String, dynamic>>[],
    }),
  );
  RetrievalFetchResult fetchResult = RetrievalFetchResult(
    success: true,
    message: 'fetch ok',
    data: AssistantToolResultData.fromJson(<String, dynamic>{
      'url': 'https://example.com',
      'content': 'hello',
    }),
  );

  @override
  Future<RetrievalFetchResult> fetch(RetrievalFetchRequest request) async {
    lastFetchRequest = request;
    return fetchResult;
  }

  @override
  Future<RetrievalSearchResult> search(RetrievalSearchRequest request) async {
    lastSearchRequest = request;
    return searchResult;
  }
}

void main() {
  group('RetrievalBroker bootstrap delegation', () {
    test('WebSearchTool 可委派给 broker', () async {
      final broker = _FakeRetrievalBroker();
      broker.searchResult = RetrievalSearchResult(
        success: true,
        message: 'search ok',
        data: AssistantToolResultData.fromJson(<String, dynamic>{
          'provider': 'fake',
          'references': <Map<String, dynamic>>[
            <String, dynamic>{
              'title': '深圳天气预报',
              'url':
                  'https://duckduckgo.com/l/?uddg=https%3A%2F%2Fweather.cma.cn%2Fshenzhen%3Futm_source%3Dfeed',
              'source': '中国气象局',
              'snippet': '深圳今天晴，约 25°C。',
            },
          ],
        }),
      );
      final tool = WebSearchTool(broker: broker);

      final result = await tool.execute(
        AssistantToolArguments.fromJson(<String, dynamic>{
          'query': '深圳天气',
          'count': 3,
          'taskGraphSearchPlan': <Map<String, dynamic>>[
            <String, dynamic>{
              'id': 'weather_now',
              'dimension': 'latest_signal',
              'query': '深圳天气 中国气象局',
            },
          ],
        }),
      );

      expect(result.success, isTrue);
      expect(result.message, equals('search ok'));
      expect(broker.lastSearchRequest?.query, equals('深圳天气'));
      expect(broker.lastSearchRequest?.count, equals(3));
      expect(broker.lastSearchRequest?.queryPlans, hasLength(1));
      expect(broker.lastSearchRequest?.queryPlans.single.id, equals('weather_now'));
      final references =
          (result.data?['references'] as List?)
              ?.whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      expect(references, isNotEmpty);
      expect(
        references.first['url'],
        equals('https://weather.cma.cn/shenzhen'),
      );
      expect(references.first['source'], equals('中国气象局'));
      expect(references.first['sourceHost'], equals('weather.cma.cn'));
    });

    test('WebFetchTool 可委派给 broker', () async {
      final broker = _FakeRetrievalBroker();
      broker.fetchResult = RetrievalFetchResult(
        success: true,
        message: 'fetch ok',
        data: AssistantToolResultData.fromJson(<String, dynamic>{
          'url':
              'https://duckduckgo.com/l/?uddg=https%3A%2F%2Fweather.cma.cn%2Fforecast%3Futm_medium%3Dcard',
          'title': '深圳天气预报',
          'source': '中国气象局',
          'content': '深圳今天晴，约 25°C。',
        }),
      );
      final tool = WebFetchTool(broker: broker);

      final result = await tool.execute(
        AssistantToolArguments.fromJson(<String, dynamic>{
          'url': 'https://example.com',
          'maxChars': 1200,
        }),
      );

      expect(result.success, isTrue);
      expect(result.message, equals('fetch ok'));
      expect(broker.lastFetchRequest?.url, equals('https://example.com'));
      expect(broker.lastFetchRequest?.maxChars, equals(1200));
      expect(result.data?['url'], equals('https://weather.cma.cn/forecast'));
      expect(result.data?['source'], equals('中国气象局'));
      final references =
          (result.data?['references'] as List?)
              ?.whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      expect(references, isNotEmpty);
      expect(references.first['sourceHost'], equals('weather.cma.cn'));
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
