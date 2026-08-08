// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/spec.md#sit-001
// readiness_case: subject_follow_follow_subject_app_api
// readiness_case: subject_follow_unfollow_subject_app_api

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/user_api_contract_harness.dart';

void main() {
  late UserApiContractHarness harness;

  setUpAll(() async {
    harness = await UserApiContractHarness.create();
  });
  tearDownAll(() => harness.close());

  test(
    'production Remote follows and unfollows a discovered homepage with replay-safe receipts',
    () async {
      final suffix = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
      await harness.loginDisposableAccount('subject-follow-$suffix');
      final homepageSlice = await harness.homepageSearch.searchHomepages(
        HomepageSearchQuery(query: '北京', limit: 10),
      );
      expect(
        homepageSlice.items,
        isNotEmpty,
        reason: 'canonical release must expose a real homepage to follow',
      );
      final homepage = homepageSlice.items.first;
      final followCommand = FollowSubjectCommand(
        subjectType: SubjectFollowTargetKind.homepage,
        subjectId: homepage.homepageId,
        source: 'api_integration',
      );
      final unfollowCommand = UnfollowSubjectCommand(
        subjectType: SubjectFollowTargetKind.homepage,
        subjectId: homepage.homepageId,
      );
      var following = false;
      var accountClosed = false;
      addTearDown(() async {
        try {
          if (following) {
            await harness.withIdempotencyKey(
              idempotencyKey: 'subject-follow-teardown-unfollow-$suffix',
              action: () => harness.subjectFollows.unfollow(unfollowCommand),
            );
          }
        } finally {
          if (!accountClosed) {
            await harness.accountLifecycle.closeAccount(
              CloseAccountCommand(
                clientRequestId: 'subject-follow-account-cleanup-$suffix',
              ),
            );
          }
        }
      });

      final followResults = await harness.withIdempotencyKey(
        idempotencyKey: 'subject-follow-follow-$suffix',
        action: () async => <SubjectFollowCommandResult>[
          await harness.subjectFollows.follow(followCommand),
          await harness.subjectFollows.follow(followCommand),
        ],
      );
      following = true;

      expect(followResults.first.subjectId, homepage.homepageId);
      expect(followResults.first.state, SubjectFollowState.following);
      expect(followResults.first.idempotentReplay, isFalse);
      expect(followResults.last.idempotentReplay, isTrue);
      expect(followResults.last.updatedAt, followResults.first.updatedAt);

      final unfollowResults = await harness.withIdempotencyKey(
        idempotencyKey: 'subject-follow-unfollow-$suffix',
        action: () async => <SubjectFollowCommandResult>[
          await harness.subjectFollows.unfollow(unfollowCommand),
          await harness.subjectFollows.unfollow(unfollowCommand),
        ],
      );
      following = false;

      expect(unfollowResults.first.state, SubjectFollowState.unfollowed);
      expect(unfollowResults.first.idempotentReplay, isFalse);
      expect(unfollowResults.last.idempotentReplay, isTrue);
      expect(unfollowResults.last.updatedAt, unfollowResults.first.updatedAt);

      final events = await harness.telemetry.waitForEvents(minimumCount: 6);
      final subjectFollowEvents = events
          .where(
            (event) =>
                event.canonicalOperationId ==
                    AppCloudOperationIds.userSubjectFollowFollowSubject ||
                event.canonicalOperationId ==
                    AppCloudOperationIds.userSubjectFollowUnfollowSubject,
          )
          .toList(growable: false);
      expect(subjectFollowEvents, hasLength(4));
      expect(subjectFollowEvents.every((event) => event.succeeded), isTrue);
      expect(
        subjectFollowEvents.every(
          (event) => event.requestId.isNotEmpty && event.traceId.isNotEmpty,
        ),
        isTrue,
      );

      await harness.accountLifecycle.closeAccount(
        CloseAccountCommand(
          clientRequestId: 'subject-follow-account-cleanup-$suffix',
        ),
      );
      accountClosed = true;
    },
  );
}
