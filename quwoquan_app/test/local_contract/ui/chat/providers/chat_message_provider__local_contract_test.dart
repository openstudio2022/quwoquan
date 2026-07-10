import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/chat/models/send_message_response.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_message_provider.dart';

final RegExp _defaultNicknamePattern = RegExp(r'^新同学_\d{6}_\d{7}$');

void main() {
  group('ChatMessageNotifier', () {
    test('loadMessages fills missing sender snapshots from members', () async {
      final container = ProviderContainer(
        overrides: [
          chatRepositoryProvider.overrideWithValue(MockChatRepository()),
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
        contains(
          '/media/avatar/s/archived-avatar/user/fixture_user_friend/v1/avatar.png',
        ),
      );
      expect(selfMessage.senderName, matches(_defaultNicknamePattern));
      expect(
        selfMessage.senderAvatar,
        contains(
          '/media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png',
        ),
      );
    });

    test('sendMessage forwards rich media payloads', () async {
      final repo = _TrackingSendChatRepository();
      final container = ProviderContainer(
        overrides: [
          chatRepositoryProvider.overrideWithValue(repo),
          contentRepositoryProvider.overrideWithValue(MockContentRepository()),
          activePersonaContextProvider.overrideWith(
            (ref) async => ActivePersonaContextViewData.fallback(
              subAccountId: 'persona_media_test',
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
        mediaUrl: 'https://cdn.example.com/photo.jpg',
        media: <String, dynamic>{
          'url': 'https://cdn.example.com/photo.jpg',
          'thumbnailUrl': 'https://cdn.example.com/thumb.jpg',
          'mimeType': 'image/jpeg',
          'fileSizeBytes': 1024,
        },
      );

      expect(sent, isTrue);
      expect(repo.lastType, 'image');
      expect(repo.lastContent, '');
      expect(repo.lastMediaUrl, 'https://cdn.example.com/photo.jpg');
      expect(
        repo.lastMedia?['thumbnailUrl'],
        'https://cdn.example.com/thumb.jpg',
      );

      final state = container.read(chatMessageProvider('fixture_conv_media'));
      expect(state.messages, hasLength(1));
      final message = state.messages.single;
      expect(message.type, 'image');
      expect(message.content, '');
      expect(message.mediaUrl, 'https://cdn.example.com/photo.jpg');
      expect(
        message.media?['thumbnailUrl'],
        'https://cdn.example.com/thumb.jpg',
      );
      expect(message.status, 'sent');
    });

    test('sendMessage forwards assistant mentions', () async {
      final repo = _TrackingSendChatRepository();
      final container = ProviderContainer(
        overrides: [
          chatRepositoryProvider.overrideWithValue(repo),
          contentRepositoryProvider.overrideWithValue(MockContentRepository()),
          activePersonaContextProvider.overrideWith(
            (ref) async => ActivePersonaContextViewData.fallback(
              subAccountId: 'persona_mention_test',
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
      expect(repo.lastMentions, contains('assistant'));
    });
  });
}

class _TrackingSendChatRepository extends MockChatRepository {
  String? lastType;
  String? lastContent;
  String? lastMediaUrl;
  Map<String, dynamic>? lastMedia;
  List<String>? lastMentions;

  @override
  Future<SendMessageResponse> sendMessage({
    required String conversationId,
    required String type,
    required String content,
    String? mediaUrl,
    Map<String, dynamic>? media,
    Map<String, dynamic>? cardPayload,
    String? replyToMessageId,
    List<String>? mentions,
    String? senderSubAccountId,
    String? personaContextVersion,
    String? senderDisplayNameSnapshot,
    String? senderAvatarUrlSnapshot,
    required String clientMsgId,
  }) async {
    lastType = type;
    lastContent = content;
    lastMediaUrl = mediaUrl;
    lastMedia = media;
    lastMentions = mentions;
    return super.sendMessage(
      conversationId: conversationId,
      type: type,
      content: content,
      mediaUrl: mediaUrl,
      media: media,
      cardPayload: cardPayload,
      replyToMessageId: replyToMessageId,
      mentions: mentions,
      senderSubAccountId: senderSubAccountId,
      personaContextVersion: personaContextVersion,
      senderDisplayNameSnapshot: senderDisplayNameSnapshot,
      senderAvatarUrlSnapshot: senderAvatarUrlSnapshot,
      clientMsgId: clientMsgId,
    );
  }
}
