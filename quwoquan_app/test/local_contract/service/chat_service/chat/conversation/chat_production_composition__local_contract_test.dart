// spec_ref: specs/feature-tree/chat-conversation/spec.md#dom-002
// readiness_case: conversation_create_conversation_app_local
// readiness_case: conversation_get_conversation_app_local
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/chat_conversation_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation_membership/application/public/chat_member_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/chat_message_repository.dart';
import 'package:quwoquan_app/runtime/di/chat_dependencies.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('repository shares one production composition across chat facets', () {
    final repository = ChatProductionComposition.repository(
      client: GeneratedCloudOperationClient(
        _RecordingExecutor(response: _conversationWire()),
      ),
      invocationContext: _context,
    );

    expect(repository, isA<ChatConversationRepository>());
    expect(repository, isA<ChatMessageRepository>());
    expect(repository, isA<ChatMemberRepository>());
    expect(repository, isA<ChatContactRepository>());
    expect(repository, isA<ChatGroupSelectionRepository>());
    expect(repository, isA<ChatGroupAdminRepository>());
  });

  test(
    'composition owns conversation surface and command identity routing',
    () async {
      final executor = _RecordingExecutor(response: _conversationWire());
      final repository = ChatProductionComposition.repository(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: _context,
      );

      await repository.getConversation('conversation-1');
      expect(executor.context?.surfaceId, AppUiSurfaces.chatDetail.id);
      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.chatConversationGetConversation,
      );

      await repository.createConversation(
        type: 'group',
        title: 'typed group',
        idempotencyKey: 'create-conversation-1',
      );
      expect(executor.context?.surfaceId, AppUiSurfaces.startGroupChat.id);
      expect(executor.context?.idempotencyKey, 'create-conversation-1');
      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.chatConversationCreateConversation,
      );
    },
  );

  test(
    'composition routes inbox object through the chat list surface',
    () async {
      final executor = _RecordingExecutor(
        response: <String, Object?>{
          'items': <Object?>[_inboxWire()],
          'nextCursor': null,
        },
      );
      final repository = ChatProductionComposition.repository(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: _context,
      );

      final items = await repository.listInbox(limit: 10);

      expect(items.single.id, 'conversation-1');
      expect(executor.context?.surfaceId, AppUiSurfaces.chatList.id);
      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.chatChatInboxViewListInbox,
      );
    },
  );

  test(
    'composition exposes MessageReceiptFact through the chat detail surface',
    () async {
      final executor = _RecordingExecutor(
        response: <String, Object?>{
          'items': <Object?>[
            <String, Object?>{
              'id': 'receipt-1',
              'messageId': 'message-1',
              'conversationId': 'conversation-1',
              'userId': 'persona-reader',
              'readAt': '2026-08-06T02:30:00Z',
            },
          ],
        },
      );
      final query = ChatProductionComposition.messageReceiptFactQuery(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: _context,
      );

      final page = await query.getReceipts(
        ChatGetMessageReceiptsQuery(
          conversationId: 'conversation-1',
          messageId: 'message-1',
        ),
      );

      expect(page.items.single.userId, 'persona-reader');
      expect(executor.context?.surfaceId, AppUiSurfaces.chatDetail.id);
      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.chatMessageReceiptFactGetReceipts,
      );
    },
  );

  test(
    'message command writer is composed through the chat detail surface',
    () async {
      final executor = _RecordingExecutor(
        response: <String, Object?>{
          'messageId': 'message-1',
          'seq': 1,
          'timestamp': '2026-08-05T00:00:00Z',
        },
      );
      final writer = ChatProductionComposition.messageCommandWriter(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: _context,
      );

      await writer.sendMessage(
        ChatSendMessageCommand(
          conversationId: 'conversation-1',
          type: 'text',
          content: 'typed message',
          clientMsgId: 'client-message-1',
        ),
      );

      expect(executor.context?.surfaceId, AppUiSurfaces.chatDetail.id);
      expect(executor.context?.idempotencyKey, 'client-message-1');
      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.chatMessageSendMessage,
      );
    },
  );
}

CloudOperationInvocationContext _context(
  AppUiSurface surface,
  String clientPageId, {
  String? idempotencyKey,
}) {
  return CloudOperationInvocationContext(
    surfaceId: surface.id,
    routeId: surface.routeId,
    clientPageId: clientPageId,
    actor: const CloudOperationActorContext(
      accountId: 'account-1',
      personaId: 'persona-1',
    ),
    idempotencyKey: idempotencyKey,
  );
}

final class _RecordingExecutor implements CloudOperationExecutor {
  _RecordingExecutor({required this.response});

  final Object? response;
  CloudOperationContract? operation;
  CloudOperationInvocationContext? context;

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    this.operation = operation;
    this.context = context;
    requestEncoder();
    return responseDecoder(response);
  }
}

Map<String, Object?> _conversationWire() => <String, Object?>{
  'id': 'conversation-1',
  'conversationId': 'conversation-1',
  'type': 'group',
  'title': 'typed group',
  'avatarUrl': 'https://cdn.example/conversation-1.png',
  'groupAvatarVersion': 1,
  'creatorId': 'persona-1',
  'circleId': '',
  'circleGroupId': '',
  'entityId': '',
  'originType': 'ad_hoc_group',
  'maxSeq': 0,
  'memberCount': 1,
  'membersRosterRevision': 1,
  'maxGroupSize': 500,
  'receiptEnabled': true,
  'announcement': '',
  'announcementUpdatedBy': '',
  'announcementUpdatedAt': '2026-08-05T00:00:00Z',
  'nameEditableByAdminOnly': false,
  'lastMessageId': '',
  'lastMessagePreview': '',
  'lastMessageType': 'text',
  'lastMessageTime': '2026-08-05T00:00:00Z',
  'messageCount': 0,
  'status': 'active',
  'createdAt': '2026-08-05T00:00:00Z',
  'updatedAt': '2026-08-05T00:00:00Z',
};

Map<String, Object?> _inboxWire() => <String, Object?>{
  'id': 'conversation-1',
  'type': 'direct',
  'title': 'typed inbox',
  'avatarUrl': '',
  'groupAvatarVersion': 0,
  'lastMessagePreview': 'latest message',
  'lastMessageType': 'text',
  'lastMessageTime': '2026-08-05T00:00:00Z',
  'lastSeq': 1,
  'unreadCount': 1,
  'mentionUnreadCount': 0,
  'muted': false,
  'pinned': false,
  'circleId': null,
};
