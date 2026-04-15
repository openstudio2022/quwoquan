import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/retrieval/domain/retrieval_broker.dart';
import 'package:quwoquan_app/assistant/tool/impl/web/web_fetch_tool_contract.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';

void main() {
  group('WebFetchTool contract', () {
    test('typed args map to broker request and back', () {
      final args = WebFetchToolArgs.fromAssistantArguments(
        AssistantToolArguments.fromJson(<String, dynamic>{
          'url': 'https://example.com/page',
          'maxChars': '1200',
          'queryTaskId': 'weather_today',
          'dimension': 'current_state',
        }),
      );

      final request = args.toRetrievalFetchRequest();
      expect(request.url, 'https://example.com/page');
      expect(request.maxChars, 1200);
      expect(request.queryTaskId, 'weather_today');
      expect(request.dimension, 'current_state');

      final roundTrip = args.toAssistantArguments();
      expect(roundTrip['url'], 'https://example.com/page');
      expect(roundTrip['maxChars'], 1200);
      expect(roundTrip['queryTaskId'], 'weather_today');
      expect(roundTrip['dimension'], 'current_state');
    });

    test('success payload can be rebuilt from retrieval payload', () {
      const retrievalPayload = RetrievalFetchResultPayload(
        url: 'https://weather.cma.cn/forecast',
        title: '深圳天气预报',
        source: '中国气象局',
        sourceHost: 'weather.cma.cn',
        content: '深圳今天晴，约 25°C。',
        summary: '深圳今天晴，约 25°C。',
        sourceTier: 'page',
        queryTaskId: 'weather_today',
        dimension: 'current_state',
        references: <RetrievalFetchReference>[
          RetrievalFetchReference(
            url: 'https://weather.cma.cn/forecast',
            title: '深圳天气预报',
            source: '中国气象局',
            sourceHost: 'weather.cma.cn',
            snippet: '深圳今天晴，约 25°C。',
            sourceTier: 'page',
            queryTaskId: 'weather_today',
            dimension: 'current_state',
            retrievedAt: '2026-04-14T10:00:00.000Z',
          ),
        ],
      );

      final payload = WebFetchToolSuccessPayload.fromRetrievalPayload(
        retrievalPayload,
      );
      final data = payload.toResultData();

      expect(payload.url, 'https://weather.cma.cn/forecast');
      expect(payload.references.single.sourceHost, 'weather.cma.cn');
      expect(data['contractVersion'], webFetchToolContractVersion);
      expect(data['queryTaskId'], 'weather_today');
      final refs = (data['references'] as List?)?.whereType<Map>().toList();
      expect(refs, isNotNull);
      expect(refs, isNotEmpty);
      expect(refs!.single['sourceHost'], 'weather.cma.cn');
    });

    test('failure payload keeps typed retry metadata', () {
      const payload = WebFetchFailurePayload(
        statusCode: 429,
        retryable: true,
        detail: 'rate limited',
      );

      final data = payload.toResultData();
      expect(data['contractVersion'], webFetchToolContractVersion);
      expect(data['statusCode'], 429);
      expect(data['retryable'], isTrue);
      expect(data['detail'], 'rate limited');
    });
  });
}
