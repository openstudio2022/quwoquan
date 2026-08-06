import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/chat_contracts.dart';

import '../../../../../support/service/chat_service/chat/conversation/chat_repository_typed_double.dart';
import '../../../../../support/service/chat_service/chat/conversation/conversation_state_typed_double.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_message_command_writer_typed_double.dart';

void main() {
  group('chat mock remote parity contract', () {
    test(
      'MockChatRepository contact rows only use media/avatar object keys',
      () async {
        final repo = MockChatRepository();
        final contacts = await repo.listContacts(limit: 100);
        expect(contacts.items, isNotEmpty);
        for (final contact in contacts.items) {
          expect(
            contact.avatarUrl.toLowerCase().startsWith('media/avatar/'),
            isTrue,
            reason: '${contact.userId} avatar=${contact.avatarUrl}',
          );
        }
      },
    );

    test(
      'listContactHome all includes user rows with contract avatars',
      () async {
        final repo = MockChatRepository();
        final rows = await repo.listContactHome(filter: 'all', limit: 500);
        expect(rows.where((row) => row.kind == 'user'), isNotEmpty);
        for (final row in rows) {
          if (row.avatarUrl.trim().isEmpty) {
            continue;
          }
          expect(
            row.avatarUrl.toLowerCase().startsWith('media/avatar/'),
            isTrue,
            reason: '${row.id} avatar=${row.avatarUrl}',
          );
        }
      },
    );

    test(
      'listMessageHome notification filter matches cloud empty contract',
      () async {
        final repo = MockChatRepository();
        final rows = await repo.listMessageHome(
          filter: 'notification',
          limit: 50,
        );
        expect(rows, isEmpty);
      },
    );

    test('repository 与发送命令共享同一个 pure state engine', () async {
      final engine = InMemoryChatStateEngine();
      final repo = MockChatRepository(engine: engine);
      final writer = InMemoryChatMessageCommandWriter(engine: engine);
      final before = await repo.listMessages(
        conversationId: 'fixture_conv_direct',
        limit: 500,
      );

      final result = await writer.sendMessage(
        ChatSendMessageCommand(
          conversationId: 'fixture_conv_direct',
          type: 'text',
          content: '共享状态消息',
          clientMsgId: 'shared-engine-message-1',
        ),
      );
      final replay = await writer.sendMessage(
        ChatSendMessageCommand(
          conversationId: 'fixture_conv_direct',
          type: 'text',
          content: '共享状态消息',
          clientMsgId: 'shared-engine-message-1',
        ),
      );
      final after = await repo.listMessages(
        conversationId: 'fixture_conv_direct',
        limit: 500,
      );
      final inbox = await repo.listInbox(limit: 500);

      expect(replay.messageId, result.messageId);
      expect(after.length, before.length + 1);
      expect(after.last.id, result.messageId);
      expect(
        inbox
            .firstWhere((item) => item.id == 'fixture_conv_direct')
            .lastMessagePreview,
        '共享状态消息',
      );
    });
  });
}
