/// 对象级端云契约：Remote adapter 的 HTTP path 与 generated metadata 对齐。
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/search/search_request_page_ids.g.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/adapters/search_query_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../../support/runtime/remote_api_path_test_harness.dart';

http.Response _responseFor(http.Request request) {
  if (request.method == 'POST' &&
      request.url.path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.searchSearchIndexViewSearch,
          )) {
    return remoteApiPathJsonResponse({
      'hits': <dynamic>[],
      'citations': <dynamic>[],
      'facets': <dynamic>[],
      'requestId': 'search-request-1',
      'relatedTerms': <String>[],
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
    late RemoteCanonicalSearchQuery searchAdapter;

    setUp(() {
      log = [];
      final client = buildRemoteApiPathOperationClient(
        log,
        responseFor: _responseFor,
      );
      searchAdapter = RemoteCanonicalSearchQuery(
        client: client,
        invocationContext: (clientPageId) {
          return CloudOperationInvocationContext(
            surfaceId: AppUiSurfaces.globalSearchNetworkResults.id,
            routeId: AppUiSurfaces.globalSearchNetworkResults.routeId,
            clientPageId: clientPageId,
            actor: const CloudOperationActorContext(personaId: 'persona-1'),
          );
        },
      );
    });

    test('canonical search → POST /search generated operation', () async {
      await searchAdapter.search(
        CanonicalSearchQuery(
          query: '摄影',
          objectTypes: const <String>['article'],
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
      expect(log.last.body['objectTypes'], const <String>['article']);
      expect(log.last.body['limit'], 9);
      expectRemoteApiPathHeaders(
        log.last.headers,
        clientPageId: SearchRequestPageIds.search,
        surfaceId: AppUiSurfaces.globalSearchNetworkResults.id,
        operationId: AppCloudOperationIds.searchSearchIndexViewSearch,
      );
    });
  });
}
