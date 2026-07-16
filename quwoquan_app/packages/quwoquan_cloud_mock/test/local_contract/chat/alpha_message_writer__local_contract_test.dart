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
}
