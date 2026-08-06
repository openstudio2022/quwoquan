import 'package:quwoquan_app/runtime/transport/generated/chat/chat_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ChatConversationMembershipQueryInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);
typedef ChatConversationMembershipCommandInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId,
      String idempotencyKey,
    );

final class RemoteChatConversationMembershipQuery
    implements ChatConversationMembershipQuery {
  const RemoteChatConversationMembershipQuery({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final ChatConversationMembershipQueryInvocationContextFactory
  invocationContext;

  @override
  Future<ConversationMemberPageSlice> listMembers(
    ChatListConversationMembersQuery query,
  ) {
    return client.chatConversationMembershipListMembers(
      query,
      context: invocationContext(ChatRequestPageIds.listMembers),
    );
  }
}

final class RemoteChatConversationMembershipCommandWriter
    implements ChatConversationMembershipCommandWriter {
  const RemoteChatConversationMembershipCommandWriter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final ChatConversationMembershipCommandInvocationContextFactory
  invocationContext;

  @override
  Future<ConversationMembershipCommandAck> addMembers(
    ChatAddConversationMembersCommand command, {
    required String idempotencyKey,
  }) {
    return client.chatConversationMembershipAddMembers(
      command,
      context: invocationContext(ChatRequestPageIds.addMembers, idempotencyKey),
    );
  }

  @override
  Future<ConversationMembershipCommandAck> removeMember(
    ChatRemoveConversationMemberCommand command, {
    required String idempotencyKey,
  }) {
    return client.chatConversationMembershipRemoveMember(
      command,
      context: invocationContext(
        ChatRequestPageIds.removeMember,
        idempotencyKey,
      ),
    );
  }

  @override
  Future<ConversationMembershipCommandAck> leaveConversation(
    ChatLeaveConversationCommand command, {
    required String idempotencyKey,
  }) {
    return client.chatConversationMembershipLeaveConversation(
      command,
      context: invocationContext(
        ChatRequestPageIds.leaveConversation,
        idempotencyKey,
      ),
    );
  }

  @override
  Future<ConversationMembershipCommandAck> inviteAssistant(
    ChatInviteConversationAssistantCommand command, {
    required String idempotencyKey,
  }) {
    return client.chatConversationMembershipInviteAssistant(
      command,
      context: invocationContext(
        ChatRequestPageIds.inviteAssistant,
        idempotencyKey,
      ),
    );
  }

  @override
  Future<ConversationMembershipCommandAck> removeAssistant(
    ChatRemoveConversationAssistantCommand command, {
    required String idempotencyKey,
  }) {
    return client.chatConversationMembershipRemoveAssistant(
      command,
      context: invocationContext(
        ChatRequestPageIds.removeAssistant,
        idempotencyKey,
      ),
    );
  }

  @override
  Future<ConversationMembershipCommandAck> transferOwnership(
    ChatTransferConversationOwnershipCommand command, {
    required String idempotencyKey,
  }) {
    return client.chatConversationMembershipTransferOwnership(
      command,
      context: invocationContext(
        ChatRequestPageIds.transferOwnership,
        idempotencyKey,
      ),
    );
  }

  @override
  Future<ConversationMembershipCommandAck> updateAdmins(
    ChatUpdateConversationAdminsCommand command, {
    required String idempotencyKey,
  }) {
    return client.chatConversationMembershipUpdateGroupAdmins(
      command,
      context: invocationContext(
        ChatRequestPageIds.updateGroupAdmins,
        idempotencyKey,
      ),
    );
  }
}
