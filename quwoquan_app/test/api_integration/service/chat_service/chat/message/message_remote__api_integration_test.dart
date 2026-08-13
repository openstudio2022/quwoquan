// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/realtime-push-and-offline-sync/spec.md#gwt-002
// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/commercial-remote-only-message-system/spec.md#gwt-001
// readiness_case: message_send_message_app_api
// readiness_case: message_recall_message_app_api
// readiness_case: message_list_messages_app_api
// readiness_case: message_sync_messages_app_api

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/errors/generated/chat/chat_errors.g.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/chat_api_contract_harness.dart';

void main() {
  late ChatApiContractHarness harness;
  late String conversationId;
  var harnessReady = false;

  setUpAll(() async {
    harness = await ChatApiContractHarness.create();
    harnessReady = true;
    conversationId = await harness.seedConversation();
  });
  tearDownAll(() async {
    if (harnessReady) {
      await harness.close();
    }
  });

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

  test('canonical recall failure 不产生伪成功或改写既有消息', () async {
    final before = await harness.repository.listMessages(
      conversationId: conversationId,
      limit: 100,
    );

    await expectLater(
      harness.repository.recallMessage(
        conversationId: conversationId,
        messageId: 'missing-message-${DateTime.now().microsecondsSinceEpoch}',
      ),
      throwsA(
        isA<CloudException>()
            .having((error) => error.statusCode, 'statusCode', 404)
            .having(
              (error) => error.code,
              'code',
              ChatErrorCode.messageNotFound.code,
            ),
      ),
    );

    final after = await harness.repository.listMessages(
      conversationId: conversationId,
      limit: 100,
    );
    expect(
      after.map((message) => message.id).toList(growable: false),
      before.map((message) => message.id).toList(growable: false),
    );
  });

  test('双 Actor 发送确认、幂等重试与接收方收件投影同源收敛', () async {
    final receiver = await ChatApiContractHarness.create();
    try {
      final receiverPersonaId =
          receiver.session.activePersona?.personaId.trim() ?? '';
      expect(receiverPersonaId, isNotEmpty);
      final sharedConversationId = await harness.seedConversation(
        maxGroupSize: 50,
      );
      await harness.repository.addMembers(
        conversationId: sharedConversationId,
        userIds: <String>[receiverPersonaId],
      );

      final clientMsgId =
          'dual-actor-${DateTime.now().toUtc().microsecondsSinceEpoch}';
      final first = await harness.sendMessage(
        sharedConversationId,
        clientMsgId,
      );
      final retry = await harness.sendMessage(
        sharedConversationId,
        clientMsgId,
      );
      expect(retry.messageId, first.messageId);
      expect(retry.seq, first.seq);

      final received = await _waitForReceivedMessage(
        receiver,
        conversationId: sharedConversationId,
        messageId: first.messageId,
      );
      expect(received.clientMsgId, clientMsgId);
      expect(received.status, 'sent');
      expect(received.seq, first.seq);

      final inbox = await _waitForReceiverInbox(
        receiver,
        conversationId: sharedConversationId,
        minimumSeq: first.seq,
      );
      expect(inbox.lastMessagePreview, 'L3 contract test message');

      await receiver.userStateCommands.markMessageRead(
        ChatMarkConversationMessageReadCommand(
          conversationId: sharedConversationId,
          messageId: first.messageId,
        ),
        idempotencyKey: 'dual-actor-read-$clientMsgId',
      );
      final receipt = await _waitForReadReceipt(
        receiver,
        conversationId: sharedConversationId,
        messageId: first.messageId,
        readerPersonaId: receiverPersonaId,
      );
      expect(receipt.readAt.isUtc, isTrue);
    } finally {
      await receiver.close();
    }
  });
}

Future<ChatMessageViewData> _waitForReceivedMessage(
  ChatApiContractHarness receiver, {
  required String conversationId,
  required String messageId,
}) async {
  final deadline = DateTime.now().add(const Duration(seconds: 20));
  while (DateTime.now().isBefore(deadline)) {
    final messages = await receiver.repository.listMessages(
      conversationId: conversationId,
      limit: 100,
    );
    for (final message in messages) {
      if (message.id == messageId) {
        return message;
      }
    }
    await Future<void>.delayed(const Duration(milliseconds: 250));
  }
  throw TestFailure('接收方消息列表未收敛到发送确认');
}

Future<ChatInboxItemView> _waitForReceiverInbox(
  ChatApiContractHarness receiver, {
  required String conversationId,
  required int minimumSeq,
}) async {
  final deadline = DateTime.now().add(const Duration(seconds: 20));
  while (DateTime.now().isBefore(deadline)) {
    final page = await receiver.inbox.listInbox(
      ChatListInboxQuery(limit: ChatListInboxQuery.maximumLimit),
    );
    for (final item in page.items) {
      if (item.id == conversationId && item.lastSeq >= minimumSeq) {
        return item;
      }
    }
    await Future<void>.delayed(const Duration(milliseconds: 250));
  }
  throw TestFailure('接收方 ChatInboxView 未收敛到最新消息');
}

Future<ChatMessageReceipt> _waitForReadReceipt(
  ChatApiContractHarness receiver, {
  required String conversationId,
  required String messageId,
  required String readerPersonaId,
}) async {
  final deadline = DateTime.now().add(const Duration(seconds: 20));
  while (DateTime.now().isBefore(deadline)) {
    final page = await receiver.receipts.getReceipts(
      ChatGetMessageReceiptsQuery(
        conversationId: conversationId,
        messageId: messageId,
      ),
    );
    for (final receipt in page.items) {
      if (receipt.userId == readerPersonaId) {
        return receipt;
      }
    }
    await Future<void>.delayed(const Duration(milliseconds: 250));
  }
  throw TestFailure('接收方 MessageReceiptFact 未收敛');
}
