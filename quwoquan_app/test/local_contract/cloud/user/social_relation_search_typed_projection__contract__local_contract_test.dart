import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/social_relation_search_item_wire_dto.g.dart';
import 'package:quwoquan_app/core/models/search_models.dart';

void main() {
  test('社交搜索结果只消费嵌套强类型 capability', () {
    final wire = SocialRelationSearchItemWireDto.fromMap(<String, Object?>{
      'subAccountId': 'persona-target',
      'username': 'target',
      'displayName': '目标用户',
      'chatAvailable': false,
      'relationshipCapability': <String, Object?>{
        'relationState': 'mutual',
        'canFollow': false,
        'canUnfollow': true,
        'canOpenConversation': true,
        'canStartVoiceCall': true,
        'canStartVideoCall': true,
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
  });

  test('缺少嵌套 capability 时失败关闭，不读取整行动态字段', () {
    final wire = SocialRelationSearchItemWireDto.fromMap(<String, Object?>{
      'subAccountId': 'persona-target',
      'displayName': '目标用户',
      'chatAvailable': true,
      'relationState': 'mutual',
      'canOpenConversation': true,
    });

    final view = SocialRelationSearchItemView.fromSocialRelationSearchItemWire(
      wire,
    );

    expect(view.relationshipCapability.relationState, 'not_following');
    expect(view.relationshipCapability.canOpenConversation, isFalse);
    expect(view.chatAvailable, isFalse);
  });
}
