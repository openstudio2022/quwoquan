import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/persona_query.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/chat_message_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_media_view_data.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_view_data.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/chat_message_provider.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../../support/service/content_service/content/post/content_facet_overrides.dart';
import '../../../../../support/service/content_service/content/post/content_post_typed_doubles.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facet_overrides.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facets_typed_double.dart';
import '../../../../../support/runtime/platform/storage/sqflite_ffi_test_support.dart';

final RegExp _defaultNicknamePattern = RegExp(r'^新同学_\d{6}_\d{7}$');

final class _ChatPersonaQuery extends Fake implements PersonaQuery {
  @override
  Future<ActivePersonaContextViewData> getActivePersonaContext() async {
    return ActivePersonaContextViewData(
      personaId: 'fixture_user_current',
      ownerUserId: 'fixture_user_current',
      subjectType: 'persona',
      displayName: '消息测试用户',
      avatarUrl: '',
      contextVersion: 1,
    );
  }
}

void main() {
  // ChatMessageNotifier 读写本地会话时间线（sqflite），VM 测试需要 ffi 后端。
  setUpAll(ensureSqfliteFfiInitialized);

  group('ChatMessageNotifier', () {
    test('loadMessages fills missing sender snapshots from members', () async {
      final mediaEndpoints = MediaEndpointConfig(
        avatarBaseUrl: 'https://avatar.example.test/media/avatar',
        imageBaseUrl: 'https://image.example.test/media/image',
        videoBaseUrl: 'https://video.example.test/media/video',
        attachmentBaseUrl: 'https://image.example.test/media/image',
      );
      final facets = ChatTestFacets();
      final container = ProviderContainer(
        overrides: [
          ...sealedCloudBoundaryOverrides(),
          ...chatTestRepositoryOverrides(facets: facets),
          personaQueryProvider(
            AppUiSurfaces.appShell,
          ).overrideWithValue(_ChatPersonaQuery()),
          mediaEndpointConfigProvider.overrideWithValue(mediaEndpoints),
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

      expect(friendMessage.senderName, '契约好友');
      expect(
        friendMessage.senderAvatar,
        'https://avatar.example.test/media/avatar/s/'
        'archived-avatar/user/fixture_user_friend/v1/avatar.png',
        reason: '统一 alpha 测试入口注入的 avatar CDN 必须解析相对头像引用',
      );
      expect(selfMessage.senderName, matches(_defaultNicknamePattern));
      expect(
        selfMessage.senderAvatar,
        'https://avatar.example.test/media/avatar/s/'
        'archived-avatar/user/fixture_user_current/v1/avatar.png',
        reason: '不得改用本地 gateway 或额外 URL 拼接回退',
      );
    });

    test('sendMessage forwards rich media payloads', () async {
      final writer = _TrackingMessageWriter();
      final container = ProviderContainer(
        overrides: [
          ...sealedCloudBoundaryOverrides(),
          chatMessageCommandWriterProvider.overrideWithValue(writer),
          ...mockContentFacetOverrides(store: InMemoryContentPostStore()),
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
          mimeType: 'image/jpeg',
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
          ...sealedCloudBoundaryOverrides(),
          chatMessageCommandWriterProvider.overrideWithValue(writer),
          ...mockContentFacetOverrides(store: InMemoryContentPostStore()),
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

    test(
      'markConversationRead ignores completion after provider disposal',
      () async {
        final facets = ChatTestFacets();
        final repository = _DelayedReadReceiptRepository(facets.message);
        final container = ProviderContainer(
          overrides: [
            ...sealedCloudBoundaryOverrides(),
            ...chatTestRepositoryOverrides(facets: facets, message: repository),
            personaQueryProvider(
              AppUiSurfaces.appShell,
            ).overrideWithValue(_ChatPersonaQuery()),
          ],
        );
        final notifier = container.read(
          chatMessageProvider('fixture_conv_direct').notifier,
        );
        await notifier.loadMessages();

        final pending = notifier.markConversationRead();
        await repository.started.future;
        container.dispose();
        repository.complete();

        expect(await pending, isFalse);
      },
    );
  });
}

class _DelayedReadReceiptRepository extends Fake
    implements ChatMessageRepository {
  _DelayedReadReceiptRepository(this._delegate);

  final ChatMessageRepository _delegate;
  final Completer<void> started = Completer<void>();
  final Completer<void> _completion = Completer<void>();

  @override
  Future<List<ChatMessageViewData>> listMessages({
    required String conversationId,
    String? before,
    int limit = 20,
  }) {
    return _delegate.listMessages(
      conversationId: conversationId,
      before: before,
      limit: limit,
    );
  }

  @override
  Future<void> markAsRead({
    required String conversationId,
    required String messageId,
  }) async {
    if (!started.isCompleted) {
      started.complete();
    }
    await _completion.future;
  }

  void complete() {
    if (!_completion.isCompleted) {
      _completion.complete();
    }
  }
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
