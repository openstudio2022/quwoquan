// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/spec.md#sit-006
// readiness_case: conversation_user_state_mark_as_read_app_local
// readiness_case: conversation_user_state_update_conversation_settings_app_local
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation_user_state/adapters/conversation_user_state_remote.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('两个用户态命令各自保留 operation、page 与幂等键', () async {
    final executor = _RecordingExecutor();
    final writer = RemoteChatConversationUserStateCommandWriter(
      client: GeneratedCloudOperationClient(executor),
      invocationContext: (clientPageId, idempotencyKey) {
        final surface = clientPageId == 'chat.message.read'
            ? AppUiSurfaces.chatDetail
            : AppUiSurfaces.chatSettings;
        return CloudOperationInvocationContext(
          surfaceId: surface.id,
          routeId: surface.routeId,
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(personaId: 'persona-chat'),
          idempotencyKey: idempotencyKey,
        );
      },
    );

    await writer.markMessageRead(
      ChatMarkConversationMessageReadCommand(
        conversationId: 'conversation-1',
        messageId: 'message-1',
      ),
      idempotencyKey: 'mark-read-1',
    );
    await writer.updateConversationSettings(
      ChatUpdateConversationSettingsCommand(
        conversationId: 'conversation-1',
        muted: true,
      ),
      idempotencyKey: 'settings-1',
    );

    expect(executor.operationIds, <String>[
      AppCloudOperationIds.chatConversationUserStateMarkAsRead,
      AppCloudOperationIds.chatConversationUserStateUpdateConversationSettings,
    ]);
    expect(executor.contexts.map((context) => context.surfaceId), <String>[
      AppUiSurfaces.chatDetail.id,
      AppUiSurfaces.chatSettings.id,
    ]);
    expect(executor.contexts.map((context) => context.clientPageId), <String>[
      'chat.message.read',
      'chat.settings.update',
    ]);
    expect(executor.contexts.map((context) => context.idempotencyKey), <String>[
      'mark-read-1',
      'settings-1',
    ]);
    expect(executor.payloads.first.pathParameters, <String, String>{
      'conversationId': 'conversation-1',
      'messageId': 'message-1',
    });
    expect(executor.payloads.last.body, <String, Object?>{'muted': true});
  });
}

final class _RecordingExecutor implements CloudOperationExecutor {
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
    return responseDecoder(const <String, Object?>{'status': 'ok'});
  }
}
