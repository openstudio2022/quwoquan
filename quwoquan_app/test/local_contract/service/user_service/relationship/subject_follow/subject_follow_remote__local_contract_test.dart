// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/spec.md#sit-001
// readiness_case: subject_follow_follow_subject_app_local
// readiness_case: subject_follow_unfollow_subject_app_local
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/user_service/relationship/subject_follow/adapters/subject_follow_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/transport/cloud_operation_routing_recorder.dart';

void main() {
  test(
    'Subject follow set/unset each use their generated command operation',
    () async {
      final executor = CloudOperationRoutingRecorder(
        responseFor: (operation) => <String, Object?>{
          'personaId': 'persona-1',
          'subjectType': 'homepage',
          'subjectId': 'homepage-1',
          'state':
              operation.canonicalOperationId ==
                  AppCloudOperationIds.userSubjectFollowFollowSubject
              ? 'following'
              : 'unfollowed',
          'idempotentReplay': false,
          'updatedAt': '2026-08-08T08:00:00Z',
        },
      );
      final writer = RemoteSubjectFollowFacet(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: (clientPageId) => CloudOperationInvocationContext(
          surfaceId: 'homepageDetail',
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(
            accountId: 'account-1',
            personaId: 'persona-1',
          ),
          idempotencyKey: 'subject-$clientPageId',
        ),
      );

      final followed = await writer.follow(
        FollowSubjectCommand(
          subjectType: SubjectFollowTargetKind.homepage,
          subjectId: 'homepage-1',
        ),
      );
      final unfollowed = await writer.unfollow(
        UnfollowSubjectCommand(
          subjectType: SubjectFollowTargetKind.homepage,
          subjectId: 'homepage-1',
        ),
      );

      expect(followed.state, SubjectFollowState.following);
      expect(unfollowed.state, SubjectFollowState.unfollowed);
      expect(
        executor.calls.map((call) => call.operation.canonicalOperationId),
        <String>[
          AppCloudOperationIds.userSubjectFollowFollowSubject,
          AppCloudOperationIds.userSubjectFollowUnfollowSubject,
        ],
      );
      for (final call in executor.calls) {
        expect(call.payload.pathParameters, <String, String>{
          'subjectType': 'homepage',
          'subjectId': 'homepage-1',
        });
        expect(call.context.idempotencyKey, startsWith('subject-'));
      }
    },
  );
}
