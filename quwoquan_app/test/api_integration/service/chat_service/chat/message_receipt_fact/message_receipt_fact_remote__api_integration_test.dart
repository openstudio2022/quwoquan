// spec_ref: specs/feature-tree/chat-conversation/list-detail-message-delivery/delivery-and-read-receipt/spec.md#gwt-001
// readiness_case: message_receipt_fact_get_receipts_app_api

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/chat_api_contract_harness.dart';

void main() {
  late ChatApiContractHarness harness;
  late String conversationId;
  late String messageId;

  setUpAll(() async {
    harness = await ChatApiContractHarness.create();
    conversationId = await harness.seedConversation(maxGroupSize: 50);
    messageId = (await harness.sendMessage(
      conversationId,
      'message-receipt-fact-api-001',
    )).messageId;
    await harness.userStateCommands.markMessageRead(
      ChatMarkConversationMessageReadCommand(
        conversationId: conversationId,
        messageId: messageId,
      ),
      idempotencyKey: 'message-receipt-fact-read-001',
    );
  });
  tearDownAll(() => harness.close());

  test('production Remote 读取同一事务追加的不可变 MessageReceiptFact', () async {
    final page = await harness.receipts.getReceipts(
      ChatGetMessageReceiptsQuery(
        conversationId: conversationId,
        messageId: messageId,
      ),
    );

    final receipt = page.items.singleWhere(
      (candidate) =>
          candidate.userId == harness.session.activePersona?.personaId,
    );
    expect(receipt.messageId, messageId);
    expect(receipt.conversationId, conversationId);
    expect(receipt.id, isNotEmpty);
    expect(receipt.readAt.isUtc, isTrue);
  });
}
