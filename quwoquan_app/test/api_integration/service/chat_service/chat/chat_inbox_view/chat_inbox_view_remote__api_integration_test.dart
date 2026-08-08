// spec_ref: specs/feature-tree/chat-conversation/list-detail-message-delivery/conversation-list-source-switch/spec.md#gwt-001
// readiness_case: chat_inbox_view_list_inbox_app_api

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/chat_api_contract_harness.dart';

void main() {
  late ChatApiContractHarness harness;
  late String conversationId;

  setUpAll(() async {
    harness = await ChatApiContractHarness.create();
    conversationId = await harness.seedConversation();
    await harness.sendMessage(conversationId, 'chat-inbox-view-api-001');
  });
  tearDownAll(() => harness.close());

  test('production Remote 经真实 gateway 返回投影后的 ChatInboxView', () async {
    final item = await _waitForInboxItem(harness, conversationId);

    expect(item.id, conversationId);
    expect(item.type, 'group');
    expect(item.title, 'L3 contract seed conversation');
    expect(item.lastMessagePreview, 'L3 contract test message');
    expect(item.lastSeq, greaterThan(0));
  });
}

Future<ChatInboxItemView> _waitForInboxItem(
  ChatApiContractHarness harness,
  String conversationId,
) async {
  final deadline = DateTime.now().add(const Duration(seconds: 15));
  while (true) {
    final page = await harness.inbox.listInbox(
      ChatListInboxQuery(limit: ChatListInboxQuery.maximumLimit),
    );
    final items = page.items
        .where((candidate) => candidate.id == conversationId)
        .toList(growable: false);
    if (items.isNotEmpty && items.single.lastSeq > 0) {
      return items.single;
    }
    if (!DateTime.now().isBefore(deadline)) {
      throw TestFailure(
        'ChatInboxView did not converge for conversation $conversationId',
      );
    }
    await Future<void>.delayed(const Duration(milliseconds: 250));
  }
}
