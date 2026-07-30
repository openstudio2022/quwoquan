// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/search-execution-routing-policy/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_contract.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_registry.g.dart';
import 'package:quwoquan_app/core/services/remote_search_repository.dart';
import 'package:quwoquan_app/core/services/search_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('suggest 与 result 都只调用 canonical Search Facet', () async {
    final facet = _RecordingCanonicalSearchFacet();
    final repository = RemoteSearchRepository(
      remoteQuery: facet,
      sessionIdProvider: () => 'search-session',
    );

    await repository.search(
      const SearchRequest(query: '川西', mode: SearchMode.suggest),
    );
    await repository.search(
      const SearchRequest(query: '川西', mode: SearchMode.result),
    );

    expect(facet.queries.map((query) => query.mode), <CanonicalSearchMode>[
      CanonicalSearchMode.suggest,
      CanonicalSearchMode.result,
    ]);
  });

  test('content hit 只从 typed content slice 映射且保留搜索归因', () async {
    final facet = _RecordingCanonicalSearchFacet(
      result: CanonicalSearchResult(
        requestId: 'search-request-1',
        relatedTerms: const <String>['川西徒步'],
        hits: <CanonicalSearchHit>[
          CanonicalSearchHit(
            target: 'article',
            objectId: 'post-1',
            title: '川西路线',
            snippet: '路线摘要',
            rankReasons: const <String>['term_heat'],
            rankPosition: 1,
            coverWidth: 1200,
            coverHeight: 800,
            content: const CanonicalSearchContentHit(
              postId: 'post-1',
              contentType: 'article',
              title: '川西路线',
              summary: '路线摘要',
              connectionState: 'connected',
            ),
          ),
        ],
      ),
    );
    final response =
        await RemoteSearchRepository(
          remoteQuery: facet,
          sessionIdProvider: () => 'search-session',
        ).search(
          const SearchRequest(
            query: '川西',
            mode: SearchMode.result,
            objectTypes: <SearchObjectType>{SearchObjectType.contentPost},
          ),
        );

    expect(response.searchRequestId, 'search-request-1');
    expect(response.relatedTerms, <String>['川西徒步']);
    expect(response.hits, hasLength(1));
    final hit = response.hits.single;
    expect(hit.rankReasons, <String>['term_heat']);
    expect(hit.rankPosition, 1);
    expect(hit.asContentPostItem?.postId, 'post-1');
    expect(hit.asContentPostItem?.connectionState, 'connected');
  });

  test('relatedTerms 为空时不在客户端合成词', () async {
    final response = await RemoteSearchRepository(
      remoteQuery: _RecordingCanonicalSearchFacet(),
      sessionIdProvider: () => 'search-session',
    ).search(const SearchRequest(query: '川西', mode: SearchMode.result));

    expect(response.relatedTerms, isEmpty);
  });

  test('canonical Facet 错误保持失败，不伪装空结果', () async {
    final repository = RemoteSearchRepository(
      remoteQuery: _ThrowingCanonicalSearchFacet(),
      sessionIdProvider: () => 'search-session',
    );

    await expectLater(
      repository.search(
        const SearchRequest(query: '川西', mode: SearchMode.result),
      ),
      throwsA(isA<StateError>()),
    );
  });
}

final class _RecordingCanonicalSearchFacet
    implements CanonicalSearchQueryFacet {
  _RecordingCanonicalSearchFacet({CanonicalSearchResult? result})
    : result =
          result ??
          CanonicalSearchResult(
            hits: const <CanonicalSearchHit>[],
            requestId: 'search-request-empty',
          );

  final CanonicalSearchResult result;
  final List<CanonicalSearchQuery> queries = <CanonicalSearchQuery>[];

  @override
  Future<CanonicalSearchResult> search(
    CanonicalSearchQuery query, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    queries.add(query);
    return result;
  }
}

final class _ThrowingCanonicalSearchFacet implements CanonicalSearchQueryFacet {
  @override
  Future<CanonicalSearchResult> search(
    CanonicalSearchQuery query, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) {
    throw StateError('canonical search unavailable');
  }
}
