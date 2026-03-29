import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/tool/impl/search/search_tool.dart';
import 'package:quwoquan_app/assistant/tool/impl/web/websearch_tool.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_contract.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_registry.g.dart';
import 'package:quwoquan_app/core/services/search_repository.dart';

void main() {
  test(
    'search tool merges web and internal hits under one query-first schema',
    () async {
      final tool = SearchTool(
        searchRepository: _FakeSearchRepository(),
        webSearchTool: _FakeWebSearchTool(),
      );

      final result = await tool.execute(<String, dynamic>{
        'query': '摄影',
        'mode': 'result',
        'objectTypes': <String>['web.document', 'content.post'],
        'limit': 5,
      });

      expect(result.success, isTrue);
      expect(result.data?['mode'], equals('result'));
      expect((result.data?['sections'] as List?)?.length, equals(2));
      expect((result.data?['hits'] as List?)?.length, equals(2));
      expect((result.data?['references'] as List?)?.length, equals(1));
      expect(result.data?['summary'], isNotEmpty);
      expect(result.data?['queryCount'], equals(1));
    },
  );

  test(
    'search tool supports multi query tasks and merges dimensions',
    () async {
      final tool = SearchTool(
        searchRepository: _FakeSearchRepository(),
        webSearchTool: _FakeWebSearchTool(),
      );

      final result = await tool.execute(<String, dynamic>{
        'query': '摄影',
        'mode': 'result',
        'objectTypes': <String>['web.document', 'content.post'],
        'queryTasks': <Map<String, dynamic>>[
          <String, dynamic>{
            'id': 'facts',
            'label': '关键事实',
            'dimension': '关键事实',
            'query': '摄影 关键事实',
          },
          <String, dynamic>{
            'id': 'risks',
            'label': '风险边界',
            'dimension': '风险边界',
            'query': '摄影 风险 注意事项',
          },
        ],
      });

      expect(result.success, isTrue);
      expect(result.data?['queryCount'], equals(2));
      expect((result.data?['coveredDimensions'] as List?)?.length, equals(2));
      expect(result.data?['summary'], contains('关键事实'));
    },
  );

  test(
    'search tool defaults invalid mode to result and filters conversation type',
    () async {
      final repository = _CapturingSearchRepository();
      final tool = SearchTool(
        searchRepository: repository,
        webSearchTool: _FakeWebSearchTool(),
      );

      final result = await tool.execute(<String, dynamic>{
        SearchToolFieldNames.query: '摄影',
        SearchToolFieldNames.mode: 'unexpected_mode',
        SearchToolFieldNames.objectTypes: <String>['content.post'],
        SearchToolFieldNames.conversationType: 'broadcast',
      });

      expect(result.success, isTrue);
      expect(repository.lastRequest, isNotNull);
      expect(repository.lastRequest!.mode, equals(SearchMode.result));
      expect(repository.lastRequest!.conversationType, isNull);
    },
  );

  test(
    'search tool result defaults include circle and location coverage',
    () async {
      final repository = _CapturingSearchRepository();
      final tool = SearchTool(
        searchRepository: repository,
        webSearchTool: _FakeWebSearchTool(),
      );

      final result = await tool.execute(<String, dynamic>{
        SearchToolFieldNames.query: '西湖',
        SearchToolFieldNames.mode: SearchMode.result.wireValue,
      });

      expect(result.success, isTrue);
      expect(repository.lastRequest, isNotNull);
      expect(
        repository.lastRequest!.objectTypes.contains(
          SearchObjectType.circleCircle,
        ),
        isTrue,
      );
      expect(
        repository.lastRequest!.objectTypes.contains(
          SearchObjectType.integrationLocationPoi,
        ),
        isTrue,
      );
    },
  );
}

class _FakeSearchRepository implements SearchRepository {
  @override
  Future<SearchResponse> search(SearchRequest request) async {
    return SearchResponse(
      request: request.normalized(),
      sections: <SearchSection>[
        SearchSection(
          id: 'content',
          title: '内容',
          objectTypes: const <SearchObjectType>[SearchObjectType.contentPost],
          hits: const <SearchHit>[
            SearchHit(
              objectType: SearchObjectType.contentPost,
              objectId: 'post_1',
              title: '摄影入门',
              subtitle: '站内内容',
              resolvedFrom: SearchResolvedFrom.remote,
              payload: <String, dynamic>{
                'postId': 'post_1',
                'contentType': 'article',
                'title': '摄影入门',
                'summary': '站内内容',
              },
            ),
          ],
          resolvedFrom: SearchResolvedFrom.remote,
        ),
      ],
    );
  }
}

class _CapturingSearchRepository extends _FakeSearchRepository {
  SearchRequest? lastRequest;

  @override
  Future<SearchResponse> search(SearchRequest request) async {
    lastRequest = request.normalized();
    return super.search(request);
  }
}

class _FakeWebSearchTool extends WebSearchTool {
  _FakeWebSearchTool();

  @override
  Future<AssistantToolResult> execute(Map<String, dynamic> arguments) async {
    return const AssistantToolResult(
      success: true,
      message: 'ok',
      data: <String, dynamic>{
        'references': <Map<String, dynamic>>[
          <String, dynamic>{
            'title': '摄影百科',
            'url': 'https://example.com/photo',
            'source': 'example.com',
            'snippet': '网页资料',
          },
        ],
      },
    );
  }
}
