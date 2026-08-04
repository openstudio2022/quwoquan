import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/models/search_models.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    as contracts;

void main() {
  test('社交搜索结果只消费嵌套强类型 capability', () {
    const wire = contracts.SocialRelationSearchItemView(
      personaId: 'persona-target',
      userHandle: 'target',
      displayName: '目标用户',
      chatAvailable: false,
      relationshipCapability: contracts.RelationshipCapabilityView(
        viewerPersonaId: 'persona-viewer',
        targetPersonaId: 'persona-target',
        relationState: contracts.RelationshipState.mutual,
        canFollow: false,
        canUnfollow: true,
        canFollowBack: false,
        canGreet: false,
        canOpenConversation: true,
        canCreateDirectConversation: true,
        canSendMessage: true,
        hasPendingGreeting: false,
        hasFormalConversation: true,
        canStartVoiceCall: true,
        canStartVideoCall: true,
        isBlocked: false,
        isBlockedBy: false,
      ),
    );

    final view = SocialRelationSearchItemViewData.fromWire(wire);

    expect(view.relationshipCapability.relationState, 'mutual');
    expect(view.relationshipCapability.canOpenConversation, isTrue);
    expect(view.chatAvailable, isTrue);
    expect(view.userHandle, 'target');
  });

  test('缺少嵌套 capability 时 canonical decoder 失败关闭', () {
    expect(
      () => contracts.SocialRelationSearchItemView.fromWire(<String, Object?>{
        'personaId': 'persona-target',
        'userHandle': 'target',
        'displayName': '目标用户',
        'chatAvailable': true,
      }),
      throwsFormatException,
    );
  });
}
