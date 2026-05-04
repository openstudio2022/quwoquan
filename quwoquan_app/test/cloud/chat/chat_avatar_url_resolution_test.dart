import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/chat/models/message_dto.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_contact_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_inbox_dto.g.dart';
import 'package:quwoquan_app/ui/chat/models/chat_contacts_row.dart';
import 'package:quwoquan_app/ui/chat/models/chat_list_item_view_model.dart';

void main() {
  group('chat avatar URL resolution', () {
    test('conversation list items expose loadable avatar URLs', () {
      final item = ChatListItemViewModel.fromDto(
        ChatInboxDto(
          id: 'conv_1',
          type: 'group',
          title: '契约群',
          avatarUrl: '/media/avatar/conversation/conv_1/v2/hash.png?v=2',
        ),
      );

      expect(
        item.avatarUrl,
        'http://127.0.0.1:18080/media/avatar/conversation/conv_1/v2/hash.png?v=2',
      );
    });

    test('contact rows expose loadable user avatar URLs', () {
      final row = ChatContactsRow.fromContactDto(
        ChatContactRowDto(
          userId: 'user_2',
          displayName: '契约同好',
          avatarUrl: 'media/avatar/user/user_2/v1/profile.png',
          isFriend: true,
        ),
      );

      expect(
        row.avatarUrl,
        'http://127.0.0.1:18080/media/avatar/user/user_2/v1/profile.png',
      );
    });

    test('message display maps expose loadable sender avatars', () {
      final map = ChatMessageDto(
        id: 'msg_1',
        conversationId: 'conv_1',
        senderId: 'user_2',
        senderName: '契约同好',
        senderAvatar: '/media/avatar/user/user_2/v3/profile.png?v=3',
        content: '你好',
      ).toDisplayMap(currentUserId: 'user_me');

      expect(
        map['senderAvatar'],
        'http://127.0.0.1:18080/media/avatar/user/user_2/v3/profile.png?v=3',
      );
    });
  });
}
