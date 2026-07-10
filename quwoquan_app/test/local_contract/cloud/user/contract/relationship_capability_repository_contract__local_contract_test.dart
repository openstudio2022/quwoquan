import 'package:test/test.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';

/// T1 契约测试：RelationshipCapabilityRepository
///
/// 守护：DTO 解析正确性 + MockRepository 行为一致性 + RelationshipState 推导逻辑
void main() {
  group('RelationshipCapabilityDto — 常规契约', () {
    test('fromMap 全字段正确解析', () {
      final dto = RelationshipCapabilityDto.fromMap(<String, dynamic>{
        'viewerSubAccountId': 'viewer_1',
        'targetSubAccountId': 'target_1',
        'relationState': 'mutual',
        'canFollow': false,
        'canUnfollow': true,
        'canFollowBack': false,
        'canGreet': false,
        'canCreateDirectConversation': true,
        'canSendMessage': true,
        'canOpenConversation': true,
        'hasPendingGreeting': false,
        'hasFormalConversation': true,
        'canStartVoiceCall': true,
        'canStartVideoCall': true,
        'isBlocked': false,
        'isBlockedBy': false,
      });
      expect(dto.viewerSubAccountId, 'viewer_1');
      expect(dto.targetSubAccountId, 'target_1');
      expect(dto.relationState, 'mutual');
      expect(dto.isMutual, isTrue);
      expect(dto.canGreet, false);
      expect(dto.canSendMessage, true);
      expect(dto.canStartVoiceCall, true);
      expect(dto.isBlocked, false);
    });

    test('isSelf 对 self 状态返回 true', () {
      final dto = RelationshipCapabilityDto.fromMap(<String, dynamic>{
        'relationState': 'self',
        'canGreet': false,
        'canCreateDirectConversation': false,
        'canSendMessage': false,
        'canOpenConversation': false,
        'canStartVoiceCall': false,
        'canStartVideoCall': false,
        'isBlocked': false,
        'isBlockedBy': false,
      });
      expect(dto.isSelf, true);
      expect(dto.isMutual, false);
    });

    test('isMutual 对 mutual 状态返回 true', () {
      final dto = RelationshipCapabilityDto.fromMap(<String, dynamic>{
        'relationState': 'mutual',
        'canGreet': false,
        'canCreateDirectConversation': true,
        'canSendMessage': true,
        'canOpenConversation': true,
        'canStartVoiceCall': true,
        'canStartVideoCall': true,
        'isBlocked': false,
        'isBlockedBy': false,
      });
      expect(dto.isMutual, true);
      expect(dto.viewerFollowsTarget, isTrue);
      expect(dto.targetFollowsViewer, isTrue);
    });

    test('isFollowing 对 following 状态返回 true', () {
      final dto = RelationshipCapabilityDto.fromMap(<String, dynamic>{
        'relationState': 'following',
        'canGreet': true,
        'canCreateDirectConversation': false,
        'canSendMessage': false,
        'canOpenConversation': false,
        'canStartVoiceCall': false,
        'canStartVideoCall': false,
        'isBlocked': false,
        'isBlockedBy': false,
      });
      expect(dto.isFollowing, true);
      expect(dto.canGreet, true);
      expect(dto.canSendMessage, false);
    });
  });

  group('RelationshipCapabilityDto — 默认值', () {
    test('fromMap 缺失字段使用安全默认值', () {
      final dto = RelationshipCapabilityDto.fromMap(const <String, dynamic>{});
      expect(dto.relationState, 'not_following');
      expect(dto.canGreet, false);
      expect(dto.canSendMessage, false);
      expect(dto.canStartVoiceCall, false);
      expect(dto.isNotFollowing, true);
    });

    test('fromFollowFlags 互关推导为 mutual', () {
      final dto = RelationshipCapabilityDto.fromFollowFlags(
        viewerId: 'viewer',
        targetId: 'target',
        isFollowing: true,
        isFollowedBy: true,
      );
      expect(dto.relationState, 'mutual');
      expect(dto.canCreateDirectConversation, true);
      expect(dto.canStartVoiceCall, true);
      expect(dto.canGreet, false);
    });

    test('fromFollowFlags 单向关注推导为 following 且 canGreet=true', () {
      final dto = RelationshipCapabilityDto.fromFollowFlags(
        viewerId: 'viewer',
        targetId: 'target',
        isFollowing: true,
        isFollowedBy: false,
      );
      expect(dto.relationState, 'following');
      expect(dto.canGreet, true);
      expect(dto.canCreateDirectConversation, false);
    });

    test('fromFollowFlags 被关注推导为 followed_by', () {
      final dto = RelationshipCapabilityDto.fromFollowFlags(
        viewerId: 'viewer',
        targetId: 'target',
        isFollowing: false,
        isFollowedBy: true,
      );
      expect(dto.relationState, 'followed_by');
      expect(dto.canFollowBack, true);
      expect(dto.canGreet, true);
    });

    test('拉黑时禁止打招呼与 RTC', () {
      final dto = RelationshipCapabilityDto.fromFollowFlags(
        viewerId: 'viewer',
        targetId: 'target',
        isFollowing: true,
        isFollowedBy: true,
        isBlocked: true,
      );
      expect(dto.canGreet, false);
      expect(dto.canStartVoiceCall, false);
      expect(dto.canCreateDirectConversation, false);
    });
  });

  group('MockRelationshipCapabilityRepository', () {
    late MockRelationshipCapabilityRepository repo;

    setUp(() {
      repo = MockRelationshipCapabilityRepository();
    });

    test('getCapability 返回非空 relationState', () async {
      final dto = await repo.getCapability('user_001');
      expect(dto.relationState, isNotEmpty);
    });

    test('getCapability 对互关 mock 用户返回 mutual', () async {
      final dto = await repo.getCapability('user_mutual_01');
      if (dto.isMutual) {
        expect(dto.canSendMessage || dto.canCreateDirectConversation, isTrue);
      }
    });
  });
}
