import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/chat/models/message_dto.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_contact_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_inbox_dto.g.dart';
import 'package:quwoquan_app/core/media/avatar_image_url.dart';
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
          avatarUrl: '/media/avatar/s/archived-avatar/conversation/conv_1/v2/hash.png?v=2',
        ),
      );

      expect(
        item.avatarUrl,
        resolveAvatarImageUrlCandidates(
          '/media/avatar/s/archived-avatar/conversation/conv_1/v2/hash.png?v=2',
          gatewayBaseUrl: CloudRuntimeConfig.gatewayBaseUrl,
          avatarCdnBaseUrl: CloudRuntimeConfig.mediaAvatarCdnBaseUrl,
        ).first,
      );
    });

    test('contact rows expose loadable user avatar URLs', () {
      final row = ChatContactsRow.fromContactDto(
        ChatContactRowDto(
          userId: 'user_2',
          displayName: '契约联系人',
          avatarUrl: 'media/avatar/s/archived-avatar/user/user_2/v1/profile.png',
          relationState: 'mutual',
        ),
      );

      expect(
        row.avatarUrl,
        resolveAvatarImageUrlCandidates(
          'media/avatar/s/archived-avatar/user/user_2/v1/profile.png',
          gatewayBaseUrl: CloudRuntimeConfig.gatewayBaseUrl,
          avatarCdnBaseUrl: CloudRuntimeConfig.mediaAvatarCdnBaseUrl,
        ).first,
      );
    });

    test('message display maps expose loadable sender avatars', () {
      final item = ChatMessageDto(
        id: 'msg_1',
        conversationId: 'conv_1',
        senderId: 'user_2',
        senderName: '契约联系人',
        senderAvatar: '/media/avatar/s/archived-avatar/user/user_2/v3/profile.png?v=3',
        content: '你好',
      ).toDisplayItem(currentUserId: 'user_me');

      expect(
        item.senderAvatar,
        resolveAvatarImageUrlCandidates(
          '/media/avatar/s/archived-avatar/user/user_2/v3/profile.png?v=3',
          gatewayBaseUrl: CloudRuntimeConfig.gatewayBaseUrl,
          avatarCdnBaseUrl: CloudRuntimeConfig.mediaAvatarCdnBaseUrl,
        ).first,
      );
    });

    test('image message display maps media url to preview image', () {
      final item = ChatMessageDto(
        id: 'msg_img',
        conversationId: 'conv_1',
        senderId: 'user_2',
        type: 'image',
        media: <String, dynamic>{
          'url': 'https://cdn.example.com/photo.jpg',
          'thumbnailUrl': 'https://cdn.example.com/thumb.jpg',
        },
      ).toDisplayItem(currentUserId: 'user_me');

      expect(item.type, 'image');
      expect(item.imageUrl, 'https://cdn.example.com/photo.jpg');
      expect(item.thumbnailUrl, 'https://cdn.example.com/thumb.jpg');
    });

    test('image message display falls back to image url when thumbnail missing', () {
      final item = ChatMessageDto(
        id: 'msg_img_fallback',
        conversationId: 'conv_1',
        senderId: 'user_2',
        type: 'image',
        media: <String, dynamic>{
          'url': 'https://cdn.example.com/photo2.jpg',
        },
      ).toDisplayItem(currentUserId: 'user_me');

      expect(item.imageUrl, 'https://cdn.example.com/photo2.jpg');
      expect(item.thumbnailUrl, 'https://cdn.example.com/photo2.jpg');
    });
  });
}
