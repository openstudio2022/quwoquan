// spec_ref: specs/feature-tree/global-search-experience/cross-domain-search/multi-domain-result-composition/spec.md#gwt-001
// readiness_case: persisted_query_execution_search_page_app_local
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/graphql_read/generated/search_page.g.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/runtime/di/search_dependencies.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/search_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import '../../../../../support/runtime/observability/recording_cloud_operation_telemetry_sink.dart';

final class _LocalClientContext implements CloudClientContextProvider {
  const _LocalClientContext();

  @override
  CloudClientContextSnapshot snapshot() => const CloudClientContextSnapshot(
    sessionId: 'persisted-search-local-contract',
    deviceActorId: 'persisted-search-local-device',
    platform: 'test',
    appVersion: 'local-contract',
    locale: 'zh-CN',
  );
}

void main() {
  test(
    'production composition sends signed SearchPage without query text',
    () async {
      late http.Request captured;
      final transport = MockClient((request) async {
        captured = request;
        return http.Response(
          jsonEncode(<String, Object?>{
            'data': <String, Object?>{
              'searchPage': <String, Object?>{
                'degradeSignals': <Object?>[],
                'facets': <Object?>[],
                'items': <Object?>[],
                'matchedTerms': <String>['山间'],
                'nextCursor': null,
                'searchRequestId': 'search.req.local-1',
                'suggestions': <String>[],
              },
            },
          }),
          200,
          headers: const <String, String>{
            'content-type': 'application/json; charset=utf-8',
            'x-request-id': 'req-local-1',
            'x-trace-id': 'trace-local-1',
          },
        );
      });
      final httpClient = CloudHttpClient(client: transport);
      final telemetry = RecordingCloudOperationTelemetrySink();
      addTearDown(httpClient.close);
      final executor = buildGeneratedCloudOperationExecutor(
        httpClient: httpClient,
        clientContextProvider: const _LocalClientContext(),
        telemetrySink: telemetry,
        environment: testCloudRuntimeEnvironment(),
      );
      final repository = SearchProductionComposition.searchRepository(
        searchPageClient: GeneratedSearchPageGraphQLClient(executor),
        invocationContext: (clientPageId) => CloudOperationInvocationContext(
          surfaceId: AppUiSurfaces.globalSearchNetworkResults.id,
          routeId: AppUiSurfaces.globalSearchNetworkResults.routeId,
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(
            deviceActorId: 'persisted-search-local-device',
          ),
        ),
      );

      final response = await repository.search(
        const SearchRequest(
          query: '山间',
          mode: CanonicalSearchMode.result,
          limit: 1,
        ),
      );

      expect(captured.url.path, '/graphql');
      final body = jsonDecode(captured.body) as Map<String, Object?>;
      expect(body['operationName'], 'SearchPage');
      expect(body.containsKey('query'), isFalse);
      final extensions = body['extensions'] as Map<String, Object?>;
      final persisted = extensions['persistedQuery'] as Map<String, Object?>;
      expect(persisted['version'], 1);
      expect(persisted['sha256Hash'], isNotEmpty);
      expect(response.searchRequestId, 'search.req.local-1');
      expect(response.pageItems, isEmpty);
      expect(
        telemetry.events.single.canonicalOperationId,
        'gateway.persisted_query_execution.ExecutePersistedGraphQLQuery',
      );
      expect(telemetry.events.single.succeeded, isTrue);
    },
  );
}
