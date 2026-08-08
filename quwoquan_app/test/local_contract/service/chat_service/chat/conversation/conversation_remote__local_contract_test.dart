// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/commercial-remote-only-message-system/spec.md#gwt-001
// readiness_case: conversation_list_conversations_app_local

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/adapters/conversation_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'ListConversations only delegates to generated typed operation',
    () async {
      final executor = _RecordingExecutor(
        response: <String, Object?>{
          'items': <Object?>[_conversationWire()],
          'nextCursor': 'next-keyset-token',
        },
      );
      final query = RemoteChatConversationQuery(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: _context,
      );

      final page = await query.listConversations(
        ChatListConversationsQuery(cursor: 'current-keyset-token', limit: 30),
      );

      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.chatConversationListConversations,
      );
      expect(executor.operation?.method, 'GET');
      expect(executor.operation?.pathTemplate, '/chat/conversations');
      expect(executor.context?.surfaceId, AppUiSurfaces.chatList.id);
      expect(executor.queryParameters, <String, String>{
        'cursor': 'current-keyset-token',
        'limit': '30',
      });
      expect(executor.pathParameters, isEmpty);
      expect(executor.body, isNull);
      expect(page.items.single.id, 'conversation-1');
      expect(page.nextCursor, 'next-keyset-token');
    },
  );

  test(
    'CreateConversation carries the stable command idempotency key',
    () async {
      final executor = _RecordingExecutor(response: _conversationWire());
      final writer = RemoteChatConversationCommandWriter(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: _commandContext,
      );

      final created = await writer.createConversation(
        ChatCreateConversationCommand(type: 'group', title: '契约群聊'),
        idempotencyKey: 'conversation-create-1',
      );

      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.chatConversationCreateConversation,
      );
      expect(executor.context?.idempotencyKey, 'conversation-create-1');
      expect(executor.body, <String, Object?>{
        'type': 'group',
        'title': '契约群聊',
      });
      expect(created.id, 'conversation-1');
    },
  );
}

CloudOperationInvocationContext _context(String clientPageId) {
  return CloudOperationInvocationContext(
    surfaceId: AppUiSurfaces.chatList.id,
    routeId: AppUiSurfaces.chatList.routeId,
    clientPageId: clientPageId,
    actor: const CloudOperationActorContext(personaId: 'persona-1'),
  );
}

CloudOperationInvocationContext _commandContext(
  String clientPageId,
  String idempotencyKey,
) {
  final base = _context(clientPageId);
  return CloudOperationInvocationContext(
    surfaceId: base.surfaceId,
    routeId: base.routeId,
    clientPageId: base.clientPageId,
    actor: base.actor,
    idempotencyKey: idempotencyKey,
  );
}

final class _RecordingExecutor implements CloudOperationExecutor {
  _RecordingExecutor({required this.response});

  final Object? response;
  CloudOperationContract? operation;
  CloudOperationInvocationContext? context;
  Map<String, String> pathParameters = const <String, String>{};
  Map<String, String> queryParameters = const <String, String>{};
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
    queryParameters = payload.queryParameters;
    body = payload.body;
    return responseDecoder(response);
  }
}

Map<String, Object?> _conversationWire() => <String, Object?>{
  'id': 'conversation-1',
  'conversationId': 'conversation-1',
  'type': 'group',
  'title': '契约群聊',
  'avatarUrl': 'https://cdn.example/conversation-1.png',
  'groupAvatarVersion': 1,
  'creatorId': 'persona-1',
  'circleId': '',
  'circleGroupId': '',
  'gatheringId': '',
  'gatheringSourceVersion': 0,
  'accessMode': 'active',
  'postingPolicy': 'member_chat',
  'entityId': '',
  'originType': 'ad_hoc_group',
  'maxSeq': 8,
  'memberCount': 2,
  'membersRosterRevision': 3,
  'maxGroupSize': 500,
  'receiptEnabled': true,
  'announcement': '',
  'announcementUpdatedBy': '',
  'announcementUpdatedAt': '2026-07-21T06:00:00Z',
  'nameEditableByAdminOnly': false,
  'lastMessageId': 'message-8',
  'lastMessagePreview': '最后一条消息',
  'lastMessageType': 'text',
  'lastMessageTime': '2026-07-21T06:00:00Z',
  'messageCount': 8,
  'status': 'active',
  'createdAt': '2026-07-20T06:00:00Z',
  'updatedAt': '2026-07-21T06:00:00Z',
};
