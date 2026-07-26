// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/conversation-entry-matrix/spec.md#gwt-001
// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/spec.md#sit-005
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock.dart';
import 'package:test/test.dart';

void main() {
  group('RelationshipCapability typed contract', () {
    test('decoder 严格解析 canonical capability', () {
      final result = decodeRelationshipCapabilityResult(const <String, Object?>{
        'viewerSubAccountId': 'viewer_1',
        'targetSubAccountId': 'target_1',
        'relationState': 'mutual',
        'canFollow': false,
        'canUnfollow': true,
        'canFollowBack': false,
        'canGreet': false,
        'canOpenConversation': true,
        'canCreateDirectConversation': true,
        'canSendMessage': true,
        'hasPendingGreeting': false,
        'hasFormalConversation': true,
        'canStartVoiceCall': true,
        'canStartVideoCall': true,
        'isBlocked': false,
        'isBlockedBy': false,
      });

      expect(result.viewerSubAccountId, 'viewer_1');
      expect(result.targetSubAccountId, 'target_1');
      expect(result.relationState, 'mutual');
      expect(result.canSendMessage, isTrue);
      expect(result.canStartVoiceCall, isTrue);
    });

    test('decoder 不为缺失能力位合成默认值', () {
      expect(
        () => decodeRelationshipCapabilityResult(const <String, Object?>{
          'viewerSubAccountId': 'viewer_1',
          'targetSubAccountId': 'target_1',
          'relationState': 'mutual',
        }),
        throwsFormatException,
      );
    });

    test('query encoder 只携带 canonical subAccountId path 参数', () {
      final payload = encodeGetRelationshipCapabilityQuery(
        GetRelationshipCapabilityQuery(targetSubAccountId: 'target_1'),
      );
      expect(payload.pathParameters, <String, String>{
        'subAccountId': 'target_1',
      });
    });
  });

  group('AlphaPersonaRelationshipFacet', () {
    test('fixture 互关对象开放消息、会话与 RTC', () async {
      final facet = AlphaPersonaRelationshipFacet();
      final result = await facet.getRelationshipCapability(
        GetRelationshipCapabilityQuery(
          targetSubAccountId: 'fixture_user_photo',
        ),
      );

      expect(result.relationState, 'mutual');
      expect(result.canSendMessage, isTrue);
      expect(result.canCreateDirectConversation, isTrue);
      expect(result.canStartVoiceCall, isTrue);
      expect(result.canGreet, isFalse);
    });

    test('未知对象返回可关注、可打招呼的 typed 能力位', () async {
      final facet = AlphaPersonaRelationshipFacet();
      final result = await facet.getRelationshipCapability(
        GetRelationshipCapabilityQuery(targetSubAccountId: 'fixture_user_new'),
      );

      expect(result.relationState, 'not_following');
      expect(result.canFollow, isTrue);
      expect(result.canGreet, isTrue);
      expect(result.canSendMessage, isFalse);
    });

    test('block command 后 query 关闭打招呼、会话与 RTC', () async {
      final facet = AlphaPersonaRelationshipFacet();
      await facet.blockUser(
        BlockUserCommand(targetSubAccountId: 'fixture_user_photo'),
      );
      final result = await facet.getRelationshipCapability(
        GetRelationshipCapabilityQuery(
          targetSubAccountId: 'fixture_user_photo',
        ),
      );

      expect(result.isBlocked, isTrue);
      expect(result.canGreet, isFalse);
      expect(result.canOpenConversation, isFalse);
      expect(result.canStartVoiceCall, isFalse);
      expect(result.canStartVideoCall, isFalse);
    });
  });
}
