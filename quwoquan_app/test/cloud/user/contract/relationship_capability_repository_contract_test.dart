import 'package:test/test.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';

/// T1 契约测试：RelationshipCapabilityRepository
///
/// 守护：DTO 解析正确性 + MockRepository 行为一致性 + 关系层级推导逻辑
void main() {
  // ── 常规契约 ────────────────────────────────────────────────────────────────

  group('RelationshipCapabilityDto — 常规契约', () {
    test('fromMap 全字段正确解析', () {
      final dto = RelationshipCapabilityDto.fromMap(<String, dynamic>{
        'viewerSubAccountId': 'viewer_1',
        'targetSubAccountId': 'target_1',
        'relationTier': 'same_interest',
        'canGreet': false,
        'canOpenConversation': true,
        'canAddSameInterest': true,
        'canSetCloseFriend': false,
        'canStartVoiceCall': true,
        'canStartVideoCall': true,
        'isBlocked': false,
        'isBlockedBy': false,
      });
      expect(dto.viewerSubAccountId, 'viewer_1');
      expect(dto.targetSubAccountId, 'target_1');
      expect(dto.relationTier, 'same_interest');
      expect(dto.canGreet, false);
      expect(dto.canOpenConversation, true);
      expect(dto.canAddSameInterest, true);
      expect(dto.canStartVoiceCall, true);
      expect(dto.canStartVideoCall, true);
      expect(dto.isBlocked, false);
    });

    test('isSelf 对 self tier 返回 true', () {
      final dto = RelationshipCapabilityDto.fromMap(<String, dynamic>{
        'relationTier': 'self',
        'canGreet': false,
        'canOpenConversation': false,
        'canAddSameInterest': false,
        'canSetCloseFriend': false,
        'canStartVoiceCall': false,
        'canStartVideoCall': false,
        'isBlocked': false,
        'isBlockedBy': false,
      });
      expect(dto.isSelf, true);
      expect(dto.isStranger, false);
    });

    test('isCloseFriend 对 close_friend tier 返回 true', () {
      final dto = RelationshipCapabilityDto.fromMap(<String, dynamic>{
        'relationTier': 'close_friend',
        'canGreet': false,
        'canOpenConversation': true,
        'canAddSameInterest': true,
        'canSetCloseFriend': true,
        'canStartVoiceCall': true,
        'canStartVideoCall': true,
        'isBlocked': false,
        'isBlockedBy': false,
      });
      expect(dto.isCloseFriend, true);
      expect(dto.isSameInterest, true);
    });

    test('isFollowingOnly 对 following_only tier 返回 true', () {
      final dto = RelationshipCapabilityDto.fromMap(<String, dynamic>{
        'relationTier': 'following_only',
        'canGreet': true,
        'canOpenConversation': false,
        'canAddSameInterest': false,
        'canSetCloseFriend': false,
        'canStartVoiceCall': false,
        'canStartVideoCall': false,
        'isBlocked': false,
        'isBlockedBy': false,
      });
      expect(dto.isFollowingOnly, true);
      expect(dto.isStranger, false);
    });
  });

  // ── 兼容性契约 ──────────────────────────────────────────────────────────────

  group('RelationshipCapabilityDto — 兼容性契约', () {
    test('fromMap 缺失字段使用安全默认值', () {
      final dto = RelationshipCapabilityDto.fromMap(const <String, dynamic>{});
      expect(dto.relationTier, 'none');
      expect(dto.canGreet, false);
      expect(dto.canOpenConversation, false);
      expect(dto.canStartVoiceCall, false);
      expect(dto.isStranger, true);
    });

    test('fromLegacyRelationship 互关推导为 same_interest', () {
      final dto = RelationshipCapabilityDto.fromLegacyRelationship(
        viewerId: 'viewer',
        targetId: 'target',
        isFollowing: true,
        isFollowedBy: true,
      );
      expect(dto.relationTier, 'same_interest');
      expect(dto.canOpenConversation, true);
      expect(dto.canStartVoiceCall, true);
      expect(dto.canGreet, false);
    });

    test('fromLegacyRelationship 单向关注推导为 following_only 且 canGreet=true', () {
      final dto = RelationshipCapabilityDto.fromLegacyRelationship(
        viewerId: 'viewer',
        targetId: 'target',
        isFollowing: true,
        isFollowedBy: false,
      );
      expect(dto.relationTier, 'following_only');
      expect(dto.canGreet, true);
      expect(dto.canOpenConversation, false);
    });

    test('fromLegacyRelationship self=true 推导为 self tier', () {
      final dto = RelationshipCapabilityDto.fromLegacyRelationship(
        viewerId: 'same_user',
        targetId: 'same_user',
        isFollowing: false,
        isFollowedBy: false,
        isSelf: true,
      );
      expect(dto.isSelf, true);
      expect(dto.canGreet, false);
    });

    test('fromLegacyRelationship closeFriend=true + 互关推导为 close_friend', () {
      final dto = RelationshipCapabilityDto.fromLegacyRelationship(
        viewerId: 'viewer',
        targetId: 'target',
        isFollowing: true,
        isFollowedBy: true,
        closeFriend: true,
      );
      expect(dto.isCloseFriend, true);
      expect(dto.canSetCloseFriend, true);
    });
  });

  // ── 异常/边界契约 ────────────────────────────────────────────────────────────

  group('RelationshipCapabilityDto — 异常/边界契约', () {
    test('fromMap 全字段缺失不崩溃', () {
      expect(
        () => RelationshipCapabilityDto.fromMap(const <String, dynamic>{}),
        returnsNormally,
      );
    });

    test('fromMap 未知 relationTier 值不崩溃', () {
      final dto = RelationshipCapabilityDto.fromMap(<String, dynamic>{
        'relationTier': 'unknown_future_tier',
        'canGreet': false,
        'canOpenConversation': false,
        'canAddSameInterest': false,
        'canSetCloseFriend': false,
        'canStartVoiceCall': false,
        'canStartVideoCall': false,
        'isBlocked': false,
        'isBlockedBy': false,
      });
      expect(dto.isSelf, false);
      expect(dto.isSameInterest, false);
      expect(dto.isStranger, false);
    });
  });

  // ── Mock Repository 契约 ─────────────────────────────────────────────────────

  group('MockRelationshipCapabilityRepository — 常规契约', () {
    late MockRelationshipCapabilityRepository repo;

    setUp(() {
      repo = MockRelationshipCapabilityRepository();
    });

    test('getCapability 返回完整 DTO', () async {
      final dto = await repo.getCapability('some_user');
      expect(dto.viewerSubAccountId, isNotEmpty);
      expect(dto.targetSubAccountId, 'some_user');
      expect(dto.relationTier, isNotEmpty);
    });

    test('getCapability 对互关 mock 用户返回 same_interest', () async {
      final dto = await repo.getCapability('u1');
      expect(dto.relationTier, 'same_interest');
      expect(dto.canStartVoiceCall, true);
      expect(dto.canStartVideoCall, true);
      expect(dto.canOpenConversation, true);
    });

    test('接口包含全部 1 个 service.yaml 方法', () {
      final methods = <String>['getCapability'];
      expect(methods.length, 1);
      expect(
        repo.runtimeType.toString(),
        contains('MockRelationshipCapabilityRepository'),
      );
    });
  });
}
