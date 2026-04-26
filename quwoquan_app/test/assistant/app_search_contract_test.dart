import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/app_search_contract.dart';

void main() {
  group('AppSearch contract', () {
    test('request round-trips orthogonal filters', () {
      const request = AppSearchRequest(
        query: '张三 昨天 聚餐',
        contentTypes: <AppSearchContentType>[
          AppSearchContentType.chatMessage,
          AppSearchContentType.post,
        ],
        filters: AppSearchFilters(
          timeStart: '2026-04-24T00:00:00+08:00',
          timeEnd: '2026-04-25T00:00:00+08:00',
          username: '张三',
          keywords: <String>['聚餐', '餐厅'],
          isMine: true,
        ),
        page: 2,
        pageSize: 20,
        nextPageToken: 'page:2',
        sort: AppSearchSortMode.latest,
      );

      final decoded = AppSearchRequest.fromJson(request.toJson());

      expect(decoded.contractId, 'app_search_request');
      expect(decoded.query, '张三 昨天 聚餐');
      expect(decoded.contentTypes, <AppSearchContentType>[
        AppSearchContentType.chatMessage,
        AppSearchContentType.post,
      ]);
      expect(decoded.filters.username, '张三');
      expect(decoded.filters.keywords, <String>['聚餐', '餐厅']);
      expect(decoded.filters.isMine, isTrue);
      expect(decoded.page, 2);
      expect(decoded.pageSize, 20);
      expect(decoded.nextPageToken, 'page:2');
      expect(decoded.sort, AppSearchSortMode.latest);
    });

    test('request drops unsupported content types', () {
      final decoded = AppSearchRequest.fromJson(<String, dynamic>{
        'query': '浏览过的文章',
        'contentTypes': <String>['history_post', 'unknown_type', 'user'],
      });

      expect(decoded.contentTypes, <AppSearchContentType>[
        AppSearchContentType.historyPost,
        AppSearchContentType.user,
      ]);
    });

    test('response round-trips full-detail-inline results', () {
      const response = AppSearchResponse(
        results: <AppSearchResultItem>[
          AppSearchResultItem(
            contentType: AppSearchContentType.historyPost,
            contentId: 'post_123',
            title: '深圳周末活动',
            body: '你昨天浏览过这篇活动推荐',
            timestamp: '2026-04-24T18:00:00+08:00',
            profile: '深圳活动号',
            tags: <String>['同城', '活动'],
          ),
        ],
        nextPageToken: 'next_1',
      );

      final decoded = AppSearchResponse.fromJson(response.toJson());

      expect(decoded.contractId, 'app_search_response');
      expect(decoded.results, hasLength(1));
      expect(
        decoded.results.single.contentType,
        AppSearchContentType.historyPost,
      );
      expect(decoded.results.single.contentId, 'post_123');
      expect(decoded.results.single.body, '你昨天浏览过这篇活动推荐');
      expect(decoded.results.single.timestamp, '2026-04-24T18:00:00+08:00');
      expect(decoded.results.single.profile, '深圳活动号');
      expect(decoded.results.single.tags, <String>['同城', '活动']);
      expect(decoded.nextPageToken, 'next_1');
    });
  });
}
