import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/chat/models/message_dto.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_view_data.dart';
import 'package:quwoquan_app/core/media/avatar_image_url.dart';
import 'package:quwoquan_app/core/media/media_delivery_reference.dart';
import 'package:quwoquan_app/ui/chat/models/chat_contacts_row.dart';
import 'package:quwoquan_app/ui/chat/models/chat_list_item_view_model.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../support/fixtures/chat/chat_inbox_fixture_builder.dart';

void main() {
  final mediaEndpointConfig = MediaEndpointConfig(
    avatarBaseUrl: 'https://media.example.com',
    imageBaseUrl: 'https://media.example.com',
    videoBaseUrl: 'https://video.example.com',
    attachmentBaseUrl: 'https://media.example.com',
  );

  group('chat avatar URL resolution', () {
    test('conversation list items expose loadable avatar URLs', () {
      final item = ChatListItemViewModel.fromDto(
        chatInboxFixture(
          id: 'conv_1',
          type: 'group',
          title: '契约群',
          avatarUrl:
              '/media/avatar/s/archived-avatar/conversation/conv_1/v1/hash.png',
        ),
        mediaEndpointConfig: mediaEndpointConfig,
      );

      expect(
        item.avatarUrl,
        resolveAvatarImageUrlCandidates(
          '/media/avatar/s/archived-avatar/conversation/conv_1/v1/hash.png',
          endpointConfig: mediaEndpointConfig,
        ).first,
      );
    });

    test('contact rows expose loadable user avatar URLs', () {
      final row = ChatContactsRow.fromContactDto(
        ChatContactRowViewData(
          userId: 'user_2',
          userHandle: 'user_2',
          displayName: '契约联系人',
          avatarUrl:
              'media/avatar/s/archived-avatar/user/user_2/v1/profile.png',
          relationState: 'mutual',
        ),
        mediaEndpointConfig: mediaEndpointConfig,
      );

      expect(
        row.avatarUrl,
        resolveAvatarImageUrlCandidates(
          'media/avatar/s/archived-avatar/user/user_2/v1/profile.png',
          endpointConfig: mediaEndpointConfig,
        ).first,
      );
    });

    test('message display maps expose loadable sender avatars', () {
      final item =
          ChatMessageViewData(
            id: 'msg_1',
            conversationId: 'conv_1',
            seq: 1,
            clientMsgId: 'client_msg_1',
            senderId: 'user_2',
            senderName: '契约联系人',
            senderAvatar:
                '/media/avatar/s/archived-avatar/user/user_2/v1/profile.png',
            type: 'text',
            content: '你好',
            status: 'sent',
          ).toDisplayItem(
            currentUserId: 'user_me',
            mediaEndpointConfig: mediaEndpointConfig,
          );

      expect(
        item.senderAvatar,
        resolveAvatarImageUrlCandidates(
          '/media/avatar/s/archived-avatar/user/user_2/v1/profile.png',
          endpointConfig: mediaEndpointConfig,
        ).first,
      );
    });

    test('image message display maps media url to preview image', () {
      final item = ChatMessageViewData(
        id: 'msg_img',
        conversationId: 'conv_1',
        seq: 2,
        clientMsgId: 'client_msg_img',
        senderId: 'user_2',
        type: 'image',
        mediaAssetId: 'asset_img',
        mediaDeliveryUrl: 'https://cdn.example.com/photo.jpg',
        mediaType: 'image',
        mediaContentType: 'image/jpeg',
        status: 'sent',
      ).toDisplayItem(currentUserId: 'user_me');

      expect(item.type, 'image');
      expect(item.imageUrl, 'https://cdn.example.com/photo.jpg');
      expect(item.thumbnailUrl, 'https://cdn.example.com/photo.jpg');
    });

    test(
      'image message display falls back to image url when thumbnail missing',
      () {
        final item = ChatMessageViewData(
          id: 'msg_img_fallback',
          conversationId: 'conv_1',
          seq: 3,
          clientMsgId: 'client_msg_img_fallback',
          senderId: 'user_2',
          type: 'image',
          mediaAssetId: 'asset_img_fallback',
          mediaDeliveryUrl: 'https://cdn.example.com/photo2.jpg',
          mediaType: 'image',
          mediaContentType: 'image/jpeg',
          status: 'sent',
        ).toDisplayItem(currentUserId: 'user_me');

        expect(item.imageUrl, 'https://cdn.example.com/photo2.jpg');
        expect(item.thumbnailUrl, 'https://cdn.example.com/photo2.jpg');
      },
    );
  });

  group('chat canonical MessageType preview rendering', () {
    const expectedFallback = <MessageType, String>{
      MessageType.text: '',
      MessageType.image: '[图片]',
      MessageType.video: '[视频]',
      MessageType.audio: '[语音]',
      MessageType.file: '[文件]',
      MessageType.card: '[卡片]',
      MessageType.systemCallLog: '[通话]',
      MessageType.systemAnnouncement: '群公告',
    };

    for (final entry in expectedFallback.entries) {
      test('${entry.key.wireName} uses the canonical list preview', () {
        final item = ChatListItemViewModel.fromDto(
          chatInboxFixture(
            id: 'conv_${entry.key.wireName}',
            type: 'group',
            title: '类型渲染',
            lastMessageType: entry.key,
          ),
        );
        expect(item.subtitle, entry.value);
      });
    }
  });
}
