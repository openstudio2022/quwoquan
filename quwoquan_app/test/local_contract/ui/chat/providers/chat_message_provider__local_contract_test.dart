import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import '../../../../support/cloud_services/chat_repository_mock.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/chat/models/chat_message_media_view_data.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_message_provider.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../support/cloud_services/content_facet_overrides.dart';
import '../../../../support/cloud_services/content/mock_content_repository.dart';

final RegExp _defaultNicknamePattern = RegExp(r'^新同学_\d{6}_\d{7}$');

void main() {
  group('ChatMessageNotifier', () {
    test('loadMessages fills missing sender snapshots from members', () async {
      final container = ProviderContainer(
        overrides: [
          chatRepositoryCompositionProvider.overrideWithValue(
            MockChatRepository(),
          ),
        ],
      );
      addTearDown(container.dispose);

      final notifier = container.read(
        chatMessageProvider('fixture_conv_direct').notifier,
      );
      await notifier.loadMessages();

      final state = container.read(chatMessageProvider('fixture_conv_direct'));
      final friendMessage = state.messages.firstWhere(
        (message) => message.senderId == 'fixture_user_friend',
      );
      final selfMessage = state.messages.firstWhere(
        (message) => message.senderId == 'fixture_user_current',
      );

      expect(friendMessage.senderName, '契约联系人');
      expect(
        friendMessage.senderAvatar,
        '${CloudRuntimeConfig.mediaAvatarCdnBaseUrl}/s/'
        'archived-avatar/user/fixture_user_friend/v1/avatar.png',
        reason: '统一 alpha 测试入口注入的 avatar CDN 必须解析相对头像引用',
      );
      expect(selfMessage.senderName, matches(_defaultNicknamePattern));
      expect(
        selfMessage.senderAvatar,
        '${CloudRuntimeConfig.mediaAvatarCdnBaseUrl}/s/'
        'archived-avatar/user/fixture_user_current/v1/avatar.png',
        reason: '不得改用本地 gateway 或额外 URL 拼接回退',
      );
    });

    test('sendMessage forwards rich media payloads', () async {
      final writer = _TrackingMessageWriter();
      final container = ProviderContainer(
        overrides: [
          chatRepositoryCompositionProvider.overrideWithValue(
            MockChatRepository(),
          ),
          chatMessageCommandWriterProvider.overrideWithValue(writer),
          ...mockContentFacetOverrides(MockContentRepository()),
          activePersonaContextProvider.overrideWith(
            (ref) async => ActivePersonaContextViewData.fallback(
              personaId: 'persona_media_test',
              ownerUserId: 'user_media_test',
              displayName: '富媒体测试分身',
              avatarUrl: '',
            ),
          ),
        ],
      );
      addTearDown(container.dispose);

      final notifier = container.read(
        chatMessageProvider('fixture_conv_media').notifier,
      );
      final sent = await notifier.sendMessage(
        'image',
        '',
        media: ChatMessageMediaViewData(
          assetId: 'asset_photo_001',
          deliveryUrl: 'https://cdn.example.com/photo.jpg',
          mediaType: 'image',
          contentType: 'image/jpeg',
          thumbnailUrl: 'https://cdn.example.com/thumb.jpg',
          fileSizeBytes: 1024,
        ),
      );

      expect(sent, isTrue);
      expect(writer.lastCommand?.type, 'image');
      expect(writer.lastCommand?.content, '');
      expect(writer.lastCommand?.mediaAssetId, 'asset_photo_001');

      final state = container.read(chatMessageProvider('fixture_conv_media'));
      expect(state.messages, hasLength(1));
      final message = state.messages.single;
      expect(message.type, 'image');
      expect(message.content, '');
      expect(message.mediaDeliveryUrl, 'https://cdn.example.com/photo.jpg');
      expect(message.mediaAssetId, 'asset_photo_001');
      expect(message.mediaType, 'image');
      expect(message.mediaContentType, 'image/jpeg');
      expect(message.mediaFileSizeBytes, 1024);
      expect(message.status, 'sent');
    });

    test('sendMessage forwards assistant mentions', () async {
      final writer = _TrackingMessageWriter();
      final container = ProviderContainer(
        overrides: [
          chatRepositoryCompositionProvider.overrideWithValue(
            MockChatRepository(),
          ),
          chatMessageCommandWriterProvider.overrideWithValue(writer),
          ...mockContentFacetOverrides(MockContentRepository()),
          activePersonaContextProvider.overrideWith(
            (ref) async => ActivePersonaContextViewData.fallback(
              personaId: 'persona_mention_test',
              ownerUserId: 'user_mention_test',
              displayName: '群聊测试分身',
              avatarUrl: '',
            ),
          ),
        ],
      );
      addTearDown(container.dispose);

      final notifier = container.read(
        chatMessageProvider('fixture_conv_group').notifier,
      );
      final sent = await notifier.sendMessage(
        'text',
        '@小趣 总结一下',
        mentions: const <String>['assistant'],
      );

      expect(sent, isTrue);
      expect(writer.lastCommand?.mentions, contains('assistant'));
    });
  });
}

class _TrackingMessageWriter implements ChatMessageCommandWriter {
  ChatSendMessageCommand? lastCommand;

  @override
  Future<ChatSendMessageResult> sendMessage(
    ChatSendMessageCommand command,
  ) async {
    lastCommand = command;
    return ChatSendMessageResult(
      messageId: 'message_${command.clientMsgId}',
      seq: 1,
      timestamp: DateTime.utc(2026, 6, 6),
    );
  }
}
