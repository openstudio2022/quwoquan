import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/remote/chat/message/message_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('SendMessage only delegates to its generated typed operation', () async {
    final executor = _RecordingExecutor(
      response: <String, Object?>{
        'messageId': 'message-1',
        'seq': 8,
        'timestamp': '2026-07-15T08:00:00Z',
      },
    );
    final writer = RemoteChatMessageCommandWriter(
      client: GeneratedCloudOperationClient(executor),
      invocationContext: _context,
    );

    final result = await writer.sendMessage(
      ChatSendMessageCommand(
        conversationId: 'conversation-1',
        type: 'text',
        content: 'typed message',
        clientMsgId: 'client-message-1',
      ),
    );

    expect(
      executor.operation?.canonicalOperationId,
      AppCloudOperationIds.chatMessageSendMessage,
    );
    expect(executor.operation?.method, 'POST');
    expect(
      executor.operation?.pathTemplate,
      '/v1/chat/conversations/{conversationId}/messages',
    );
    expect(executor.context?.surfaceId, AppUiSurfaces.chatDetail.id);
    expect(executor.context?.idempotencyKey, 'client-message-1');
    expect(executor.pathParameters, <String, String>{
      'conversationId': 'conversation-1',
    });
    expect(executor.body, <String, Object?>{
      'type': 'text',
      'content': 'typed message',
      'clientMsgId': 'client-message-1',
    });
    expect(result.messageId, 'message-1');
    expect(result.seq, 8);
  });
}

CloudOperationInvocationContext _context(
  String clientPageId,
  String idempotencyKey,
) {
  return CloudOperationInvocationContext(
    surfaceId: AppUiSurfaces.chatDetail.id,
    routeId: AppUiSurfaces.chatDetail.routeId,
    clientPageId: clientPageId,
    actor: const CloudOperationActorContext(personaId: 'persona-1'),
    idempotencyKey: idempotencyKey,
  );
}

final class _RecordingExecutor implements CloudOperationExecutor {
  _RecordingExecutor({required this.response});

  final Object? response;
  CloudOperationContract? operation;
  CloudOperationInvocationContext? context;
  Map<String, String> pathParameters = const <String, String>{};
  Object? body;

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    this.operation = operation;
    this.context = context;
    final payload = requestEncoder();
    pathParameters = payload.pathParameters;
    body = payload.body;
    return responseDecoder(response);
  }
}
