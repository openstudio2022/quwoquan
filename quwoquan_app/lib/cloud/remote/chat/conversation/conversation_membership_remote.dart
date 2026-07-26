import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_request_page_ids.g.dart';
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
  Future<ChatConversationMemberPageSlice> listMembers(
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
  Future<ChatCommandAck> addMembers(ChatAddConversationMembersCommand command) {
    return client.chatConversationMembershipAddMembers(
      command,
      context: invocationContext(
        ChatRequestPageIds.addMembers,
        command.idempotencyKey,
      ),
    );
  }

  @override
  Future<ChatCommandAck> removeMember(
    ChatRemoveConversationMemberCommand command,
  ) {
    return client.chatConversationMembershipRemoveMember(
      command,
      context: invocationContext(
        ChatRequestPageIds.removeMember,
        command.idempotencyKey,
      ),
    );
  }

  @override
  Future<ChatCommandAck> leaveConversation(
    ChatLeaveConversationCommand command,
  ) {
    return client.chatConversationMembershipLeaveConversation(
      command,
      context: invocationContext(
        ChatRequestPageIds.leaveConversation,
        command.idempotencyKey,
      ),
    );
  }

  @override
  Future<ChatCommandAck> inviteAssistant(
    ChatInviteConversationAssistantCommand command,
  ) {
    return client.chatConversationMembershipInviteAssistant(
      command,
      context: invocationContext(
        ChatRequestPageIds.inviteAssistant,
        command.idempotencyKey,
      ),
    );
  }

  @override
  Future<ChatCommandAck> removeAssistant(
    ChatRemoveConversationAssistantCommand command,
  ) {
    return client.chatConversationMembershipRemoveAssistant(
      command,
      context: invocationContext(
        ChatRequestPageIds.removeAssistant,
        command.idempotencyKey,
      ),
    );
  }

  @override
  Future<ChatCommandAck> transferOwnership(
    ChatTransferConversationOwnershipCommand command,
  ) {
    return client.chatConversationMembershipTransferOwnership(
      command,
      context: invocationContext(
        ChatRequestPageIds.transferOwnership,
        command.idempotencyKey,
      ),
    );
  }

  @override
  Future<ChatCommandAck> updateAdmins(
    ChatUpdateConversationAdminsCommand command,
  ) {
    return client.chatConversationMembershipUpdateGroupAdmins(
      command,
      context: invocationContext(
        ChatRequestPageIds.updateGroupAdmins,
        command.idempotencyKey,
      ),
    );
  }
}
