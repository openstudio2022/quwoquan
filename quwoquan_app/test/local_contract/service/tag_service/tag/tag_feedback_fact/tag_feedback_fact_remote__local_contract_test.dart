// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/career-interest-profile-editor/spec.md#gwt-002
// readiness_case: tag_feedback_fact_report_tag_feedback_app_local
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/tag_service/tag/tag_feedback_fact/adapters/tag_feedback_fact_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/transport/cloud_operation_routing_recorder.dart';

void main() {
  test(
    'Tag feedback executes the generated append contract and typed decoder',
    () async {
      final executor = CloudOperationRoutingRecorder(
        responseFor: (_) => <String, Object?>{'accepted': true},
      );
      final adapter = RemoteTagFeedbackAdapter(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: (clientPageId) => CloudOperationInvocationContext(
          surfaceId: 'careerInterest',
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(
            accountId: 'account-1',
            personaId: 'persona-1',
          ),
        ),
      );

      final result = await adapter.reportTagFeedback(
        ReportTagFeedbackCommand(
          tagRef: ' Topic/摄影 ',
          action: TagFeedbackAction.dislike,
        ),
      );

      final call = executor.calls.single;
      expect(result.accepted, isTrue);
      expect(
        call.operation.canonicalOperationId,
        AppCloudOperationIds.tagTagFeedbackFactReportTagFeedback,
      );
      expect(call.payload.body, <String, Object?>{
        'tagRef': 'Topic/摄影',
        'action': 'dislike',
      });
    },
  );
}
