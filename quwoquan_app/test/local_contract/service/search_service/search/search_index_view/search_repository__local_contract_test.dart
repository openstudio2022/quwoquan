// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/search-execution-routing-policy/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/canonical_search_query_facet.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/adapters/remote_search_repository.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/search_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('canonical Search wire 直接消费服务端 content typed slice', () {
    final result = decodeSearchResponseView(<String, Object?>{
      'hits': <Object?>[
        <String, Object?>{
          'target': 'article',
          'objectType': 'content.post',
          'objectId': 'post-typed-1',
          'title': '川西路线',
          'score': 1,
          'matchedTerms': <String>['川西'],
          'matchedTags': <String>[],
          'evidence': <Object?>[
            <String, Object?>{'field': 'title', 'snippet': '川西路线'},
          ],
          'rankReasons': <Object?>[
            <String, Object?>{
              'code': 'term_heat',
              'label': '热词相关',
              'weight': 1,
            },
          ],
          'content': <String, Object?>{
            'postId': 'post-typed-1',
            'contentType': 'article',
            'contentIdentity': 'work',
            'coverUrl': 'https://cdn.example/typed.jpg',
            'likeCount': 12,
          },
        },
      ],
      'citations': <Object?>[],
      'facets': <Object?>[],
      'degradeSignals': <Object?>[],
      'provenance': <String, Object?>{
        'provider': 'elasticsearch',
        'generatedAt': '2026-07-31T00:00:00Z',
      },
      'relatedTerms': <String>[],
      'requestId': 'search-request-typed',
    });

    final hit = result.hits.single;
    expect(hit.content?.coverUrl, 'https://cdn.example/typed.jpg');
    expect(hit.content?.contentType, ContentType.article);
    expect(hit.content?.contentIdentity, ContentIdentity.work);
    expect(hit.payload, isNull);
  });

  test('content hit 禁止 payload 旧轨与未声明 wire 字段', () {
    Map<String, Object?> hit({bool withRetiredField = false}) =>
        <String, Object?>{
          'target': 'article',
          'objectType': 'content.post',
          'objectId': 'post-retired-1',
          'title': '旧轨结果',
          'score': 1,
          'matchedTerms': <String>[],
          'matchedTags': <String>[],
          'evidence': <Object?>[],
          'rankReasons': <Object?>[],
          'payload': <String, Object?>{'coverUrl': 'https://retired.invalid'},
          if (withRetiredField) 'coverWidth': 1200,
        };

    Object envelope(Map<String, Object?> item) => <String, Object?>{
      'hits': <Object?>[item],
      'citations': <Object?>[],
      'facets': <Object?>[],
      'degradeSignals': <Object?>[],
      'provenance': <String, Object?>{
        'provider': 'elasticsearch',
        'generatedAt': '2026-07-31T00:00:00Z',
      },
      'relatedTerms': <String>[],
      'requestId': 'search-request-retired',
    };

    expect(
      () => decodeSearchResponseView(envelope(hit())),
      throwsA(isA<FormatException>()),
    );
    expect(
      () => decodeSearchResponseView(envelope(hit(withRetiredField: true))),
      throwsA(isA<FormatException>()),
    );
  });

  test('suggest 与 result 都只调用 canonical Search Facet', () async {
    final facet = _RecordingCanonicalSearchFacet();
    final repository = RemoteSearchRepository(
      remoteQuery: facet,
      sessionIdProvider: () => 'search-session',
    );

    await repository.search(
      SearchRequest(query: '川西', mode: CanonicalSearchMode.suggest),
    );
    await repository.search(
      SearchRequest(query: '川西', mode: CanonicalSearchMode.result),
    );

    expect(facet.queries.map((query) => query.mode), <CanonicalSearchMode>[
      CanonicalSearchMode.suggest,
      CanonicalSearchMode.result,
    ]);
  });

  test('content hit 只从 typed content slice 映射且保留搜索归因', () async {
    final facet = _RecordingCanonicalSearchFacet(
      result: SearchResponseView(
        provenance: CanonicalSearchProvenance(
          provider: 'elasticsearch',
          generatedAt: DateTime.utc(2026, 7, 31),
        ),
        requestId: 'search-request-1',
        relatedTerms: const <String>['川西徒步'],
        hits: <CanonicalSearchHit>[
          CanonicalSearchHit(
            target: 'article',
            objectType: 'content.post',
            objectId: 'post-1',
            title: '川西路线',
            snippet: '路线摘要',
            score: 1,
            matchedTerms: const <String>['川西'],
            matchedTags: const <String>[],
            evidence: <CanonicalSearchEvidence>[
              CanonicalSearchEvidence(field: 'title', snippet: '川西路线'),
            ],
            rankReasons: <CanonicalSearchRankReason>[
              CanonicalSearchRankReason(
                code: 'term_heat',
                label: 'term_heat',
                weight: 1,
              ),
            ],
            rankPosition: 1,
            connectionState: 'connected',
            content: CanonicalSearchContentHit(
              postId: 'post-1',
              contentType: ContentType.article,
              title: '川西路线',
              summary: '路线摘要',
              likeCount: 0,
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
          SearchRequest(
            query: '川西',
            mode: CanonicalSearchMode.result,
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
    final response =
        await RemoteSearchRepository(
          remoteQuery: _RecordingCanonicalSearchFacet(),
          sessionIdProvider: () => 'search-session',
        ).search(
          SearchRequest(query: '川西', mode: CanonicalSearchMode.result),
        );

    expect(response.relatedTerms, isEmpty);
  });

  test('canonical Facet 错误保持失败，不伪装空结果', () async {
    final repository = RemoteSearchRepository(
      remoteQuery: _ThrowingCanonicalSearchFacet(),
      sessionIdProvider: () => 'search-session',
    );

    await expectLater(
      repository.search(
        SearchRequest(query: '川西', mode: CanonicalSearchMode.result),
      ),
      throwsA(isA<StateError>()),
    );
  });
}

final class _RecordingCanonicalSearchFacet
    implements CanonicalSearchQueryFacet {
  _RecordingCanonicalSearchFacet({SearchResponseView? result})
    : result =
          result ??
          SearchResponseView(
            provenance: CanonicalSearchProvenance(
              provider: 'elasticsearch',
              generatedAt: DateTime.utc(2026, 7, 31),
            ),
            requestId: 'search-request-empty',
          );

  final SearchResponseView result;
  final List<CanonicalSearchQuery> queries = <CanonicalSearchQuery>[];

  @override
  Future<SearchResponseView> search(
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
  Future<SearchResponseView> search(
    CanonicalSearchQuery query, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) {
    throw StateError('canonical search unavailable');
  }
}
