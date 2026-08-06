// spec_ref: specs/feature-tree/chat-conversation/group-creation-member-management/spec.md#sit-001
// spec_ref: specs/feature-tree/chat-conversation/spec.md#dom-002
// readiness_case: conversation_membership_add_members_app_local
// readiness_case: conversation_membership_remove_member_app_local
// readiness_case: conversation_membership_leave_conversation_app_local
// readiness_case: conversation_membership_transfer_ownership_app_local
// readiness_case: conversation_membership_invite_assistant_app_local
// readiness_case: conversation_membership_remove_assistant_app_local
// readiness_case: conversation_membership_update_group_admins_app_local
// readiness_case: conversation_membership_list_members_app_local
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation_membership/adapters/conversation_membership_remote.dart';
import 'package:quwoquan_app/runtime/transport/generated/chat/chat_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'ListMembers delegates to the object generated typed operation',
    () async {
      final executor = _RoutingExecutor();
      final query = RemoteChatConversationMembershipQuery(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: _queryContext,
      );

      final page = await query.listMembers(
        ChatListConversationMembersQuery(
          conversationId: 'conversation-1',
          cursor: 'member-cursor',
          limit: 30,
          role: 'admin',
          sort: 'display_name_asc',
          query: '小趣',
        ),
      );

      expect(executor.operationIds, <String>[
        AppCloudOperationIds.chatConversationMembershipListMembers,
      ]);
      expect(executor.operations.single.method, 'GET');
      expect(
        executor.operations.single.pathTemplate,
        '/chat/conversations/{conversationId}/members',
      );
      expect(
        executor.contexts.single.clientPageId,
        ChatRequestPageIds.listMembers,
      );
      expect(executor.payloads.single.pathParameters, <String, String>{
        'conversationId': 'conversation-1',
      });
      expect(executor.payloads.single.queryParameters, <String, String>{
        'cursor': 'member-cursor',
        'limit': '30',
        'role': 'admin',
        'sort': 'display_name_asc',
        'query': '小趣',
      });
      expect(executor.payloads.single.body, isNull);
      expect(page.items.single.displayName, '小趣');
      expect(page.nextCursor, 'next-member-token');
    },
  );

  test(
    'seven membership commands preserve operation and idempotency identity',
    () async {
      final executor = _RoutingExecutor();
      final writer = RemoteChatConversationMembershipCommandWriter(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: _commandContext,
      );

      await writer.addMembers(
        ChatAddConversationMembersCommand(
          conversationId: 'conversation-1',
          userIds: const <String>['persona-2'],
        ),
        idempotencyKey: 'add-1',
      );
      await writer.removeMember(
        ChatRemoveConversationMemberCommand(
          conversationId: 'conversation-1',
          userId: 'persona-2',
        ),
        idempotencyKey: 'remove-1',
      );
      await writer.leaveConversation(
        ChatLeaveConversationCommand(conversationId: 'conversation-1'),
        idempotencyKey: 'leave-1',
      );
      await writer.inviteAssistant(
        ChatInviteConversationAssistantCommand(
          conversationId: 'conversation-1',
        ),
        idempotencyKey: 'assistant-invite-1',
      );
      await writer.removeAssistant(
        ChatRemoveConversationAssistantCommand(
          conversationId: 'conversation-1',
        ),
        idempotencyKey: 'assistant-remove-1',
      );
      await writer.transferOwnership(
        ChatTransferConversationOwnershipCommand(
          conversationId: 'conversation-1',
          newOwnerId: 'persona-2',
        ),
        idempotencyKey: 'transfer-1',
      );
      await writer.updateAdmins(
        ChatUpdateConversationAdminsCommand(
          conversationId: 'conversation-1',
          adminIds: const <String>['persona-2'],
        ),
        idempotencyKey: 'admins-1',
      );

      expect(executor.operationIds, <String>[
        AppCloudOperationIds.chatConversationMembershipAddMembers,
        AppCloudOperationIds.chatConversationMembershipRemoveMember,
        AppCloudOperationIds.chatConversationMembershipLeaveConversation,
        AppCloudOperationIds.chatConversationMembershipInviteAssistant,
        AppCloudOperationIds.chatConversationMembershipRemoveAssistant,
        AppCloudOperationIds.chatConversationMembershipTransferOwnership,
        AppCloudOperationIds.chatConversationMembershipUpdateGroupAdmins,
      ]);
      expect(executor.contexts.map((context) => context.clientPageId), <String>[
        ChatRequestPageIds.addMembers,
        ChatRequestPageIds.removeMember,
        ChatRequestPageIds.leaveConversation,
        ChatRequestPageIds.inviteAssistant,
        ChatRequestPageIds.removeAssistant,
        ChatRequestPageIds.transferOwnership,
        ChatRequestPageIds.updateGroupAdmins,
      ]);
      expect(
        executor.contexts.map((context) => context.idempotencyKey),
        <String>[
          'add-1',
          'remove-1',
          'leave-1',
          'assistant-invite-1',
          'assistant-remove-1',
          'transfer-1',
          'admins-1',
        ],
      );
      expect(executor.payloads.first.body, <String, Object?>{
        'userIds': <String>['persona-2'],
      });
      expect(executor.payloads[1].pathParameters, <String, String>{
        'conversationId': 'conversation-1',
        'userId': 'persona-2',
      });
      expect(executor.payloads[2].body, isNull);
      expect(executor.payloads[3].body, isNull);
      expect(executor.payloads[4].body, isNull);
      expect(executor.payloads[5].body, <String, Object?>{
        'newOwnerId': 'persona-2',
      });
      expect(executor.payloads[6].body, <String, Object?>{
        'adminIds': <String>['persona-2'],
      });
    },
  );
}

CloudOperationInvocationContext _queryContext(String clientPageId) {
  return CloudOperationInvocationContext(
    surfaceId: 'chat-membership-contract',
    clientPageId: clientPageId,
    actor: const CloudOperationActorContext(personaId: 'persona-1'),
  );
}

CloudOperationInvocationContext _commandContext(
  String clientPageId,
  String idempotencyKey,
) {
  return CloudOperationInvocationContext(
    surfaceId: 'chat-membership-contract',
    clientPageId: clientPageId,
    actor: const CloudOperationActorContext(personaId: 'persona-1'),
    idempotencyKey: idempotencyKey,
  );
}

final class _RoutingExecutor implements CloudOperationExecutor {
  final List<String> operationIds = <String>[];
  final List<CloudOperationContract> operations = <CloudOperationContract>[];
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
    operations.add(operation);
    contexts.add(context);
    payloads.add(requestEncoder());
    return responseDecoder(_responseFor(operation.canonicalOperationId));
  }
}

Object? _responseFor(String operationId) {
  if (operationId ==
      AppCloudOperationIds.chatConversationMembershipListMembers) {
    return <String, Object?>{
      'items': <Object?>[_member],
      'nextCursor': 'next-member-token',
    };
  }
  return const <String, Object?>{'status': 'ok'};
}

const Map<String, Object?> _member = <String, Object?>{
  'userId': 'persona-2',
  'userHandle': 'xiaoq_public',
  'displayName': '小趣',
  'avatarUrl': '',
  'role': 'admin',
  'memberType': 'user',
  'joinedAt': '2026-07-20T08:00:00Z',
  'isCurrentUser': false,
};
