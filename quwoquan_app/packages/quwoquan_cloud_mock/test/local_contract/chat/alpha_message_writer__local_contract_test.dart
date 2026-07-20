import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock.dart';
import 'package:test/test.dart';

void main() {
  test('alpha Message writer replays the same command receipt', () async {
    final writer = AlphaChatMessageCommandWriter();
    final command = ChatSendMessageCommand(
      conversationId: 'fixture_conv_direct',
      type: 'text',
      content: 'alpha typed message',
      clientMsgId: 'alpha-message-1',
    );

    final first = await writer.sendMessage(command);
    final replay = await writer.sendMessage(command);

    expect(replay.messageId, first.messageId);
    expect(replay.seq, first.seq);
    expect(replay.timestamp, first.timestamp);
  });

  test('alpha Message writer rejects conflicting idempotency reuse', () async {
    final writer = AlphaChatMessageCommandWriter();
    await writer.sendMessage(
      ChatSendMessageCommand(
        conversationId: 'fixture_conv_direct',
        type: 'text',
        content: 'first payload',
        clientMsgId: 'alpha-conflict-1',
      ),
    );

    expect(
      () => writer.sendMessage(
        ChatSendMessageCommand(
          conversationId: 'fixture_conv_direct',
          type: 'text',
          content: 'different payload',
          clientMsgId: 'alpha-conflict-1',
        ),
      ),
      throwsA(
        isA<StateError>().having(
          (error) => error.message,
          'message',
          'CHAT.USER.message_idempotency_conflict',
        ),
      ),
    );
  });

  test('alpha Message writer validates and canonicalizes group mentions', () {
    final engine = AlphaChatStateEngine();
    final target = engine
        .membersFor('fixture_conv_group')
        .firstWhere(
          (member) => member['userId'] != engine.currentUserId,
        )['userId']
        .toString();

    engine.sendMessage(
      ChatSendMessageCommand(
        conversationId: 'fixture_conv_group',
        type: 'text',
        content: '@成员 你好',
        clientMsgId: 'alpha-mention-valid',
        mentions: <String>[target, target],
      ),
    );
    final stored = engine
        .listMessages(conversationId: 'fixture_conv_group', limit: 50)
        .firstWhere(
          (message) => message['clientMsgId'] == 'alpha-mention-valid',
        );
    expect(stored['mentions'], <String>[target]);

    expect(
      () => engine.sendMessage(
        ChatSendMessageCommand(
          conversationId: 'fixture_conv_group',
          type: 'text',
          content: '@外部',
          clientMsgId: 'alpha-mention-outsider',
          mentions: const <String>['user_outsider'],
        ),
      ),
      throwsA(
        isA<StateError>().having(
          (error) => error.message,
          'message',
          'CHAT.USER.message_invalid',
        ),
      ),
    );
  });

  test('alpha ordinary member cannot use mention-all', () {
    final baseline = AlphaChatStateEngine();
    final currentUserId = baseline.currentUserId;
    final engine = AlphaChatStateEngine(
      seedMembers: <String, List<Map<String, Object?>>>{
        'fixture_conv_group': <Map<String, Object?>>[
          <String, Object?>{
            'id': 'membership_current',
            'conversationId': 'fixture_conv_group',
            'userId': currentUserId,
            'displayName': '当前成员',
            'role': 'member',
            'memberType': 'user',
          },
        ],
      },
    );

    expect(
      () => engine.sendMessage(
        ChatSendMessageCommand(
          conversationId: 'fixture_conv_group',
          type: 'text',
          content: '@所有人',
          clientMsgId: 'alpha-mention-all-member',
          mentions: const <String>['__all__'],
        ),
      ),
      throwsA(
        isA<StateError>().having(
          (error) => error.message,
          'message',
          'CHAT.USER.message_invalid',
        ),
      ),
    );
  });

  test(
    'alpha assistant alias canonicalizes to the active assistant member id',
    () {
      final baseline = AlphaChatStateEngine();
      final engine = AlphaChatStateEngine(
        seedMembers: <String, List<Map<String, Object?>>>{
          'fixture_conv_group': <Map<String, Object?>>[
            <String, Object?>{
              'id': 'membership_owner',
              'conversationId': 'fixture_conv_group',
              'userId': baseline.currentUserId,
              'displayName': '群主',
              'role': 'owner',
              'memberType': 'user',
            },
            <String, Object?>{
              'id': 'membership_assistant',
              'conversationId': 'fixture_conv_group',
              'userId': 'assistant_member_actual',
              'displayName': '小趣',
              'role': 'member',
              'memberType': 'assistant',
            },
          ],
        },
      );

      engine.sendMessage(
        ChatSendMessageCommand(
          conversationId: 'fixture_conv_group',
          type: 'text',
          content: '@小趣',
          clientMsgId: 'alpha-mention-assistant',
          mentions: const <String>['assistant'],
        ),
      );
      final stored = engine
          .listMessages(conversationId: 'fixture_conv_group', limit: 50)
          .singleWhere(
            (message) => message['clientMsgId'] == 'alpha-mention-assistant',
          );
      expect(stored['mentions'], <String>['assistant_member_actual']);
    },
  );

  test('alpha partial read preserves later unread mention count', () {
    final baseline = AlphaChatStateEngine();
    final currentUserId = baseline.currentUserId;
    final engine = AlphaChatStateEngine(
      seedMessages: <String, List<Map<String, Object?>>>{
        'fixture_conv_group': <Map<String, Object?>>[
          <String, Object?>{
            'id': 'message_read_target',
            'conversationId': 'fixture_conv_group',
            'seq': 100001,
            'senderId': 'user_sender',
            'mentions': <String>[currentUserId],
          },
          <String, Object?>{
            'id': 'message_later_mention',
            'conversationId': 'fixture_conv_group',
            'seq': 100002,
            'senderId': 'user_sender',
            'mentions': const <String>['__all__'],
          },
          <String, Object?>{
            'id': 'message_later_self',
            'conversationId': 'fixture_conv_group',
            'seq': 100003,
            'senderId': currentUserId,
            'mentions': <String>[currentUserId],
          },
        ],
      },
    );

    engine.markAsRead(
      conversationId: 'fixture_conv_group',
      messageId: 'message_read_target',
    );
    final inbox = engine
        .listInbox(limit: 0)
        .singleWhere((item) => item['id'] == 'fixture_conv_group');
    expect(inbox['unreadCount'], 1);
    expect(inbox['mentionUnreadCount'], 1);
  });
}
