// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/search-storage-topology-and-elasticity/spec.md#gwt-004
// readiness_case: search_request_fact_list_hot_queries_app_local
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/search_service/search/search_request_fact/adapters/hot_query_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/transport/cloud_operation_routing_recorder.dart';

void main() {
  test(
    'Hot-query reader preserves generated query encoding and result order',
    () async {
      final executor = CloudOperationRoutingRecorder(
        responseFor: (_) => <String, Object?>{
          'items': <Object?>[
            <String, Object?>{'query': '旅行摄影', 'relevance': 9.8},
            <String, Object?>{'query': '城市漫步', 'relevance': 9.1},
          ],
        },
      );
      final reader = RemoteSearchHotQueryReader(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: (clientPageId) => CloudOperationInvocationContext(
          surfaceId: 'searchHome',
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(
            accountId: 'account-1',
            personaId: 'persona-1',
          ),
        ),
      );

      final result = await reader.listHotQueries(ListHotQueriesQuery(limit: 6));

      final call = executor.calls.single;
      expect(
        call.operation.canonicalOperationId,
        AppCloudOperationIds.searchSearchRequestFactListHotQueries,
      );
      expect(call.payload.queryParameters, <String, String>{'limit': '6'});
      expect(result.items.map((item) => item.query), <String>['旅行摄影', '城市漫步']);
    },
  );
}
