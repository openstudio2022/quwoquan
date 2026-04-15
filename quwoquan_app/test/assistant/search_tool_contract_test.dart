import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/tool/impl/search/search_tool_contract.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_contract.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_registry.g.dart';

void main() {
  group('SearchTool contract', () {
    test('typed arguments parse public fields and isolate bridge payload', () {
      final contract = SearchToolArgumentsContract.fromAssistantArguments(
        AssistantToolArguments.fromJson(<String, dynamic>{
          SearchToolFieldNames.query: 'A股 大涨 原因',
          SearchToolFieldNames.mode: SearchMode.result.wireValue,
          SearchToolFieldNames.objectTypes: <String>['web.document'],
          SearchToolFieldNames.limit: 4,
          SearchToolFieldNames.queryVariants: <String>[
            'A股 大涨 原因',
            '2026-04-07 A股 大涨 原因',
          ],
          SearchToolFieldNames.queryTasks: <Map<String, dynamic>>[
            <String, dynamic>{
              'id': 'market_reason',
              'label': '盘面原因',
              'dimension': 'latest_signal',
              'query': '2026-04-07 A股 大涨 原因',
            },
          ],
          'provider': 'serpapi',
          'queryNormalization': <String, dynamic>{
            'normalizedQuery': '2026-04-07 A股 大涨 原因',
          },
        }),
      );

      expect(contract.query, 'A股 大涨 原因');
      expect(contract.mode, SearchMode.result);
      expect(contract.objectTypes, contains(SearchObjectType.webDocument));
      expect(contract.limit, 4);
      expect(contract.queryVariants.length, 2);
      expect(contract.queryTasks.single.id, 'market_reason');
      expect(contract.queryTasks.single.dimension, 'latest_signal');
      expect(contract.bridgePayload['provider'], 'serpapi');
      expect(contract.bridgePayload['queryNormalization'], isA<Map>());

      final webArgs = contract.toWebSearchArguments(
        query: '2026-04-07 A股 大涨 原因',
        count: 4,
        queryTasks: contract.queryTasks,
      );
      expect(webArgs['query'], '2026-04-07 A股 大涨 原因');
      expect(webArgs['count'], 4);
      expect(webArgs['provider'], 'serpapi');
      expect((webArgs['queryTasks'] as List?)?.length, 1);
    });

    test('typed result payload serializes references and query tasks', () {
      const payload = SearchToolResultPayload(
        query: '摄影 入门',
        mode: SearchMode.result,
        objectTypes: <SearchObjectType>{SearchObjectType.webDocument},
        references: <SearchToolReference>[
          SearchToolReference(
            title: '摄影百科',
            url: 'https://example.com/photo',
            source: 'example.com',
            snippet: '网页资料',
            queryTaskId: 'facts',
            dimension: 'key_facts',
          ),
        ],
        queryTasks: <SearchToolQueryTask>[
          SearchToolQueryTask(
            id: 'facts',
            label: '关键事实',
            dimension: 'key_facts',
            query: '摄影 入门 关键事实',
          ),
        ],
      );

      final data = payload.toAssistantToolResultData();
      expect(data['contractVersion'], searchToolContractVersion);
      final references = (data['references'] as List?)?.whereType<Map>().toList();
      expect(references, isNotNull);
      expect(references, isNotEmpty);
      expect(references!.first['url'], 'https://example.com/photo');
      expect(references.first['queryTaskId'], 'facts');
      final queryTasks = (data[SearchToolFieldNames.queryTasks] as List?)
          ?.whereType<Map>()
          .toList();
      expect(queryTasks, isNotNull);
      expect(queryTasks!.single['dimension'], 'key_facts');
    });
  });
}
