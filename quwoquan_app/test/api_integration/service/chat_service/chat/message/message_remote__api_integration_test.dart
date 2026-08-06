// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/realtime-push-and-offline-sync/spec.md#gwt-002

import 'package:flutter_test/flutter_test.dart';

import '../../../../../support/runtime/api_contract/chat_api_contract_harness.dart';

void main() {
  late ChatApiContractHarness harness;
  late String conversationId;

  setUpAll(() async {
    harness = await ChatApiContractHarness.create();
    conversationId = await harness.seedConversation();
  });
  tearDownAll(() => harness.close());

  test('generated client 发送消息返回 seq 与 messageId', () async {
    final stopwatch = Stopwatch()..start();
    final result = await harness.sendMessage(conversationId, 'l3-send-001');
    stopwatch.stop();

    expect(stopwatch.elapsedMilliseconds, lessThan(500));
    expect(result.messageId, isNotEmpty);
    expect(result.seq, greaterThan(0));
    expect(result.timestamp, isNotNull);
  });

  test('相同 clientMsgId 幂等返回同一消息', () async {
    final first = await harness.sendMessage(conversationId, 'l3-dedup-001');
    final replay = await harness.sendMessage(conversationId, 'l3-dedup-001');

    expect(replay.messageId, first.messageId);
    expect(replay.seq, first.seq);
  });

  test('production Remote 可撤回消息', () async {
    final message = await harness.sendMessage(conversationId, 'l3-recall-001');
    await harness.repository.recallMessage(
      conversationId: conversationId,
      messageId: message.messageId,
    );

    final messages = await harness.repository.listMessages(
      conversationId: conversationId,
      limit: 20,
    );
    expect(
      messages
          .where((candidate) => candidate.id == message.messageId)
          .single
          .status,
      'recalled',
    );
  });

  test('production Remote 消息列表保留 canonical typed fields', () async {
    await harness.sendMessage(conversationId, 'l3-list-001');
    final messages = await harness.repository.listMessages(
      conversationId: conversationId,
      limit: 10,
    );

    expect(messages, isNotEmpty);
    expect(messages.first.id, isNotEmpty);
    expect(messages.first.type, isNotEmpty);
    expect(messages.first.seq, greaterThan(0));
  });

  test('production Remote sync 返回增量消息', () async {
    for (var index = 0; index < 5; index += 1) {
      await harness.sendMessage(conversationId, 'l3-sync-seed-$index');
    }
    final stopwatch = Stopwatch()..start();
    final result = await harness.repository.syncMessages(
      conversationId: conversationId,
      lastSeq: 0,
      limit: 100,
    );
    stopwatch.stop();

    expect(stopwatch.elapsedMilliseconds, lessThan(800));
    expect(result.messages.length, greaterThanOrEqualTo(5));
  });
}
