import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/chat/models/message_dto.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import '../../../support/cloud_services/chat_repository_mock.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_message_handler.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_message_provider.dart';

void main() {
  testWidgets('MessageSent 只接受 canonical event 并生成 typed card', (tester) async {
    late ProviderContainer container;
    await tester.pumpWidget(
      ProviderScope(
        child: Consumer(
          builder: (context, ref, _) {
            container = ProviderScope.containerOf(context);
            return const MaterialApp(home: SizedBox());
          },
        ),
      ),
    );
    await tester.pump();

    RealtimeMessageHandler(container.read).handle(<String, dynamic>{
      'type': 'MessageSent',
      'conversationId': 'conv_card',
      'payload': <String, dynamic>{
        'messageId': 'msg_card',
        'conversationId': 'conv_card',
        'seq': 8,
        'clientMsgId': 'client_card',
        'senderId': 'persona_sender',
        'type': 'card',
        'content': '查看分享',
        'card': <String, dynamic>{
          'kind': 'content_post',
          'title': '城市漫步',
          'attributes': <Map<String, String>>[
            <String, String>{'name': 'postId', 'value': 'post_001'},
          ],
        },
        'personaContextVersion': 2,
        'timestamp': '2026-07-15T08:00:00Z',
      },
    });
    await tester.pump();

    final messages = container.read(chatMessageProvider('conv_card')).messages;
    final message = messages.singleWhere((item) => item.id == 'msg_card');
    expect(message.card?.kind, 'content_post');
    expect(message.card?.attributes.single.value, 'post_001');
  });

  testWidgets('已移除字段 event 与 media event 均通过 Reader 恢复而非动态解码', (tester) async {
    final repository = _CountingMessageRepository();
    late ProviderContainer container;
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          chatRepositoryCompositionProvider.overrideWithValue(repository),
        ],
        child: Consumer(
          builder: (context, ref, _) {
            container = ProviderScope.containerOf(context);
            return const MaterialApp(home: SizedBox());
          },
        ),
      ),
    );
    await tester.pump();
    final handler = RealtimeMessageHandler(container.read);

    handler.handle(<String, dynamic>{
      'type': 'MessageSent',
      'conversationId': 'conv_recovery',
      'payload': <String, dynamic>{
        'messageId': 'removed_msg',
        'conversationId': 'conv_recovery',
        'seq': 9,
        'clientMsgId': 'removed_client',
        'senderId': 'persona_sender',
        'senderSubAccountId': 'removed_alias',
        'type': 'text',
        'content': 'removed',
        'timestamp': '2026-07-15T08:00:01Z',
      },
    });
    await tester.pump();
    expect(repository.listMessagesCallCount, 1);
    expect(
      container
          .read(chatMessageProvider('conv_recovery'))
          .messages
          .any((item) => item.id == 'removed_msg'),
      isFalse,
    );

    handler.handle(<String, dynamic>{
      'type': 'MessageSent',
      'conversationId': 'conv_recovery',
      'payload': <String, dynamic>{
        'messageId': 'media_msg',
        'conversationId': 'conv_recovery',
        'seq': 10,
        'clientMsgId': 'media_client',
        'senderId': 'persona_sender',
        'type': 'image',
        'content': '',
        'mediaAssetId': 'asset_image',
        'timestamp': '2026-07-15T08:00:02Z',
      },
    });
    await tester.pump();
    expect(repository.listMessagesCallCount, 2);
    expect(
      container
          .read(chatMessageProvider('conv_recovery'))
          .messages
          .any((item) => item.id == 'media_msg'),
      isFalse,
    );
  });
}

class _CountingMessageRepository extends MockChatRepository {
  int listMessagesCallCount = 0;

  @override
  Future<List<ChatMessageDto>> listMessages({
    required String conversationId,
    String? before,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    listMessagesCallCount += 1;
    return const <ChatMessageDto>[];
  }
}
