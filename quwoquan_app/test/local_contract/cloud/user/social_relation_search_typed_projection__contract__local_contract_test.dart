import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/social_relation_search_item_wire_dto.g.dart';
import 'package:quwoquan_app/core/models/search_models.dart';

void main() {
  test('社交搜索结果只消费嵌套强类型 capability', () {
    final wire = SocialRelationSearchItemWireDto.fromMap(<String, Object?>{
      'personaId': 'persona-target',
      'userHandle': 'target',
      'displayName': '目标用户',
      'chatAvailable': false,
      'relationshipCapability': <String, Object?>{
        'viewerPersonaId': 'persona-viewer',
        'targetPersonaId': 'persona-target',
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
      },
      // 整行同名字段不再作为 capability 回退来源。
      'relationState': 'not_following',
      'canOpenConversation': false,
    });

    final view = SocialRelationSearchItemView.fromSocialRelationSearchItemWire(
      wire,
    );

    expect(view.relationshipCapability.relationState, 'mutual');
    expect(view.relationshipCapability.canOpenConversation, isTrue);
    expect(view.chatAvailable, isTrue);
    expect(view.userHandle, 'target');
  });

  test('缺少嵌套 capability 时失败关闭，不读取整行动态字段', () {
    expect(
      () => SocialRelationSearchItemView.fromSocialRelationSearchItemWire(
        SocialRelationSearchItemWireDto.fromMap(<String, Object?>{
          'personaId': 'persona-target',
          'displayName': '目标用户',
          'chatAvailable': true,
          'relationState': 'mutual',
          'canOpenConversation': true,
        }),
      ),
      throwsFormatException,
    );
  });
}
