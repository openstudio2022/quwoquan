import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/user/providers/profile_state_provider.dart';

class _TestUserProfileRepository extends MockUserProfileRepository {
  int followCalls = 0;
  int unfollowCalls = 0;

  @override
  Future<SubAccountProfileViewData> getUserProfile(String userId) async {
    return SubAccountProfileViewData(
      subAccountId: userId,
      ownerUserId: 'owner-1',
      subjectType: 'subAccount',
      userHandle: 'user_name',
      username: 'user_name',
      displayName: '展示名',
      avatarUrl: '',
      backgroundUrl: '',
      bio: '',
      followerCount: 0,
      followingCount: 0,
      postCount: 0,
      circleCount: 0,
      likeCount: 0,
      isolationLevel: 'open',
      profileVisibility: 'public',
      inheritsFromOwner: true,
      overriddenFields: const <String>[],
      updatedAt: null,
    );
  }

  @override
  Future<UserProfileStatsViewData> getUserStats(String userId) async {
    return const UserProfileStatsViewData(
      followingCount: 0,
      circleCount: 0,
      followerCount: 0,
      likeCount: 0,
      postCount: 0,
    );
  }

  @override
  Future<void> followUser(
    String targetUserId, {
    String? ownerUserId,
    String? subAccountId,
    String? subAccountContextVersion,
  }) async {
    followCalls += 1;
  }

  @override
  Future<void> unfollowUser(
    String targetUserId, {
    String? ownerUserId,
    String? subAccountId,
    String? subAccountContextVersion,
  }) async {
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
  late Directory tempDir;

  setUpAll(() async {
    tempDir = await Directory.systemTemp.createTemp('profile_state_test_');
    Hive.init(tempDir.path);
    final box = await Hive.openBox<String>('client_interaction_state');
    await box.clear();
    await box.close();
  });

  setUp(() async {
    if (Hive.isBoxOpen('client_interaction_state')) {
      await Hive.box<String>('client_interaction_state').clear();
      return;
    }
    final box = await Hive.openBox<String>('client_interaction_state');
    await box.clear();
    await box.close();
  });

  tearDownAll(() async {
    await Hive.close();
    if (await tempDir.exists()) {
      await tempDir.delete(recursive: true);
    }
  });

  test('toggleFollow 仅通过 optimistic overlay 更新展示 capability', () async {
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

    final notifier = container.read(
      profileNotifierProvider('profile-1').notifier,
    );
    await Future<void>.delayed(const Duration(milliseconds: 1));
    await Future<void>.delayed(const Duration(milliseconds: 1));

    expect(
      container
          .read(profileNotifierProvider('profile-1'))
          .capability
          ?.relationState,
      'not_following',
    );
    expect(
      container.read(userRelationshipStateProvider).isFollowing('profile-1'),
      isFalse,
    );

    await notifier.toggleFollow();

    expect(
      container
          .read(profileNotifierProvider('profile-1'))
          .displayCapability
          ?.relationState,
      'following',
    );
    expect(
      container
          .read(profileNotifierProvider('profile-1'))
          .capability
          ?.relationState,
      'not_following',
    );
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

  test('shared follow 快照已知时，仅以 optimistic overlay 覆盖展示态', () async {
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

    container.read(profileNotifierProvider('profile-1').notifier);
    await Future<void>.delayed(const Duration(milliseconds: 1));
    await Future<void>.delayed(const Duration(milliseconds: 1));

    final profileState = container.read(profileNotifierProvider('profile-1'));
    expect(profileState.isFollowing, isTrue);
    expect(profileState.displayCapability?.relationState, 'following');
    expect(profileState.capability?.relationState, 'not_following');
  });
}
