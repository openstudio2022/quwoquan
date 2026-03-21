import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/user/providers/profile_state_provider.dart';

class _TestUserProfileRepository extends MockUserProfileRepository {
  int followCalls = 0;
  int unfollowCalls = 0;

  @override
  Future<Map<String, dynamic>> getUserProfile(String userId) async {
    return {
      'profileSubjectId': userId,
      'ownerUserId': 'owner-1',
      'subjectType': 'sub_account',
      'subAccountId': userId,
      'username': 'user_name',
      'displayName': '展示名',
      'avatarUrl': '',
      'backgroundUrl': '',
      'bio': '',
      'followerCount': 0,
      'followingCount': 0,
      'postCount': 0,
      'circleCount': 0,
      'likeCount': 0,
      'profileVisibility': 'public',
      'inheritsFromOwner': true,
      'overriddenFields': const <String>[],
    };
  }

  @override
  Future<Map<String, dynamic>> getUserStats(String userId) async {
    return const <String, dynamic>{};
  }

  @override
  Future<void> followUser(String targetUserId) async {
    followCalls += 1;
  }

  @override
  Future<void> unfollowUser(String targetUserId) async {
    unfollowCalls += 1;
  }
}

class _TestRelationshipCapabilityRepository
    extends MockRelationshipCapabilityRepository {
  @override
  Future<RelationshipCapabilityDto> getCapability(String targetUserId) async {
    return RelationshipCapabilityDto(
      viewerSubAccountId: 'viewer-1',
      targetSubAccountId: targetUserId,
      relationState: 'not_following',
      canGreet: false,
      canOpenConversation: true,
      canAddSameInterest: false,
      canSetCloseFriend: false,
      canStartVoiceCall: false,
      canStartVideoCall: false,
      isBlocked: false,
      isBlockedBy: false,
    );
  }
}

void main() {
  test('toggleFollow 会同步 capability relationState 与 shared provider', () async {
    final userRepo = _TestUserProfileRepository();
    final container = ProviderContainer(
      overrides: [
        userProfileRepositoryProvider.overrideWithValue(userRepo),
        relationshipCapabilityRepositoryProvider.overrideWithValue(
          _TestRelationshipCapabilityRepository(),
        ),
      ],
    );
    addTearDown(container.dispose);

    final notifier = container.read(profileNotifierProvider('profile-1'));
    await Future<void>.delayed(const Duration(milliseconds: 1));
    await Future<void>.delayed(const Duration(milliseconds: 1));

    expect(notifier.state.capability?.relationState, 'not_following');
    expect(
      container.read(userRelationshipStateProvider).isFollowing('profile-1'),
      isFalse,
    );

    await notifier.toggleFollow();

    expect(notifier.state.capability?.relationState, 'following');
    expect(
      container.read(userRelationshipStateProvider).isFollowing('profile-1'),
      isTrue,
    );
    expect(userRepo.followCalls, 0);
    expect(
      container.read(clientStateSyncOutboxProvider).entries.single.objectId,
      'profile-1',
    );
  });

  test('shared follow 快照已知时，mock capability 不覆盖为未关注', () async {
    final container = ProviderContainer(
      overrides: [
        userProfileRepositoryProvider.overrideWithValue(
          _TestUserProfileRepository(),
        ),
        relationshipCapabilityRepositoryProvider.overrideWithValue(
          _TestRelationshipCapabilityRepository(),
        ),
      ],
    );
    addTearDown(container.dispose);
    container
        .read(userRelationshipStateProvider.notifier)
        .setFollowing('profile-1', true);

    final notifier = container.read(profileNotifierProvider('profile-1'));
    await Future<void>.delayed(const Duration(milliseconds: 1));
    await Future<void>.delayed(const Duration(milliseconds: 1));

    expect(notifier.state.isFollowing, isTrue);
    expect(notifier.state.capability?.relationState, 'following');
  });
}
