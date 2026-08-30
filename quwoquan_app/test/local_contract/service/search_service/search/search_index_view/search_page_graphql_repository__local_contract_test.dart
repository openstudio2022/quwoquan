// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-002
// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-002.t1
// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-003.t4
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/api_edge/graphql_read/persisted_query_execution/application/public/persisted_search_page_query.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/adapters/remote_search_page_repository.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/search_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_contracts/generated/gateway_contracts.dart';

void main() {
  test(
    'SearchPage result keeps opaque card/action without legacy hit synthesis',
    () async {
      final facet = _RecordingSearchPageFacet(
        const SearchPageSlice(
          items: <SearchPageItem>[
            SearchPageItem(
              objectRef: 'ref:content-post:opaque-1',
              resultType: SearchPageObjectType.contentPost,
              contentType: SearchPageContentType.article,
              title: '山间路线',
              subtitle: '两日徒步',
              snippet: '从营地出发',
              thumbnailUrl: 'https://cdn.example.test/cover.jpg',
              action: '/posts/opaque-1',
              rankPosition: 1,
              rankReason: '标题命中',
            ),
          ],
          facets: <SearchPageFacet>[
            SearchPageFacet(key: 'CONTENT_POST', count: 1),
          ],
          suggestions: <String>['山间徒步'],
          matchedTerms: <String>['山间'],
          degradeSignals: <SearchPageDegradeSignal>[],
          searchRequestId: 'search.req.test-1',
          nextCursor: 'cursor:opaque-next',
        ),
      );
      final repository = RemoteSearchPageRepository(remoteQuery: facet);

      final response = await repository.search(
        const SearchRequest(
          query: '  山间  ',
          mode: CanonicalSearchMode.result,
          objectTypes: <SearchObjectType>{SearchObjectType.contentPost},
          limit: 50,
        ),
      );

      expect(facet.calls, 1);
      expect(facet.input?.query, '山间');
      expect(facet.input?.first, 20);
      expect(facet.input?.objectTypes, <String>['CONTENT_POST']);
      expect(response.sections, isEmpty);
      expect(response.hits, isEmpty);
      expect(response.pageItems, hasLength(1));
      expect(response.pageItems.single.objectRef, 'ref:content-post:opaque-1');
      expect(response.pageItems.single.action, '/posts/opaque-1');
      expect(
        response.pageItems.single.resultType,
        SearchPageObjectType.contentPost,
      );
      expect(response.pageFacets.single.key, 'CONTENT_POST');
      expect(response.relatedTerms, <String>['山间徒步']);
      expect(response.matchedTerms, <String>['山间']);
      expect(response.pageItems.single.rankPosition, 1);
      expect(response.pageItems.single.rankReason, '标题命中');
      expect(
        response.pageItems.single.contentType,
        SearchPageContentType.article,
      );
      expect(response.nextCursor, 'cursor:opaque-next');
      expect(response.searchRequestId, 'search.req.test-1');
    },
  );

  test('SearchPage remote rejects suggest before any network query', () async {
    final facet = _RecordingSearchPageFacet(
      const SearchPageSlice(
        items: <SearchPageItem>[],
        facets: <SearchPageFacet>[],
        suggestions: <String>[],
        matchedTerms: <String>[],
        degradeSignals: <SearchPageDegradeSignal>[],
        searchRequestId: 'search.req.test-2',
      ),
    );
    final repository = RemoteSearchPageRepository(remoteQuery: facet);

    await expectLater(
      repository.search(const SearchRequest(query: 'a')),
      throwsA(isA<StateError>()),
    );
    expect(facet.calls, 0);
  });
}

final class _RecordingSearchPageFacet implements PersistedSearchPageQuery {
  _RecordingSearchPageFacet(this.result);

  final SearchPageSlice result;
  SearchPageInput? input;
  int calls = 0;

  @override
  Future<SearchPageSlice> searchPage(
    SearchPageInput input, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    calls += 1;
    this.input = input;
    return result;
  }
}
