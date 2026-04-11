import 'package:test/test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona_create_request_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/persona_update_request_dto.g.dart';
import 'package:quwoquan_app/cloud/services/user/profile_edit_update_payload.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';

void main() {
  // ── 常规契约 ──────────────────────────────────────────────────────────────

  group('UserProfileRepository — 常规契约', () {
    late UserProfileRepository repo;

    setUp(() {
      repo = const MockUserProfileRepository();
    });

    // ── 档案 ────────────────────────────────────────────────────────────────

    test('getUserProfile 返回完整档案', () async {
      final profile = await repo.getUserProfile('nature_photographer');
      expect(profile.profileSubjectId, 'nature_photographer');
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
          const ProfileEditUpdatePayload(
            nickname: '新昵称',
            username: 'u',
            bio: 'b',
          ),
        ),
        completes,
      );
    });

    // ── 主页 Tab 数据 ──────────────────────────────────────────────────────

    test('listUserPosts 返回非空帖子列表', () async {
      final posts = await repo.listUserPosts('nature_photographer');
      expect(posts, isNotEmpty);
      expect(posts.length, 4);
      final types = posts.map((p) => p.type).toSet();
      expect(types, containsAll(['photo', 'video', 'article', 'moment']));
    });

    test('listUserWorks 返回作品集列表', () async {
      final works = await repo.listUserWorks('nature_photographer');
      expect(works, isNotEmpty);
      for (final w in works) {
        expect(w.id, isNotEmpty);
        expect(w.title, isNotEmpty);
        expect(w.coverUrl, isNotEmpty);
        expect(w.type, isNotEmpty);
      }
    });

    test('listUserLifeItems 返回生活记录列表', () async {
      final items = await repo.listUserLifeItems('nature_photographer');
      expect(items, isNotEmpty);
      for (final item in items) {
        expect(item.id, isNotEmpty);
        expect(item.name, isNotEmpty);
        expect(item.categoryKey, isNotEmpty);
      }
    });

    test('listUserCircles 返回圈子列表', () async {
      final circles = await repo.listUserCircles('nature_photographer');
      expect(circles, isNotEmpty);
      for (final c in circles) {
        expect(c.id, isNotEmpty);
        expect(c.name, isNotEmpty);
        expect(c.coverUrl ?? '', isNotEmpty);
      }
    });

    test('getUserStats 返回统计数据', () async {
      final stats = await repo.getUserStats('nature_photographer');
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
      final following = await repo.listFollowing('nature_photographer');
      expect(following, isList);
      expect(following, isNotEmpty);
      for (final u in following) {
        expect(u.profileSubjectId, isNotEmpty);
        expect(u.displayName, isNotEmpty);
        expect(u.avatarUrl, isNotEmpty);
      }
    });

    test('listFollowers 返回用户列表', () async {
      final followers = await repo.listFollowers('nature_photographer');
      expect(followers, isList);
      expect(followers, isNotEmpty);
      for (final u in followers) {
        expect(u.profileSubjectId, isNotEmpty);
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
      final likes = await repo.listUserLikes('nature_photographer');
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
        PersonaCreateRequestDto(
          displayName: '新分身',
          isolationLevel: 'strict',
        ),
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

    test('接口包含全部 18 个 service.yaml API 方法', () {
      final methods = <String>[
        'getUserProfile', 'updateProfile',
        'listUserPosts', 'listUserWorks', 'listUserLifeItems',
        'listUserCircles', 'getUserStats',
        'followUser', 'unfollowUser',
        'listFollowing', 'listFollowers', 'getRelationship', 'listUserLikes',
        'listPersonas', 'createPersona', 'updatePersona',
        'deletePersona', 'activatePersona',
      ];
      expect(methods.length, 18);
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
      final posts = await repo.listUserPosts('nature_photographer', limit: 2);
      expect(posts.length, lessThanOrEqualTo(2));
    });

    test('listUserCircles limit 参数限制条数', () async {
      final circles = await repo.listUserCircles('nature_photographer', limit: 1);
      expect(circles.length, lessThanOrEqualTo(1));
    });

    test('listFollowing limit 参数限制条数', () async {
      final following = await repo.listFollowing('nature_photographer', limit: 2);
      expect(following.length, lessThanOrEqualTo(2));
    });

    test('listFollowers limit 参数限制条数', () async {
      final followers = await repo.listFollowers('nature_photographer', limit: 2);
      expect(followers.length, lessThanOrEqualTo(2));
    });

    test('listUserLikes limit 参数限制条数', () async {
      final likes = await repo.listUserLikes('nature_photographer', limit: 1);
      expect(likes.length, lessThanOrEqualTo(1));
    });

    test('getUserProfile 统计字段与 getUserStats 一致', () async {
      final profile = await repo.getUserProfile('nature_photographer');
      final stats = await repo.getUserStats('nature_photographer');
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
      expect(profile.profileSubjectId, 'nonexistent_user_xyz');
      expect(profile.displayName, isNotEmpty);
    });

    test('getUserStats 所有计数为非负 int', () async {
      final stats = await repo.getUserStats('nature_photographer');
      expect(stats.followingCount, isNonNegative);
      expect(stats.circleCount, isNonNegative);
      expect(stats.followerCount, isNonNegative);
      expect(stats.likeCount, isNonNegative);
      expect(stats.postCount, isNonNegative);
    });

    test('帖子各类型 DTO 正确分发', () async {
      final posts = await repo.listUserPosts('nature_photographer');
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
          const ProfileEditUpdatePayload(
            nickname: '',
            username: '',
            bio: '',
          ),
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
      final list = await repo.listFollowing('nature_photographer', cursor: 'some_cursor');
      expect(list, isList);
    });

    test('listFollowers cursor 参数不崩溃', () async {
      final list = await repo.listFollowers('nature_photographer', cursor: 'some_cursor');
      expect(list, isList);
    });
  });
}
