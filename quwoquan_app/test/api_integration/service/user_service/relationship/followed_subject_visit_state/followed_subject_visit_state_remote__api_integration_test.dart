// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/spec.md#sit-001
// readiness_case: followed_subject_visit_state_mark_followed_subject_visited_app_api

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
    'production Remote marks a projected homepage visited with one replay receipt',
    () async {
      final suffix = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
      await harness.loginDisposableAccount('subject-visit-$suffix');
      final homepageSlice = await harness.homepageSearch.searchHomepages(
        HomepageSearchQuery(query: '北京', limit: 10),
      );
      expect(
        homepageSlice.items,
        isNotEmpty,
        reason: 'canonical release must expose a real homepage to follow',
      );
      final homepage = homepageSlice.items.first;
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
              idempotencyKey: 'subject-visit-teardown-unfollow-$suffix',
              action: () => harness.subjectFollows.unfollow(unfollowCommand),
            );
          }
        } finally {
          if (!accountClosed) {
            await harness.accountLifecycle.closeAccount(
              CloseAccountCommand(
                clientRequestId: 'subject-visit-account-cleanup-$suffix',
              ),
            );
          }
        }
      });

      await harness.withIdempotencyKey(
        idempotencyKey: 'subject-visit-follow-$suffix',
        action: () => harness.subjectFollows.follow(
          FollowSubjectCommand(
            subjectType: SubjectFollowTargetKind.homepage,
            subjectId: homepage.homepageId,
            source: 'api_integration',
          ),
        ),
      );
      following = true;
      await _waitForHomepageProjection(harness, homepage.homepageId);

      final command = MarkFollowedSubjectVisitedCommand(
        subjectId: homepage.homepageId,
        subjectType: FollowSubjectKind.homepage,
        visitedAt: DateTime.now().toUtc(),
        clientRequestId: 'subject-visit-mark-$suffix',
      );
      final first = await harness.followedSubjectVisits
          .markFollowedSubjectVisited(command);
      final replay = await harness.followedSubjectVisits
          .markFollowedSubjectVisited(command);

      expect(first.subjectId, homepage.homepageId);
      expect(first.subjectType, FollowSubjectKind.homepage);
      expect(first.hasUnreadChanges, isFalse);
      expect(replay.subjectId, first.subjectId);
      expect(replay.subjectType, first.subjectType);
      expect(replay.lastVisitedAt, first.lastVisitedAt);
      expect(replay.hasUnreadChanges, first.hasUnreadChanges);

      final events = await harness.telemetry.waitForEvents(minimumCount: 6);
      final markEvents = events
          .where(
            (event) =>
                event.canonicalOperationId ==
                AppCloudOperationIds
                    .userFollowedSubjectVisitStateMarkFollowedSubjectVisited,
          )
          .toList(growable: false);
      expect(markEvents, hasLength(2));
      expect(markEvents.every((event) => event.succeeded), isTrue);
      expect(
        markEvents.every(
          (event) => event.requestId.isNotEmpty && event.traceId.isNotEmpty,
        ),
        isTrue,
      );

      await harness.withIdempotencyKey(
        idempotencyKey: 'subject-visit-unfollow-$suffix',
        action: () => harness.subjectFollows.unfollow(unfollowCommand),
      );
      following = false;
      await harness.accountLifecycle.closeAccount(
        CloseAccountCommand(
          clientRequestId: 'subject-visit-account-cleanup-$suffix',
        ),
      );
      accountClosed = true;
    },
  );
}

Future<void> _waitForHomepageProjection(
  UserApiContractHarness harness,
  String homepageId,
) async {
  final deadline = DateTime.now().add(const Duration(seconds: 15));
  while (DateTime.now().isBefore(deadline)) {
    final slice = await harness.followingSubjects.listFollowingSubjects(
      ListFollowingSubjectsQuery(
        limit: 100,
        subjectType: FollowSubjectKind.homepage,
      ),
    );
    if (slice.items.any((item) => item.subjectId == homepageId)) {
      return;
    }
    await Future<void>.delayed(const Duration(milliseconds: 250));
  }
  throw StateError(
    'user.following_subject did not project followed homepage $homepageId '
    'within 15 seconds',
  );
}
