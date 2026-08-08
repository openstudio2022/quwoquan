// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/spec.md#sit-001
// readiness_case: following_subject_list_following_subjects_app_api

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
    'production Remote lists the real homepage followed by a disposable persona',
    () async {
      final suffix = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
      await harness.loginDisposableAccount('following-subject-$suffix');
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
              idempotencyKey: 'following-subject-teardown-unfollow-$suffix',
              action: () => harness.subjectFollows.unfollow(unfollowCommand),
            );
          }
        } finally {
          if (!accountClosed) {
            await harness.accountLifecycle.closeAccount(
              CloseAccountCommand(
                clientRequestId: 'following-subject-account-cleanup-$suffix',
              ),
            );
          }
        }
      });

      await harness.withIdempotencyKey(
        idempotencyKey: 'following-subject-follow-$suffix',
        action: () => harness.subjectFollows.follow(
          FollowSubjectCommand(
            subjectType: SubjectFollowTargetKind.homepage,
            subjectId: homepage.homepageId,
            source: 'api_integration',
          ),
        ),
      );
      following = true;

      final projected = await _waitForHomepageProjection(
        harness,
        homepage.homepageId,
      );
      expect(projected.subjectType, FollowSubjectKind.homepage);
      expect(projected.subjectId, homepage.homepageId);
      expect(projected.displayName, isNotEmpty);
      expect(projected.targetRouteId, isNotEmpty);
      expect(projected.targetObjectId, isNotEmpty);

      await harness.withIdempotencyKey(
        idempotencyKey: 'following-subject-unfollow-$suffix',
        action: () => harness.subjectFollows.unfollow(unfollowCommand),
      );
      following = false;
      await harness.accountLifecycle.closeAccount(
        CloseAccountCommand(
          clientRequestId: 'following-subject-account-cleanup-$suffix',
        ),
      );
      accountClosed = true;
    },
  );
}

Future<FollowingSubjectItemView> _waitForHomepageProjection(
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
    for (final item in slice.items) {
      if (item.subjectId == homepageId) {
        return item;
      }
    }
    await Future<void>.delayed(const Duration(milliseconds: 250));
  }
  throw StateError(
    'user.following_subject did not project followed homepage $homepageId '
    'within 15 seconds',
  );
}
