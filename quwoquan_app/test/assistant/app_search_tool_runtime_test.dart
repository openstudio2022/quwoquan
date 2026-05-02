import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/app_search_contract.dart';
import 'package:quwoquan_app/assistant/tool/impl/app/app_search_tool.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_contract.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_registry.g.dart';
import 'package:quwoquan_app/core/models/search_hit_payload.dart';
import 'package:quwoquan_app/core/services/search_repository.dart';

void main() {
  test('app_search tool executes against in-app search repository', () async {
    final repository = _CapturingSearchRepository();
    final tool = AppSearchTool(searchRepository: repository);

    final result = await tool.execute(
      AssistantToolArguments.fromJson(
        const AppSearchRequest(
          query: '查我和张三昨天聊过什么',
          contentTypes: <AppSearchContentType>[
            AppSearchContentType.chatMessage,
          ],
          filters: AppSearchFilters(
            username: '张三',
            keywords: <String>['聚餐', '餐厅'],
          ),
          sort: AppSearchSortMode.latest,
          pageSize: 5,
        ).toJson(),
      ),
    );

    final response = AppSearchResponse.fromJson(
      result.data?.toDynamicJson() ?? const <String, dynamic>{},
    );

    expect(result.success, isTrue);
    expect(repository.lastRequest, isNotNull);
    expect(repository.lastRequest!.query, '查我和张三昨天聊过什么 聚餐 餐厅 张三');
    expect(repository.lastRequest!.objectTypes, <SearchObjectType>{
      SearchObjectType.chatMessage,
    });
    expect(repository.lastRequest!.limit, 6);
    expect(response.results, hasLength(1));
    expect(
      response.results.single.contentType,
      AppSearchContentType.chatMessage,
    );
    expect(response.results.single.body, '我们去那家餐厅吧');
    expect(response.results.single.profile, '张三');
    expect(response.nextPageToken, isEmpty);
  });

  test(
    'app_search applies filters, latest sort and page token locally',
    () async {
      final repository = _CapturingSearchRepository();
      final tool = AppSearchTool(searchRepository: repository);

      final firstPage = await tool.execute(
        AssistantToolArguments.fromJson(
          const AppSearchRequest(
            query: '行程',
            contentTypes: <AppSearchContentType>[AppSearchContentType.post],
            filters: AppSearchFilters(
              timeStart: '2026-04-20T00:00:00.000',
              timeEnd: '2026-04-30T23:59:59.999',
              userId: 'user_me',
              keywords: <String>['行程'],
              isMine: true,
            ),
            sort: AppSearchSortMode.latest,
            pageSize: 1,
          ).toJson(),
        ),
      );
      final firstResponse = AppSearchResponse.fromJson(
        firstPage.data?.toDynamicJson() ?? const <String, dynamic>{},
      );

      expect(firstResponse.results, hasLength(1));
      expect(firstResponse.results.single.contentId, 'post_recent');
      expect(firstResponse.nextPageToken, 'page:2');

      final secondPage = await tool.execute(
        AssistantToolArguments.fromJson(
          AppSearchRequest(
            query: '行程',
            contentTypes: const <AppSearchContentType>[
              AppSearchContentType.post,
            ],
            filters: const AppSearchFilters(
              timeStart: '2026-04-20T00:00:00.000',
              timeEnd: '2026-04-30T23:59:59.999',
              userId: 'user_me',
              keywords: <String>['行程'],
              isMine: true,
            ),
            sort: AppSearchSortMode.latest,
            pageSize: 1,
            nextPageToken: firstResponse.nextPageToken,
          ).toJson(),
        ),
      );
      final secondResponse = AppSearchResponse.fromJson(
        secondPage.data?.toDynamicJson() ?? const <String, dynamic>{},
      );

      expect(secondResponse.results, hasLength(1));
      expect(secondResponse.results.single.contentId, 'post_old');
      expect(secondResponse.nextPageToken, isEmpty);
    },
  );
}

class _CapturingSearchRepository implements SearchRepository {
  SearchRequest? lastRequest;

  @override
  Future<SearchResponse> search(SearchRequest request) async {
    lastRequest = request.normalized();
    return SearchResponse(
      request: lastRequest!,
      sections: <SearchSection>[
        SearchSection(
          id: 'messages',
          title: '聊天消息',
          objectTypes: const <SearchObjectType>[SearchObjectType.chatMessage],
          hits: const <SearchHit>[
            SearchHit(
              objectType: SearchObjectType.chatMessage,
              objectId: 'msg_1',
              title: '昨晚聚餐消息',
              snippet: '我们去那家餐厅吧',
              resolvedFrom: SearchResolvedFrom.local,
              matchedField: 'body',
              payload: SearchHitPayloadWireMap(<String, dynamic>{
                'messageId': 'msg_1',
                'contentPreview': '我们去那家餐厅吧',
                'senderDisplayName': '张三',
              }),
            ),
            SearchHit(
              objectType: SearchObjectType.contentPost,
              objectId: 'post_old',
              title: '旧行程',
              snippet: '行程安排 A',
              resolvedFrom: SearchResolvedFrom.remote,
              payload: SearchHitPayloadWireMap(<String, dynamic>{
                'body': '行程安排 A',
                'authorUserId': 'user_me',
                'isMine': true,
                'createdAt': '2026-04-21T09:00:00.000',
              }),
            ),
            SearchHit(
              objectType: SearchObjectType.contentPost,
              objectId: 'post_recent',
              title: '新行程',
              snippet: '行程安排 B',
              resolvedFrom: SearchResolvedFrom.remote,
              payload: SearchHitPayloadWireMap(<String, dynamic>{
                'body': '行程安排 B',
                'authorUserId': 'user_me',
                'isMine': true,
                'createdAt': '2026-04-25T09:00:00.000',
              }),
            ),
            SearchHit(
              objectType: SearchObjectType.contentPost,
              objectId: 'post_other',
              title: '别人的行程',
              snippet: '行程安排 C',
              resolvedFrom: SearchResolvedFrom.remote,
              payload: SearchHitPayloadWireMap(<String, dynamic>{
                'body': '行程安排 C',
                'authorUserId': 'user_other',
                'isMine': false,
                'createdAt': '2026-04-26T09:00:00.000',
              }),
            ),
          ],
          resolvedFrom: SearchResolvedFrom.local,
        ),
      ],
    );
  }
}
