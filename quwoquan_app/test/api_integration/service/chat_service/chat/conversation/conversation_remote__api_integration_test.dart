// spec_ref: specs/feature-tree/chat-conversation/list-detail-message-delivery/conversation-list-source-switch/spec.md#gwt-001

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';

import '../../../../../support/runtime/api_contract/chat_api_contract_harness.dart';

void main() {
  late ChatApiContractHarness harness;
  late String conversationId;

  setUpAll(() async {
    harness = await ChatApiContractHarness.create();
    conversationId = await harness.seedConversation();
  });
  tearDownAll(() => harness.close());

  test('generated client 通过 production Remote 返回会话列表', () async {
    final stopwatch = Stopwatch()..start();
    final conversations = await harness.repository.listConversations(limit: 5);
    stopwatch.stop();

    expect(stopwatch.elapsedMilliseconds, lessThan(800));
    expect(conversations, isNotEmpty);
    expect(conversations.first.id, isNotEmpty);
    expect(conversations.first.type, isNotEmpty);
  });

  test('generated client 通过 production Remote 返回完整会话', () async {
    final conversation = await harness.repository.getConversation(
      conversationId,
    );

    expect(conversation.id, conversationId);
    expect(conversation.type, isNotEmpty);
    expect(conversation.status, 'active');
    expect(conversation.createdAt, isNotNull);
  });

  test('不存在的 conversationId 保留 canonical error', () async {
    await expectLater(
      harness.repository.getConversation('nonexistent_conv_00000'),
      throwsA(
        isA<CloudException>()
            .having((error) => error.statusCode, 'statusCode', 404)
            .having(
              (error) => error.code,
              'code',
              'CHAT.USER.conversation_not_found',
            ),
      ),
    );
  });
}
