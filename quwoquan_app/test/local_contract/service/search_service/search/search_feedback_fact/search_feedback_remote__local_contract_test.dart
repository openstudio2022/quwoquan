// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/search-storage-topology-and-elasticity/spec.md#gwt-004
// readiness_case: search_feedback_fact_report_search_feedback_app_local
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/search_service/search/search_feedback_fact/adapters/search_feedback_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/transport/cloud_operation_routing_recorder.dart';

void main() {
  test(
    'Search feedback uses one generated append operation and opaque replay key',
    () async {
      final executor = CloudOperationRoutingRecorder(
        responseFor: (_) => <String, Object?>{
          'accepted': true,
          'requestId': 'search-request-1',
        },
      );
      final adapter = RemoteSearchFeedbackAdapter(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: (clientPageId) => CloudOperationInvocationContext(
          surfaceId: 'searchResults',
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(
            accountId: 'account-1',
            personaId: 'persona-1',
          ),
        ),
      );

      final result = await adapter.reportSearchFeedback(
        ReportSearchFeedbackCommand(
          searchRequestId: 'search-request-1',
          eventType: SearchFeedbackEventType.click,
          objectId: 'post-1',
          target: 'posts',
          rankPosition: 2,
          referralSource: 'searchResults',
        ),
      );

      final call = executor.calls.single;
      expect(result.accepted, isTrue);
      expect(
        call.operation.canonicalOperationId,
        AppCloudOperationIds.searchSearchFeedbackFactReportSearchFeedback,
      );
      expect(call.payload.body, <String, Object?>{
        'searchRequestId': 'search-request-1',
        'eventType': 'click',
        'objectId': 'post-1',
        'target': 'posts',
        'rankPosition': 2,
        'referralSource': 'searchResults',
      });
      expect(call.context.idempotencyKey, startsWith('search-feedback-'));
      expect(call.context.idempotencyKey, isNot(contains('search-request-1')));
    },
  );
}
