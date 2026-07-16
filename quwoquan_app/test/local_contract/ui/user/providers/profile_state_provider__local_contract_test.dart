import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/user/providers/profile_state_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../../../support/cloud_services/content_facet_overrides.dart';

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
      canGreet: true,
      canOpenConversation: false,
      canStartVoiceCall: false,
      canStartVideoCall: false,
      isBlocked: false,
      isBlockedBy: false,
    );
  }
}

/// 统计 getCapability 调用次数：验证 homepage-bundle 提供首屏关系能力后不再串行补拉。
class _CountingRelationshipCapabilityRepository
    extends _TestRelationshipCapabilityRepository {
  int getCapabilityCalls = 0;

  @override
  Future<RelationshipCapabilityDto> getCapability(String targetUserId) async {
    getCapabilityCalls += 1;
    return super.getCapability(targetUserId);
  }
}

/// 首屏聚合失败仓库：getUserHomepageBundle 抛错，用于验证结构化错误态。
class _FailingUserProfileRepository extends MockUserProfileRepository {
  @override
  Future<UserHomepageBundleViewData> getUserHomepageBundle(
    String subAccountId,
  ) async {
    throw Exception('homepage-bundle 加载失败');
  }
}

class _CountingProfileContentRepository extends MockContentRepository {
  int listUserPostsCalls = 0;

  @override
  Future<CursorPage<PostBaseDto>> listUserPosts({
    required String userId,
    String? identity,
    String? type,
    String? visibility,
    String? cursor,
    int limit = 20,
  }) async {
    listUserPostsCalls += 1;
    return CursorPage<PostBaseDto>(
      items: <PostBaseDto>[_profilePostDto('content_repo_post')],
      nextCursor: null,
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
    SharedPreferences.setMockInitialValues(<String, Object>{});
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
        ...mockContentFacetOverrides(MockContentRepository()),
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
        ...mockContentFacetOverrides(MockContentRepository()),
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

  test('作者主页会跟随共享关系态变化刷新关注展示', () async {
    final container = ProviderContainer(
      overrides: [
        userProfileRepositoryProvider.overrideWithValue(
          _TestUserProfileRepository(),
        ),
        relationshipCapabilityRepositoryProvider.overrideWithValue(
          _TestRelationshipCapabilityRepository(),
        ),
        ...mockContentFacetOverrides(MockContentRepository()),
      ],
    );
    addTearDown(container.dispose);

    container.read(profileNotifierProvider('profile-1').notifier);
    await Future<void>.delayed(const Duration(milliseconds: 1));
    await Future<void>.delayed(const Duration(milliseconds: 1));

    container
        .read(userRelationshipStateProvider.notifier)
        .setFollowing('profile-1', true);
    await Future<void>.delayed(const Duration(milliseconds: 1));

    final profileState = container.read(profileNotifierProvider('profile-1'));
    expect(profileState.isFollowing, isTrue);
    expect(profileState.displayCapability?.relationState, 'following');
  });

  test('loadProfile 一次聚合 bundle：提供关系能力后不再串行 getCapability', () async {
    final capRepo = _CountingRelationshipCapabilityRepository();
    final container = ProviderContainer(
      overrides: [
        userProfileRepositoryProvider.overrideWithValue(
          _TestUserProfileRepository(),
        ),
        relationshipCapabilityRepositoryProvider.overrideWithValue(capRepo),
        ...mockContentFacetOverrides(MockContentRepository()),
      ],
    );
    addTearDown(container.dispose);

    container.read(profileNotifierProvider('profile-1').notifier);
    await Future<void>.delayed(const Duration(milliseconds: 1));
    await Future<void>.delayed(const Duration(milliseconds: 1));

    final s = container.read(profileNotifierProvider('profile-1'));
    expect(s.isLoading, isFalse);
    expect(s.hasLoadError, isFalse);
    expect(s.profile, isNotNull);
    // bundle 自带首屏关系能力，capability 非空。
    expect(s.capability, isNotNull);
    // 首屏不再串行补拉 getCapability（性能闭环：消除额外请求）。
    expect(capRepo.getCapabilityCalls, 0);
  });

  test(
    'loadProfile 的作品列表经 ContentReadRepository 读取以复用 query snapshot',
    () async {
      final contentRepo = _CountingProfileContentRepository();
      final container = ProviderContainer(
        overrides: [
          userProfileRepositoryProvider.overrideWithValue(
            _TestUserProfileRepository(),
          ),
          ...mockContentFacetOverrides(contentRepo),
          relationshipCapabilityRepositoryProvider.overrideWithValue(
            _TestRelationshipCapabilityRepository(),
          ),
        ],
      );
      addTearDown(container.dispose);

      container.read(profileNotifierProvider('profile-1').notifier);
      await Future<void>.delayed(const Duration(milliseconds: 1));
      await Future<void>.delayed(const Duration(milliseconds: 1));

      final s = container.read(profileNotifierProvider('profile-1'));
      expect(contentRepo.listUserPostsCalls, 1);
      expect(s.creations.single.id, 'content_repo_post');
    },
  );

  test('loadProfile 失败进入结构化错误态：errorMessage 非空且不静默', () async {
    final container = ProviderContainer(
      overrides: [
        userProfileRepositoryProvider.overrideWithValue(
          _FailingUserProfileRepository(),
        ),
        relationshipCapabilityRepositoryProvider.overrideWithValue(
          _TestRelationshipCapabilityRepository(),
        ),
        ...mockContentFacetOverrides(MockContentRepository()),
      ],
    );
    addTearDown(container.dispose);

    container.read(profileNotifierProvider('profile-err').notifier);
    await Future<void>.delayed(const Duration(milliseconds: 1));
    await Future<void>.delayed(const Duration(milliseconds: 1));

    final s = container.read(profileNotifierProvider('profile-err'));
    expect(s.isLoading, isFalse);
    expect(s.hasLoadError, isTrue);
    expect(s.errorMessage, isNotNull);
    expect(s.errorMessage, isNotEmpty);
  });
}

PostBaseDto _profilePostDto(String id) {
  return postBaseDtoFromMap(<String, dynamic>{
    'postId': id,
    'id': id,
    '_id': id,
    'contentType': 'micro',
    'contentIdentity': 'moment',
    'identity': 'moment',
    'authorId': 'profile-1',
    'displayName': '展示名',
    'avatarUrl': '',
    'body': '个人作品缓存内容',
    'mediaUrls': <String>[],
    'likeCount': 0,
    'commentCount': 0,
    'shareCount': 0,
    'createdAt': '2026-05-19T00:00:00.000Z',
    'updatedAt': '2026-05-19T00:00:00.000Z',
  });
}
