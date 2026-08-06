// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/commercial-remote-only-message-system/spec.md#gwt-001
// readiness_case: message_receipt_fact_get_receipts_app_local
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/chat_service/chat/message_receipt_fact/adapters/message_receipt_fact_remote.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('GetReceipts 只由 MessageReceiptFact adapter 发起并强类型解码', () async {
    final executor = _ReceiptExecutor();
    final query = RemoteMessageReceiptFactQuery(
      client: GeneratedCloudOperationClient(executor),
      invocationContext: (clientPageId) => CloudOperationInvocationContext(
        surfaceId: AppUiSurfaces.chatDetail.id,
        routeId: AppUiSurfaces.chatDetail.routeId,
        clientPageId: clientPageId,
        actor: const CloudOperationActorContext(personaId: 'persona-chat'),
      ),
    );

    final page = await query.getReceipts(
      ChatGetMessageReceiptsQuery(
        conversationId: 'conversation-1',
        messageId: 'message-1',
      ),
    );

    expect(
      executor.operation?.canonicalOperationId,
      AppCloudOperationIds.chatMessageReceiptFactGetReceipts,
    );
    expect(executor.context?.surfaceId, AppUiSurfaces.chatDetail.id);
    expect(executor.context?.clientPageId, 'chat.message.receipts');
    expect(executor.payload?.pathParameters, <String, String>{
      'conversationId': 'conversation-1',
      'messageId': 'message-1',
    });
    expect(page.items.single.id, 'receipt-1');
    expect(page.items.single.userId, 'persona-reader');
  });
}

final class _ReceiptExecutor implements CloudOperationExecutor {
  CloudOperationContract? operation;
  CloudOperationInvocationContext? context;
  CloudOperationRequestPayload? payload;

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    this.operation = operation;
    this.context = context;
    payload = requestEncoder();
    return responseDecoder(<String, Object?>{
      'items': <Object?>[
        <String, Object?>{
          'id': 'receipt-1',
          'messageId': 'message-1',
          'conversationId': 'conversation-1',
          'userId': 'persona-reader',
          'readAt': '2026-08-05T09:00:00Z',
        },
      ],
    });
  }
}
