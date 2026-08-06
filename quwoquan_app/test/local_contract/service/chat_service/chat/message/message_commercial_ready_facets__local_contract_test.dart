// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/commercial-remote-only-message-system/spec.md#gwt-001
// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/spec.md#sit-006
// readiness_case: message_list_messages_app_local
// readiness_case: message_recall_message_app_local
// readiness_case: message_sync_messages_app_local
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/adapters/message_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  late _RoutingExecutor executor;
  late GeneratedCloudOperationClient client;

  setUp(() {
    executor = _RoutingExecutor();
    client = GeneratedCloudOperationClient(executor);
  });

  test('消息列表、同步与撤回三个操作保持 typed 单路径', () async {
    final query = RemoteChatMessageQuery(
      client: client,
      invocationContext: _queryContext,
    );
    final mutation = RemoteChatMessageMutationWriter(
      client: client,
      invocationContext: _commandContext,
    );
    final messages = await query.listMessages(
      ChatListMessagesQuery(
        conversationId: 'conversation-1',
        beforeSeq: 20,
        limit: 10,
      ),
    );
    final sync = await query.syncMessages(
      ChatSyncMessagesQuery(
        conversationId: 'conversation-1',
        lastSeq: 8,
        limit: 100,
      ),
    );
    await mutation.recallMessage(
      ChatRecallMessageCommand(
        conversationId: 'conversation-1',
        messageId: 'message-1',
      ),
      idempotencyKey: 'recall-1',
    );
    expect(messages.items.single.content, '你好');
    expect(sync.messages.single.seq, 9);
    expect(sync.hasMore, isFalse);
    expect(executor.operationIds, <String>[
      AppCloudOperationIds.chatMessageListMessages,
      AppCloudOperationIds.chatMessageSyncMessages,
      AppCloudOperationIds.chatMessageRecallMessage,
    ]);
    expect(executor.payloads.first.queryParameters, <String, String>{
      'limit': '10',
      'beforeSeq': '20',
    });
    expect(executor.payloads[1].body, <String, Object?>{
      'lastSeq': 8,
      'limit': 100,
    });
    expect(
      executor.contexts.skip(2).map((context) => context.idempotencyKey),
      <String>['recall-1'],
    );
  });
}

CloudOperationInvocationContext _queryContext(String clientPageId) {
  return CloudOperationInvocationContext(
    surfaceId: 'chat-contract',
    clientPageId: clientPageId,
    actor: const CloudOperationActorContext(
      accountId: 'account-1',
      personaId: 'persona-1',
    ),
  );
}

CloudOperationInvocationContext _commandContext(
  String clientPageId,
  String idempotencyKey,
) {
  return CloudOperationInvocationContext(
    surfaceId: 'chat-contract',
    clientPageId: clientPageId,
    actor: const CloudOperationActorContext(
      accountId: 'account-1',
      personaId: 'persona-1',
    ),
    idempotencyKey: idempotencyKey,
  );
}

final class _RoutingExecutor implements CloudOperationExecutor {
  final List<String> operationIds = <String>[];
  final List<CloudOperationInvocationContext> contexts =
      <CloudOperationInvocationContext>[];
  final List<CloudOperationRequestPayload> payloads =
      <CloudOperationRequestPayload>[];

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    operationIds.add(operation.canonicalOperationId);
    contexts.add(context);
    payloads.add(requestEncoder());
    return responseDecoder(_responseFor(operation.canonicalOperationId));
  }
}

Object? _responseFor(String operationId) {
  return switch (operationId) {
    AppCloudOperationIds.chatMessageListMessages => <String, Object?>{
      'items': <Object?>[_message],
      'nextBeforeSeq': null,
    },
    AppCloudOperationIds.chatMessageSyncMessages => <String, Object?>{
      'messages': <Object?>[
        <String, Object?>{..._message, 'seq': 9},
      ],
      'hasMore': false,
    },
    _ => const <String, Object?>{'status': 'ok'},
  };
}

const Map<String, Object?> _message = <String, Object?>{
  'id': 'message-1',
  'conversationId': 'conversation-1',
  'seq': 8,
  'clientMsgId': 'client-message-1',
  'senderId': 'persona-2',
  'senderName': '小趣',
  'senderAvatar': '',
  'type': 'text',
  'content': '你好',
  'mediaAssetId': null,
  'card': null,
  'replyToMessageId': null,
  'mentions': <String>[],
  'status': 'sent',
  'timestamp': '2026-07-21T08:00:00Z',
  'recalledAt': null,
  'mediaDeliveryUrl': null,
  'mediaType': null,
  'mediaContentType': null,
  'mediaFileSizeBytes': null,
};
