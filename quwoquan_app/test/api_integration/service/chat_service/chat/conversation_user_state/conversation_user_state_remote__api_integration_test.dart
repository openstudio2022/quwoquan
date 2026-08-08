// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/spec.md#sit-006
// readiness_case: conversation_user_state_mark_as_read_app_api
// readiness_case: conversation_user_state_update_conversation_settings_app_api

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
      'conversation-user-state-api-001',
    )).messageId;
  });
  tearDownAll(() => harness.close());

  test('production Remote 更新用户级 mute/pin 且相同幂等键安全重放', () async {
    final command = ChatUpdateConversationSettingsCommand(
      conversationId: conversationId,
      muted: true,
      pinned: true,
    );

    final first = await harness.userStateCommands.updateConversationSettings(
      command,
      idempotencyKey: 'conversation-user-state-settings-001',
    );
    final replay = await harness.userStateCommands.updateConversationSettings(
      command,
      idempotencyKey: 'conversation-user-state-settings-001',
    );

    expect(first.status, 'ok');
    expect(replay.status, first.status);
  });

  test('production Remote 推进已读水位且相同幂等键安全重放', () async {
    final command = ChatMarkConversationMessageReadCommand(
      conversationId: conversationId,
      messageId: messageId,
    );

    final first = await harness.userStateCommands.markMessageRead(
      command,
      idempotencyKey: 'conversation-user-state-read-001',
    );
    final replay = await harness.userStateCommands.markMessageRead(
      command,
      idempotencyKey: 'conversation-user-state-read-001',
    );

    expect(first.status, 'ok');
    expect(replay.status, first.status);
  });
}
