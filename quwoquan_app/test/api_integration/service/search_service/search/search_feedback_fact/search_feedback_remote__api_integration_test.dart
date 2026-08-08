// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/search-storage-topology-and-elasticity/spec.md#gwt-002
// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/search-storage-topology-and-elasticity/spec.md#gwt-004
// readiness_case: search_feedback_fact_report_search_feedback_app_api
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/search_api_contract_harness.dart';

void main() {
  test(
    'production Search Remote returns a hit before feedback is accepted',
    () async {
      final harness = await SearchApiContractHarness.create();
      addTearDown(harness.close);

      final response = await harness.search.search(
        CanonicalSearchQuery(
          sessionId: 'search-feedback-api-contract',
          query: '西湖',
          mode: CanonicalSearchMode.result,
          objectTypes: const <String>['article', 'entity', 'location'],
          limit: 20,
        ),
      );
      final feedbackCandidates = response.hits
          .where(
            (hit) =>
                hit.objectId.trim().isNotEmpty &&
                hit.target.trim().isNotEmpty &&
                (hit.rankPosition ?? 0) > 0,
          )
          .toList(growable: false);
      expect(response.requestId.trim(), isNotEmpty);
      expect(
        feedbackCandidates,
        isNotEmpty,
        reason: 'the real Search result must provide a feedback target',
      );
      final hit = feedbackCandidates.first;

      final acknowledgement = await harness.feedback.reportSearchFeedback(
        ReportSearchFeedbackCommand(
          searchRequestId: response.requestId,
          eventType: SearchFeedbackEventType.click,
          objectId: hit.objectId,
          target: hit.target,
          rankPosition: hit.rankPosition,
          referralSource: 'api_integration',
        ),
      );

      expect(acknowledgement.accepted, isTrue);
      expect(acknowledgement.requestId.trim(), isNotEmpty);
      final events = await harness.telemetry.waitForEvents(minimumCount: 2);
      final operationEvents = {
        for (final event in events) event.canonicalOperationId: event,
      };
      expect(operationEvents.keys.toSet(), <String>{
        AppCloudOperationIds.searchSearchIndexViewSearch,
        AppCloudOperationIds.searchSearchFeedbackFactReportSearchFeedback,
      });
      expect(operationEvents.values.every((event) => event.succeeded), isTrue);
      expect(
        operationEvents.values.every(
          (event) =>
              event.requestId.trim().isNotEmpty &&
              event.traceId.trim().isNotEmpty,
        ),
        isTrue,
      );
      expect(
        operationEvents[AppCloudOperationIds.searchSearchIndexViewSearch]
            ?.statusCode,
        200,
      );
      expect(
        operationEvents[AppCloudOperationIds
                .searchSearchFeedbackFactReportSearchFeedback]
            ?.statusCode,
        202,
      );
    },
  );
}
