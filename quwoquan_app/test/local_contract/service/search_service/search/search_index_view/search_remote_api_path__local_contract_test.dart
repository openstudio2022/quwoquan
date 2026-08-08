// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-002
// readiness_case: search_index_view_search_app_local

/// 对象级端云契约：Remote adapter 的 HTTP path 与 generated metadata 对齐。
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/search/search_request_page_ids.g.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/adapters/remote_search_repository.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/adapters/search_query_remote.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/public/search_query_contract.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/search_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../../support/runtime/remote_api_path_test_harness.dart';

http.Response _responseFor(http.Request request) {
  if (request.method == 'POST' &&
      request.url.path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.searchSearchIndexViewSearch,
          )) {
    return remoteApiPathJsonResponse({
      'hits': <Object?>[
        <String, Object?>{
          'target': 'article',
          'objectType': 'content.post',
          'objectId': 'post-search-1',
          'title': '西湖摄影路线',
          'snippet': '晨雾与苏堤的拍摄建议',
          'score': 9.5,
          'matchedTerms': <String>['摄影'],
          'matchedTags': <String>['西湖'],
          'evidence': <Object?>[
            <String, Object?>{'field': 'title', 'snippet': '西湖摄影路线'},
          ],
          'connectionState': 'connected',
          'rankReasons': <Object?>[
            <String, Object?>{
              'code': 'term_heat',
              'label': '热词相关',
              'weight': 1,
            },
          ],
          'rankPosition': 1,
          'content': <String, Object?>{
            'postId': 'post-search-1',
            'contentType': 'article',
            'contentIdentity': 'work',
            'title': '西湖摄影路线',
            'summary': '晨雾与苏堤的拍摄建议',
            'coverUrl': 'https://cdn.example/search/post-search-1.jpg',
            'likeCount': 12,
          },
        },
      ],
      'citations': <dynamic>[],
      'facets': <dynamic>[],
      'requestId': 'search-request-1',
      'relatedTerms': <String>['西湖日出'],
      'experimentBucket': 'search-control',
      'degradeSignals': <dynamic>[],
      'provenance': <String, dynamic>{
        'provider': 'elasticsearch',
        'generatedAt': '2026-07-31T00:00:00Z',
      },
    });
  }
  return remoteApiPathJsonResponse('{}');
}

void main() {
  group('Search adapter — generated operation 路径对齐', () {
    late List<CapturedRemoteApiPathRequest> log;
    late RemoteSearchRepository repository;

    setUp(() {
      log = [];
      final client = buildRemoteApiPathOperationClient(
        log,
        responseFor: _responseFor,
      );
      repository = RemoteSearchRepository(
        remoteQuery: RemoteCanonicalSearchQuery(
          client: client,
          invocationContext: (clientPageId) {
            return CloudOperationInvocationContext(
              surfaceId: AppUiSurfaces.globalSearchNetworkResults.id,
              routeId: AppUiSurfaces.globalSearchNetworkResults.routeId,
              clientPageId: clientPageId,
              actor: const CloudOperationActorContext(personaId: 'persona-1'),
            );
          },
        ),
        sessionIdProvider: () => 'search-session-1',
      );
    });

    test('canonical search → POST /search 并透传 typed 结果', () async {
      final response = await repository.search(
        SearchRequest(
          query: '摄影',
          mode: CanonicalSearchMode.result,
          objectTypes: const <SearchObjectType>{SearchObjectType.contentPost},
          contentTypes: const <SearchContentTypeFilter>{
            SearchContentTypeFilter.article,
          },
          limit: 9,
        ),
      );
      expect(log.last.method, 'POST');
      expect(
        log.last.path,
        canonicalRemoteApiPath(
          AppCloudOperationIds.searchSearchIndexViewSearch,
        ),
      );
      expect(log.last.body['query'], '摄影');
      expect(log.last.body['mode'], 'result');
      expect(log.last.body['objectTypes'], const <String>['article']);
      expect(log.last.body['limit'], 9);
      expect(log.last.headers['X-Session-Id'], 'search-session-1');
      expect(log.last.headers.containsKey('Idempotency-Key'), isFalse);
      expectRemoteApiPathHeaders(
        log.last.headers,
        clientPageId: SearchRequestPageIds.search,
        surfaceId: AppUiSurfaces.globalSearchNetworkResults.id,
        operationId: AppCloudOperationIds.searchSearchIndexViewSearch,
      );
      expect(response.searchRequestId, 'search-request-1');
      expect(response.relatedTerms, <String>['西湖日出']);
      expect(response.hits, hasLength(1));
      final hit = response.hits.single;
      expect(hit.objectId, 'post-search-1');
      expect(hit.rankReasons, <String>['热词相关']);
      expect(hit.rankPosition, 1);
      expect(hit.connectionState, 'connected');
      expect(hit.asContentPostItem?.postId, 'post-search-1');
      expect(
        hit.asContentPostItem?.coverUrl,
        'https://cdn.example/search/post-search-1.jpg',
      );
    });

    test('canonical failure 保持 CloudException，不伪装空结果', () async {
      final client = buildRemoteApiPathOperationClient(
        <CapturedRemoteApiPathRequest>[],
        responseFor: (_) => remoteApiPathJsonResponse(<String, Object?>{
          'code': 'SEARCH.MIDDLEWARE.unavailable',
          'message': 'search dependency unavailable',
        }, statusCode: 503),
      );
      final failingRepository = RemoteSearchRepository(
        remoteQuery: RemoteCanonicalSearchQuery(
          client: client,
          invocationContext: (clientPageId) => CloudOperationInvocationContext(
            surfaceId: AppUiSurfaces.globalSearchNetworkResults.id,
            routeId: AppUiSurfaces.globalSearchNetworkResults.routeId,
            clientPageId: clientPageId,
            actor: const CloudOperationActorContext(personaId: 'persona-1'),
          ),
        ),
        sessionIdProvider: () => 'search-session-1',
      );

      await expectLater(
        failingRepository.search(
          SearchRequest(
            query: '摄影',
            mode: CanonicalSearchMode.result,
            objectTypes: const <SearchObjectType>{SearchObjectType.contentPost},
          ),
        ),
        throwsA(isA<CloudException>()),
      );
    });
  });
}
