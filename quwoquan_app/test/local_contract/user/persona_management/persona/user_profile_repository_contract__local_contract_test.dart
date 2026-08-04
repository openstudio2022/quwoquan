import 'package:quwoquan_app/user/persona_management/persona/application/persona_query.dart';
import 'package:quwoquan_app/user/relationship/persona_relationship/application/persona_relationship_facets.dart';
import 'package:quwoquan_app/application/user/profile/profile_edit_query.dart';
import 'package:quwoquan_app/application/user/profile/profile_query.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_errors.g.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    as contracts;
import 'package:test/test.dart';

import '../../../../support/user/account/credential_binding/credential_binding_typed_double.dart';
import '../../../../support/user/account/user_account/user_account_profile_typed_double.dart';
import '../../../../support/fakes/test_persona_facets.dart';

const _fixtureCurrentUserId = 'fixture_user_current';
const _fixtureProfileUserId = 'fixture_user_photo';

void main() {
  group('ProfileQuery alpha fixture parity', () {
    late ProfileQuery query;

    setUp(() {
      query = const MockUserProfileRepository();
    });

    test('公开资料、统计与主页聚合读取同一 profile 真相', () async {
      final profile = await query.getUserProfile(_fixtureProfileUserId);
      final stats = await query.getUserStats(_fixtureProfileUserId);
      final bundle = await query.getUserHomepageBundle(_fixtureProfileUserId);

      expect(profile.personaId, _fixtureProfileUserId);
      expect(profile.displayName, isNotEmpty);
      expect(profile.userHandle, isNotEmpty);
      expect(stats.followingCount, profile.followingCount);
      expect(stats.followerCount, profile.followerCount);
      expect(stats.circleCount, profile.circleCount);
      expect(stats.likeCount, profile.likeCount);
      expect(stats.postCount, profile.postCount);
      expect(bundle.profile.personaId, profile.personaId);
      expect(bundle.profileWithStats.followerCount, bundle.stats.followerCount);
      expect(bundle.tabCounts.worksCount, bundle.stats.postCount);
      expect(bundle.tabCounts.likesCount, bundle.stats.likeCount);
      expect(bundle.tabCounts.circlesCount, bundle.stats.circleCount);
      expect(bundle.tabCounts.collectionsCount, 0);
    });

    test('本人主页不下发关系动作，他人主页下发目标一致的能力', () async {
      final mine = await query.getUserHomepageBundle(_fixtureCurrentUserId);
      final other = await query.getUserHomepageBundle(_fixtureProfileUserId);

      expect(mine.viewerContext.isOwner, isTrue);
      expect(mine.viewerContext.relationToTarget, 'self');
      expect(mine.relationshipCapability, isNull);
      expect(other.viewerContext.isOwner, isFalse);
      expect(
        other.relationshipCapability?.targetPersonaId,
        _fixtureProfileUserId,
      );
    });

    test('未知用户保持 alpha 安全回退，计数不为负', () async {
      final profile = await query.getUserProfile('nonexistent_user_xyz');
      final stats = await query.getUserStats('nonexistent_user_xyz');

      expect(profile.personaId, 'nonexistent_user_xyz');
      expect(profile.displayName, isNotEmpty);
      expect(stats.followingCount, isNonNegative);
      expect(stats.followerCount, isNonNegative);
      expect(stats.circleCount, isNonNegative);
      expect(stats.likeCount, isNonNegative);
      expect(stats.postCount, isNonNegative);
    });

    test('社会关系搜索返回强类型结果且遵守 limit', () async {
      final results = await query.searchSocialRelations(
        query: _fixtureProfileUserId,
        limit: 1,
      );

      expect(results.length, lessThanOrEqualTo(1));
      expect(results, isNotEmpty);
      expect(results.single.personaId, _fixtureProfileUserId);
    });
  });

  group('ProfileEditQuery alpha fixture parity', () {
    late ProfileEditQuery query;

    setUp(() {
      query = const MockUserProfileRepository();
    });

    test('编辑快照与二维码卡片保留真实强类型字段', () async {
      final snapshot = await query.getProfileEditSnapshot();
      final card = await query.getProfileQrCard();

      expect(snapshot.personaId, isNotEmpty);
      expect(snapshot.nickname, isNotEmpty);
      expect(card.qrPayload, isNotEmpty);
      expect(card.publicProfileUrl, isNotEmpty);
    });

    test('二维码解析返回 accepted 目标，空 token fail-fast', () async {
      final resolved = await query.resolveProfileQrToken(
        token: 'opaque-token',
        handle: _fixtureProfileUserId,
      );

      expect(resolved.personaId, _fixtureProfileUserId);
      expect(resolved.scanStatus, 'accepted');
      await expectLater(
        query.resolveProfileQrToken(token: ''),
        throwsArgumentError,
      );
    });
  });

  group('ProfileCommandWriter alpha parity', () {
    test('资料命令返回规范快照与递增版本', () async {
      final contracts.ProfileCommandWriter writer = AlphaProfileCommandWriter();
      final result = await writer.updateUserProfile(
        contracts.UpdateUserProfileCommand(
          nickname: '资料同步用户',
          bio: '资料编辑单轨命令验证',
          avatarAssetId: 'asset_avatar_1',
          avatarUrl: 'https://cdn.example.test/avatar.jpg',
          backgroundAssetId: 'asset_cover_1',
          backgroundUrl: 'https://cdn.example.test/cover.jpg',
          gender: 'female',
          birthDate: '1996-05-21',
          regionTagRef: 'Topic/地理/行政区/中国/广东省/云浮市',
          occupationTagRef: 'Audience/用户/职业/产品/产品经理',
          interestTagRefs: const <String>['Audience/用户/兴趣偏好/影像/摄影'],
          expectedTaxonomyReleaseId: 'taxonomy-release-test',
        ),
      );

      expect(result.nickname, '资料同步用户');
      expect(result.bio, '资料编辑单轨命令验证');
      expect(result.avatarAssetId, 'asset_avatar_1');
      expect(result.backgroundAssetId, 'asset_cover_1');
      expect(result.gender, 'female');
      expect(
        result.identityTags,
        containsAll(<String>[
          'Audience/用户/职业/产品/产品经理',
          'Audience/用户/兴趣偏好/影像/摄影',
        ]),
      );
      expect(result.profileVersion, greaterThan(1));
    });
  });

  group('PersonaQuery 与 PersonaManagementCommandWriter parity', () {
    late TestPersonaFacets facets;
    late PersonaQuery query;
    late contracts.PersonaManagementCommandWriter commands;

    setUp(() {
      facets = TestPersonaFacets();
      query = facets;
      commands = facets;
    });

    test('列表恰有一个主分身和一个活跃分身', () async {
      final personas = await query.listPersonas();

      expect(personas.where((item) => item.isPrimary), hasLength(1));
      expect(personas.where((item) => item.isActive), hasLength(1));
      expect((await query.getActivePersonaContext()).personaId, isNotEmpty);
    });

    test('创建、更新与激活后查询投影立即一致', () async {
      final created = await commands.createPersona(
        contracts.CreatePersonaCommand(
          displayName: '新分身',
          isolationLevel: 'strict',
        ),
      );
      final updated = await commands.updatePersona(
        contracts.UpdatePersonaCommand(
          personaId: created.personaId,
          displayName: '更新名',
        ),
      );
      final active = await commands.activatePersona(
        contracts.ActivatePersonaCommand(personaId: created.personaId),
      );

      expect(created.displayName, '新分身');
      expect(updated.displayName, '更新名');
      expect(active.personaId, created.personaId);
      expect(
        (await query.listPersonas())
            .singleWhere((item) => item.personaId == created.personaId)
            .isActive,
        isTrue,
      );
    });

    test('主分身守卫拒绝退役并映射结构化错误', () async {
      final guard = await query.getPersonaLifecycleGuard('persona_primary');
      expect(guard.requestedAction, 'retire');
      expect(guard.allowed, isFalse);
      expect(guard.reason, 'blocked_primary_persona');
      expect(guard.requiresSuccessor, isFalse);

      await expectLater(
        commands.retirePersona(
          contracts.RetirePersonaCommand(personaId: 'persona_primary'),
        ),
        throwsA(
          isA<CloudException>()
              .having(
                (error) => error.code,
                'code',
                UserErrorCode.primaryPersonaGuard.code,
              )
              .having(
                (error) => error.runtimeFailure.code,
                'runtimeFailure.code',
                UserErrorCode.primaryPersonaGuard.code,
              ),
        ),
      );
    });
  });

  group('PersonaRelationship Facet parity', () {
    late _TestPersonaRelationshipFacets facets;
    late PersonaRelationshipQuery query;
    late PersonaRelationshipCommandWriter commands;

    setUp(() {
      facets = _TestPersonaRelationshipFacets();
      query = facets;
      commands = facets;
    });

    test('follow/unfollow 与 following 查询共享同一强类型状态', () async {
      expect(
        (await query.listFollowing(personaId: _fixtureCurrentUserId)).items,
        isEmpty,
      );

      await commands.follow(
        _fixtureProfileUserId,
        sourceSurfaceId: 'userProfile',
      );
      final following = await query.listFollowing(
        personaId: _fixtureCurrentUserId,
        limit: 1,
      );
      expect(following.items, hasLength(1));
      expect(following.items.single.personaId, _fixtureProfileUserId);

      await commands.unfollow(_fixtureProfileUserId);
      expect(
        (await query.listFollowing(personaId: _fixtureCurrentUserId)).items,
        isEmpty,
      );
    });

    test('followers 查询保留 typed cursor page 与 limit 边界', () async {
      final followers = await query.listFollowers(
        personaId: _fixtureProfileUserId,
        limit: 1,
      );

      expect(followers.items, hasLength(1));
      expect(followers.totalCount, 1);
      expect(followers.nextCursor, isNull);
    });
  });
}

