import 'chat_operation_contracts.g.dart';

export 'chat_operation_contracts.g.dart';

abstract interface class ChatConversationMembershipQuery {
  Future<ConversationMemberPageSlice> listMembers(
    ChatListConversationMembersQuery query,
  );
}

abstract interface class ChatConversationMembershipCommandWriter {
  Future<ConversationMembershipCommandAck> addMembers(
    ChatAddConversationMembersCommand command, {
    required String idempotencyKey,
  });

  Future<ConversationMembershipCommandAck> removeMember(
    ChatRemoveConversationMemberCommand command, {
    required String idempotencyKey,
  });

  Future<ConversationMembershipCommandAck> leaveConversation(
    ChatLeaveConversationCommand command, {
    required String idempotencyKey,
  });

  Future<ConversationMembershipCommandAck> inviteAssistant(
    ChatInviteConversationAssistantCommand command, {
    required String idempotencyKey,
  });

  Future<ConversationMembershipCommandAck> removeAssistant(
    ChatRemoveConversationAssistantCommand command, {
    required String idempotencyKey,
  });

  Future<ConversationMembershipCommandAck> transferOwnership(
    ChatTransferConversationOwnershipCommand command, {
    required String idempotencyKey,
  });

  Future<ConversationMembershipCommandAck> updateAdmins(
    ChatUpdateConversationAdminsCommand command, {
    required String idempotencyKey,
  });
}
