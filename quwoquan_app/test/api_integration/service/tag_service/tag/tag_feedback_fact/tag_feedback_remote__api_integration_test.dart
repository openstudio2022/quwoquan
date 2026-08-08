// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/career-interest-profile-editor/spec.md#gwt-002
// readiness_case: tag_feedback_fact_report_tag_feedback_app_api

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/tag_api_contract_harness.dart';

void main() {
  late TagApiContractHarness harness;

  setUpAll(() async => harness = await TagApiContractHarness.create());
  tearDownAll(() => harness.close());

  test('generated Remote 追加 canonical TagFeedbackFact 并保留观测身份', () async {
    final resolved = await harness.catalog.resolveTag('Topic/旅行');
    final key =
        'tag-feedback-api-${DateTime.now().toUtc().microsecondsSinceEpoch}';

    final result = await harness.withIdempotencyKey(
      key,
      () => harness.feedback.reportTagFeedback(
        ReportTagFeedbackCommand(
          tagRef: resolved.tagRef,
          action: TagFeedbackAction.click,
          context: 'career_interest_editor',
        ),
      ),
    );

    expect(result.accepted, isTrue);
    final events = await harness.telemetry.waitForEvents(minimumCount: 3);
    final feedbackEvent = events.singleWhere(
      (event) =>
          event.canonicalOperationId ==
          AppCloudOperationIds.tagTagFeedbackFactReportTagFeedback,
    );
    expect(feedbackEvent.succeeded, isTrue);
    expect(feedbackEvent.statusCode, 200);
    expect(feedbackEvent.requestId, isNotEmpty);
    expect(feedbackEvent.traceId, isNotEmpty);
  });
}