final class _TestPersonaRelationshipFacets
    implements PersonaRelationshipQuery, PersonaRelationshipCommandWriter {
  bool _following = false;

  ProfileSocialRelationRowViewData get _row =>
      const ProfileSocialRelationRowViewData(
        personaId: _fixtureProfileUserId,
        userHandle: 'fixture_photo',
        displayName: 'Fixture Photo',
        avatarUrl: 'media/avatar/s/mock/user/fixture_user_photo/v1/avatar.png',
        profileVisibility: 'public',
        relationState: 'following',
      );

  @override
  Future<void> follow(
    String targetPersonaId, {
    required String sourceSurfaceId,
  }) async {
    if (targetPersonaId.trim().isEmpty) {
      throw ArgumentError.value(targetPersonaId, 'targetPersonaId');
    }
    _following = true;
  }

  @override
  Future<void> unfollow(String targetPersonaId) async {
    if (targetPersonaId.trim().isEmpty) {
      throw ArgumentError.value(targetPersonaId, 'targetPersonaId');
    }
    _following = false;
  }

  @override
  Future<CursorPage<ProfileSocialRelationRowViewData>> listFollowing({
    required String personaId,
    String? query,
    String? cursor,
    int limit = 20,
  }) async {
    final items = _following
        ? <ProfileSocialRelationRowViewData>[_row]
        : const <ProfileSocialRelationRowViewData>[];
    return _page(items, query: query, cursor: cursor, limit: limit);
  }

  @override
  Future<CursorPage<ProfileSocialRelationRowViewData>> listFollowers({
    required String personaId,
    String? query,
    String? cursor,
    int limit = 20,
  }) async {
    return _page(
      <ProfileSocialRelationRowViewData>[_row],
      query: query,
      cursor: cursor,
      limit: limit,
    );
  }

  CursorPage<ProfileSocialRelationRowViewData> _page(
    List<ProfileSocialRelationRowViewData> source, {
    required String? query,
    required String? cursor,
    required int limit,
  }) {
    final normalized = query?.trim().toLowerCase() ?? '';
    final filtered = normalized.isEmpty
        ? source
        : source
              .where(
                (item) =>
                    item.displayName.toLowerCase().contains(normalized) ||
                    item.userHandle.toLowerCase().contains(normalized),
              )
              .toList(growable: false);
    final start = int.tryParse(cursor ?? '') ?? 0;
    final safeStart = start < 0
        ? 0
        : start > filtered.length
        ? filtered.length
        : start;
    final safeLimit = limit <= 0 ? 20 : limit;
    final requestedEnd = safeStart + safeLimit;
    final end = requestedEnd > filtered.length ? filtered.length : requestedEnd;
    return CursorPage<ProfileSocialRelationRowViewData>(
      items: filtered.sublist(safeStart, end),
      nextCursor: end < filtered.length ? '$end' : null,
      totalCount: filtered.length,
    );
  }
}
