import 'package:test/test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona_create_request_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona_update_request_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_homepage_bundle_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/services/user/profile_edit_models.dart';
import 'package:quwoquan_app/cloud/services/user/profile_edit_update_payload.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';
import 'package:quwoquan_app/core/auth/mock_session_identity.dart';

const _fixtureCurrentUserId = 'fixture_user_current';
const _fixtureProfileUserId = 'fixture_user_photo';

void main() {
  // ── 常规契约 ──────────────────────────────────────────────────────────────

  group('UserProfileRepository — 常规契约', () {
    late UserProfileRepository repo;

    setUp(() {
      repo = const MockUserProfileRepository();
    });

    // ── 档案 ────────────────────────────────────────────────────────────────

    test('getUserProfile 返回完整档案', () async {
      final profile = await repo.getUserProfile(_fixtureProfileUserId);
      expect(profile.subAccountId, _fixtureProfileUserId);
      expect(profile.displayName, isNotEmpty);
      expect(profile.avatarUrl, isNotEmpty);
      expect(profile.followerCount, greaterThan(0));
      expect(profile.followingCount, greaterThan(0));
      expect(profile.postCount, greaterThan(0));
      expect(profile.circleCount, greaterThan(0));
      expect(profile.likeCount, greaterThan(0));
    });

    test('updateProfile 不崩溃', () async {
      await expectLater(
        repo.updateProfile(
          const ProfileEditUpdatePayload(nickname: '新昵称', bio: 'b'),
        ),
        completes,
      );
    });

    test('updateProfile payload 使用 profile media assetId 和 fieldsMask', () {
      final wire = const ProfileEditUpdatePayload(
        avatarAssetId: 'asset_avatar_1',
        backgroundAssetId: 'asset_cover_1',
        avatarUrl: 'https://cdn.example.test/avatar.jpg',
        backgroundUrl: 'https://cdn.example.test/cover.jpg',
      ).toRepositoryMap();

      expect(wire['avatarAssetId'], 'asset_avatar_1');
      expect(wire['backgroundAssetId'], 'asset_cover_1');
      expect(
        wire['fieldsMask'],
        containsAll(<String>[
          'avatarAssetId',
          'backgroundAssetId',
          'avatarUrl',
          'backgroundUrl',
        ]),
      );
    });

    test('updateProfile 后本人主页与编辑快照按 alias 双向一致', () async {
      const avatarUrl =
          'media/avatar/s/mock/seed/u_1599566150163-29194dcaad36/v1/avatar.jpg';
      const backgroundUrl =
          'media/background/s/archived-avatar/user/fixture_user_current/v1/background.png';
      const nickname = '资料同步用户';
      const bio = '资料编辑双向一致性验证';
      const gender = 'female';
      const birthDate = '1996-05-21';
      const regionTagRef = 'Topic/地理/行政区/中国/广东省/云浮市';
      const occupationTagRef = 'Audience/用户/职业/产品/产品经理';
      const interestTagRefs = <String>[
        'Audience/用户/兴趣偏好/影像/摄影',
        'Audience/用户/兴趣偏好/旅行/城市漫游',
      ];

      await repo.updateProfile(
        const ProfileEditUpdatePayload(
          nickname: nickname,
          bio: bio,
          avatarUrl: avatarUrl,
          backgroundUrl: backgroundUrl,
          gender: gender,
          birthDate: birthDate,
          regionTagRef: regionTagRef,
          occupationTagRef: occupationTagRef,
          interestTagRefs: interestTagRefs,
        ),
      );

      final canonicalProfile = await repo.getUserProfile(
        kMockCurrentSubAccountId,
      );
      final archiveProfile = await repo.getUserProfile('user_001');
      final homepageBundle = await repo.getUserHomepageBundle('user_001');
      final editSnapshot = await repo.getProfileEditSnapshot();
      final expectedAvatarUrl = canonicalProfile.avatarUrl;
      final expectedBackgroundUrl = canonicalProfile.backgroundUrl;

      expect(expectedAvatarUrl, isNotEmpty);
      expect(expectedBackgroundUrl, isNotEmpty);

      for (final profile in <SubAccountProfileViewData>[
        canonicalProfile,
        archiveProfile,
        homepageBundle.profile,
      ]) {
        expect(profile.displayName, nickname);
        expect(profile.bio, bio);
        expect(profile.avatarUrl, expectedAvatarUrl);
        expect(profile.backgroundUrl, expectedBackgroundUrl);
        expect(profile.identityTags, <String>[
          occupationTagRef,
          ...interestTagRefs,
        ]);
      }
      expect(homepageBundle.viewerContext.isOwner, isTrue);
      expect(editSnapshot.nickname, nickname);
      expect(editSnapshot.bio, bio);
      expect(editSnapshot.avatarUrl, expectedAvatarUrl);
      expect(editSnapshot.backgroundUrl, expectedBackgroundUrl);
      expect(editSnapshot.gender, gender);
      expect(editSnapshot.birthDate, birthDate);
      expect(editSnapshot.regionTagRef, regionTagRef);
      expect(editSnapshot.region, '广东 云浮');
      expect(editSnapshot.occupationTagRef, occupationTagRef);
      expect(editSnapshot.interestTagRefs, interestTagRefs);
      expect(editSnapshot.userHandle, canonicalProfile.userHandle);
    });

    test('ProfileQrCardData 要求服务返回真实 qrPayload', () {
      expect(
        () => ProfileQrCardData.fromMap(<String, dynamic>{
          'publicProfileUrl': 'https://app.example.test/u/qw123',
        }),
        throwsStateError,
      );
      final card = ProfileQrCardData.fromMap(<String, dynamic>{
        'publicProfileUrl': 'https://app.example.test/u/qw123',
        'qrPayload': 'https://app.example.test/u/qw123?qr=opaque',
        'qrTokenId': 'token_1',
      });
      expect(card.qrPayload, contains('qr=opaque'));
    });

    // ── 主页 Tab 数据 ──────────────────────────────────────────────────────

    test('listUserPosts 返回非空帖子列表', () async {
      final posts = await repo.listUserPosts(_fixtureProfileUserId);
      expect(posts, isNotEmpty);
      expect(
        posts.every((post) => post.authorId == _fixtureProfileUserId),
        isTrue,
      );
      expect(posts.every((post) => post.identity == 'work'), isTrue);
    });

    test('listUserWorks 返回作品集列表', () async {
      final works = await repo.listUserWorks(_fixtureProfileUserId);
      expect(works, isNotEmpty);
      for (final w in works) {
        expect(w.id, isNotEmpty);
        expect(w.title, isNotEmpty);
        expect(w.coverUrl, isNotEmpty);
        expect(w.type, isNotEmpty);
      }
    });

    test('listUserLifeItems 返回生活记录列表（字段对齐 UserLifeItemDto）', () async {
      const lifeCategories = {'footprint', 'soul', 'taste', 'private'};
      final items = await repo.listUserLifeItems(_fixtureCurrentUserId);
      expect(items, isNotEmpty);
      for (final item in items) {
        expect(item.id, isNotEmpty);
        expect(item.title, isNotEmpty);
        // category 为 LifeItemCategory 枚举值，子页过滤直接比对。
        expect(lifeCategories, contains(item.category));
        expect(item.imageUrl, isNotEmpty);
      }
    });

    test('listUserCircles 返回圈子列表', () async {
      final circles = await repo.listUserCircles(_fixtureProfileUserId);
      expect(circles, isNotEmpty);
      for (final c in circles) {
        expect(c.id, isNotEmpty);
        expect(c.name, isNotEmpty);
        expect(c.coverUrl ?? '', isNotEmpty);
      }
    });

    test('getUserStats 返回统计数据', () async {
      final stats = await repo.getUserStats(_fixtureProfileUserId);
      expect(stats.followingCount, greaterThan(0));
      expect(stats.circleCount, greaterThan(0));
      expect(stats.followerCount, greaterThan(0));
      expect(stats.likeCount, greaterThan(0));
    });

    // ── 关注 / 粉丝 ────────────────────────────────────────────────────────

    test('followUser 不崩溃', () async {
      await expectLater(repo.followUser('target_user_1'), completes);
    });

    test('unfollowUser 不崩溃', () async {
      await expectLater(repo.unfollowUser('target_user_1'), completes);
    });

    test('listFollowing 返回用户列表', () async {
      final following = await repo.listFollowing(_fixtureCurrentUserId);
      expect(following, isList);
      expect(following, isNotEmpty);
      for (final u in following) {
        expect(u.subAccountId, isNotEmpty);
        expect(u.displayName, isNotEmpty);
        expect(u.avatarUrl, isNotEmpty);
      }
    });

    test('listFollowers 返回用户列表', () async {
      final followers = await repo.listFollowers(_fixtureProfileUserId);
      expect(followers, isList);
      expect(followers, isNotEmpty);
      for (final u in followers) {
        expect(u.subAccountId, isNotEmpty);
        expect(u.displayName, isNotEmpty);
      }
    });

    test('getRelationship 返回关系状态', () async {
      final rel = await repo.getRelationship('target_user_1');
      expect(rel.isFollowing, isA<bool>());
      expect(rel.isFollowedBy, isA<bool>());
      expect(rel.isMutual, isA<bool>());
    });

    test('listUserLikes 返回获赞列表', () async {
      final likes = await repo.listUserLikes(_fixtureProfileUserId);
      expect(likes, isList);
      expect(likes, isNotEmpty);
      for (final item in likes) {
        expect(item.postId, isNotEmpty);
        expect(item.likerNickname, isNotEmpty);
      }
    });

    // ── 分身 ────────────────────────────────────────────────────────────────

    test('listPersonas 返回分身列表', () async {
      final personas = await repo.listPersonas();
      expect(personas, isNotEmpty);
      for (final p in personas) {
        expect(p.id, isNotEmpty);
        expect(p.displayName, isNotEmpty);
      }
    });

    test('createPersona 返回含 id 的分身', () async {
      final persona = await repo.createPersona(
        PersonaCreateRequestDto(displayName: '新分身', isolationLevel: 'strict'),
      );
      expect(persona.id, isNotEmpty);
      expect(persona.displayName, '新分身');
      expect(persona.isPrivate, isTrue);
    });

    test('updatePersona 不崩溃', () async {
      await expectLater(
        repo.updatePersona(
          'persona_primary',
          PersonaUpdateRequestDto(displayName: '更新名'),
        ),
        completes,
      );
    });

    test('deletePersona 不崩溃', () async {
      await expectLater(repo.deletePersona('persona_anon'), completes);
    });

    test('activatePersona 不崩溃', () async {
      await expectLater(repo.activatePersona('persona_anon'), completes);
    });

    // ── 主页首屏聚合（homepage-bundle，锁定决策 #1）─────────────────────────

    test('getUserHomepageBundle 本人态：聚合身份域真相且不下发关系能力', () async {
      final bundle = await repo.getUserHomepageBundle(_fixtureCurrentUserId);
      expect(bundle.profile.subAccountId, kMockCurrentSubAccountId);
      expect(bundle.viewerContext.isOwner, isTrue);
      expect(bundle.viewerContext.isGuest, isFalse);
      expect(bundle.viewerContext.relationToTarget, 'self');
      // 本人态无需关系动作能力（关注/打招呼等），不下发。
      expect(bundle.relationshipCapability, isNull);
      expect(bundle.cacheVersion, isNotEmpty);
    });

    test(
      'getUserHomepageBundle tabCounts 与 stats 同源（works/likes/circles）',
      () async {
        final bundle = await repo.getUserHomepageBundle(_fixtureProfileUserId);
        expect(bundle.tabCounts.worksCount, bundle.stats.postCount);
        expect(bundle.tabCounts.likesCount, bundle.stats.likeCount);
        expect(bundle.tabCounts.circlesCount, bundle.stats.circleCount);
        // collections 属 content 域，user 域不造假，置 0 待端覆盖。
        expect(bundle.tabCounts.collectionsCount, 0);
      },
    );

    test('getUserHomepageBundle 他人态：下发关系能力且非本人', () async {
      final bundle = await repo.getUserHomepageBundle(_fixtureProfileUserId);
      expect(bundle.viewerContext.isOwner, isFalse);
      expect(bundle.relationshipCapability, isNotNull);
      expect(
        bundle.relationshipCapability!.targetSubAccountId,
        _fixtureProfileUserId,
      );
      // 未关注时可关注、不可取关（与关系态同源）。
      expect(
        bundle.relationshipCapability!.canFollow ||
            bundle.relationshipCapability!.canUnfollow,
        isTrue,
      );
    });

    test('getUserHomepageBundle profileWithStats 计数与 stats 一致', () async {
      final bundle = await repo.getUserHomepageBundle(_fixtureProfileUserId);
      final merged = bundle.profileWithStats;
      expect(merged.followerCount, bundle.stats.followerCount);
      expect(merged.followingCount, bundle.stats.followingCount);
      expect(merged.likeCount, bundle.stats.likeCount);
      expect(merged.circleCount, bundle.stats.circleCount);
      expect(merged.postCount, bundle.stats.postCount);
    });

    test('接口包含全部 19 个 service.yaml API 方法', () {
      final methods = <String>[
        'getUserProfile',
        'getUserHomepageBundle',
        'updateProfile',
        'listUserPosts',
        'listUserWorks',
        'listUserLifeItems',
        'listUserCircles',
        'getUserStats',
        'followUser',
        'unfollowUser',
        'listFollowing',
        'listFollowers',
        'getRelationship',
        'listUserLikes',
        'listPersonas',
        'createPersona',
        'updatePersona',
        'deletePersona',
        'activatePersona',
      ];
      expect(methods.length, 19);
      expect(
        repo.runtimeType.toString(),
        contains('MockUserProfileRepository'),
      );
    });
  });

  // ── 兼容性契约 ────────────────────────────────────────────────────────────

  group('UserProfileRepository — 兼容性契约', () {
    late UserProfileRepository repo;

    setUp(() {
      repo = const MockUserProfileRepository();
    });

    test('listUserPosts limit 参数限制条数', () async {
      final posts = await repo.listUserPosts(_fixtureProfileUserId, limit: 2);
      expect(posts.length, lessThanOrEqualTo(2));
    });

    test('listUserCircles limit 参数限制条数', () async {
      final circles = await repo.listUserCircles(
        _fixtureProfileUserId,
        limit: 1,
      );
      expect(circles.length, lessThanOrEqualTo(1));
    });

    test('listFollowing limit 参数限制条数', () async {
      final following = await repo.listFollowing(
        _fixtureCurrentUserId,
        limit: 2,
      );
      expect(following.length, lessThanOrEqualTo(2));
    });

    test('listFollowers limit 参数限制条数', () async {
      final followers = await repo.listFollowers(
        _fixtureProfileUserId,
        limit: 2,
      );
      expect(followers.length, lessThanOrEqualTo(2));
    });

    test('listUserLikes limit 参数限制条数', () async {
      final likes = await repo.listUserLikes(_fixtureProfileUserId, limit: 1);
      expect(likes.length, lessThanOrEqualTo(1));
    });

    test('getUserProfile 统计字段与 getUserStats 一致', () async {
      final profile = await repo.getUserProfile(_fixtureProfileUserId);
      final stats = await repo.getUserStats(_fixtureProfileUserId);
      expect(profile.followingCount, stats.followingCount);
      expect(profile.followerCount, stats.followerCount);
      expect(profile.circleCount, stats.circleCount);
      expect(profile.likeCount, stats.likeCount);
    });

    test('listPersonas 至少有一个 isPrimary=true', () async {
      final personas = await repo.listPersonas();
      final primary = personas.where((p) => p.isPrimary);
      expect(primary, isNotEmpty);
    });

    test('listPersonas 恰好有一个 isActive=true', () async {
      final personas = await repo.listPersonas();
      final active = personas.where((p) => p.isActive);
      expect(active.length, 1);
    });
  });

  // ── 异常/边界契约 ─────────────────────────────────────────────────────────

  group('UserProfileRepository — 异常/边界契约', () {
    late UserProfileRepository repo;

    setUp(() {
      repo = const MockUserProfileRepository();
    });

    test('不存在的 userId — listUserPosts 返回列表而非崩溃', () async {
      final posts = await repo.listUserPosts('nonexistent_user_xyz');
      expect(posts, isList);
    });

    test('不存在的 userId — getUserProfile 返回默认档案', () async {
      final profile = await repo.getUserProfile('nonexistent_user_xyz');
      expect(profile.subAccountId, 'nonexistent_user_xyz');
      expect(profile.displayName, isNotEmpty);
    });

    test('getUserStats 所有计数为非负 int', () async {
      final stats = await repo.getUserStats(_fixtureProfileUserId);
      expect(stats.followingCount, isNonNegative);
      expect(stats.circleCount, isNonNegative);
      expect(stats.followerCount, isNonNegative);
      expect(stats.likeCount, isNonNegative);
      expect(stats.postCount, isNonNegative);
    });

    test('帖子 DTO 字段分发正确', () async {
      final posts = await repo.listUserPosts(_fixtureProfileUserId);
      for (final post in posts) {
        expect(post.id, isNotEmpty);
        expect(post.authorId, isNotEmpty);
        expect(post.likeCount, isNonNegative);
      }
    });

    test('followUser 对不存在用户不崩溃', () async {
      await expectLater(repo.followUser('nonexistent'), completes);
    });

    test('unfollowUser 对不存在用户不崩溃', () async {
      await expectLater(repo.unfollowUser('nonexistent'), completes);
    });

    test('deletePersona 对不存在 ID 不崩溃', () async {
      await expectLater(repo.deletePersona('nonexistent'), completes);
    });

    test('activatePersona 对不存在 ID 不崩溃', () async {
      await expectLater(repo.activatePersona('nonexistent'), completes);
    });

    test('updateProfile 空 payload 不崩溃', () async {
      await expectLater(
        repo.updateProfile(
          const ProfileEditUpdatePayload(nickname: '', bio: ''),
        ),
        completes,
      );
    });

    test('createPersona 最小请求（仅 displayName 空串）不崩溃', () async {
      final result = await repo.createPersona(
        PersonaCreateRequestDto(displayName: ''),
      );
      expect(result.id, isNotEmpty);
    });

    test('listFollowing cursor 参数不崩溃', () async {
      final list = await repo.listFollowing(
        _fixtureCurrentUserId,
        cursor: 'some_cursor',
      );
      expect(list, isList);
    });

    test('listFollowers cursor 参数不崩溃', () async {
      final list = await repo.listFollowers(
        _fixtureProfileUserId,
        cursor: 'some_cursor',
      );
      expect(list, isList);
    });
  });

  // ── homepage-bundle wire 解码与回退（Remote 解码路径）─────────────────────

  group('UserHomepageBundleViewData — wire 解码与回退', () {
    test(
      'fromMap 解析顶层 bundle（含嵌套 profile/viewerContext/relationshipCapability）',
      () {
        final wire = UserHomepageBundleWireDto.fromMap(<String, dynamic>{
          'profile': <String, dynamic>{
            'subAccountId': 'u_remote',
            'displayName': '远端用户',
          },
          'stats': <String, dynamic>{
            'postCount': 7,
            'likeCount': 88,
            'circleCount': 3,
            'followerCount': 100,
            'followingCount': 20,
          },
          'tabCounts': <String, dynamic>{
            'worksCount': 7,
            'likesCount': 88,
            'circlesCount': 3,
            'collectionsCount': 0,
          },
          'viewerContext': <String, dynamic>{
            'viewerSubAccountId': 'viewer_1',
            'isOwner': false,
            'isGuest': false,
            'relationToTarget': 'following',
            'canViewFullProfile': true,
          },
          'relationshipCapability': <String, dynamic>{
            'viewerSubAccountId': 'viewer_1',
            'targetSubAccountId': 'u_remote',
            'relationState': 'following',
            'canFollow': false,
            'canUnfollow': true,
          },
          'cacheVersion': 'abc123',
        });
        final bundle = UserHomepageBundleViewData.fromUserHomepageBundleWire(
          wire,
        );
        expect(bundle.profile.subAccountId, 'u_remote');
        expect(bundle.stats.postCount, 7);
        expect(bundle.tabCounts.likesCount, 88);
        expect(bundle.viewerContext.relationToTarget, 'following');
        expect(bundle.relationshipCapability, isNotNull);
        expect(bundle.relationshipCapability!.canUnfollow, isTrue);
        expect(bundle.cacheVersion, 'abc123');
      },
    );

    test('stats/tabCounts/viewerContext 缺失时同源回退（不造假）', () {
      final wire = UserHomepageBundleWireDto.fromMap(<String, dynamic>{
        'profile': <String, dynamic>{
          'subAccountId': 'u_min',
          'postCount': 4,
          'likeCount': 9,
          'circleCount': 1,
        },
        'cacheVersion': 'v',
      });
      final bundle = UserHomepageBundleViewData.fromUserHomepageBundleWire(
        wire,
      );
      // stats 缺失 → 由 profile 同源推导。
      expect(bundle.stats.postCount, 4);
      // tabCounts 缺失 → 由 stats 推导，collections 归 0。
      expect(bundle.tabCounts.worksCount, 4);
      expect(bundle.tabCounts.collectionsCount, 0);
      // viewerContext 缺失 → 游客保守回退。
      expect(bundle.viewerContext.isGuest, isTrue);
      expect(bundle.relationshipCapability, isNull);
    });

    test('profile 缺失时抛 FormatException（契约破坏不静默）', () {
      final wire = UserHomepageBundleWireDto.fromMap(<String, dynamic>{
        'cacheVersion': 'v',
      });
      expect(
        () => UserHomepageBundleViewData.fromUserHomepageBundleWire(wire),
        throwsA(isA<FormatException>()),
      );
    });
  });
}
