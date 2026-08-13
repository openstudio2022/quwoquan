// ignore_for_file: prefer_initializing_formals

import 'package:quwoquan_app/service/chat_service/chat/chat_inbox_view/application/chat_inbox_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/chat_inbox_view/application/public/chat_inbox_view_data.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/chat_conversation_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/chat_conversation_view_data.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/domain/conversation_dto.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation_membership/application/public/chat_member_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/chat_message_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_view_data.dart';
import 'package:quwoquan_app/runtime/transport/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/runtime/transport/models/cursor_page.dart';
import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';

/// Compatibility shape for the existing Provider override surface.
///
/// Production does not implement this with a mega Remote adapter. The runtime
/// composition delegates each method to an object-scoped repository; local
/// contract tests may still override the aggregate with a test-only double.
abstract interface class ChatRepository
    implements
        ChatInboxRepository,
        ChatConversationRepository,
        ChatMessageRepository,
        ChatMemberRepository,
        ChatContactRepository,
        ChatGroupSelectionRepository,
        ChatGroupAdminRepository {}

final class ComposedChatRepository implements ChatRepository {
  const ComposedChatRepository({
    required ChatInboxRepository inbox,
    required ChatConversationRepository conversation,
    required ChatMessageRepository message,
    required ChatMemberRepository member,
    required ChatContactRepository contact,
    required ChatGroupSelectionRepository groupSelection,
    required ChatGroupAdminRepository groupAdmin,
  }) : _inbox = inbox,
       _conversation = conversation,
       _message = message,
       _member = member,
       _contact = contact,
       _groupSelection = groupSelection,
       _groupAdmin = groupAdmin;

  final ChatInboxRepository _inbox;
  final ChatConversationRepository _conversation;
  final ChatMessageRepository _message;
  final ChatMemberRepository _member;
  final ChatContactRepository _contact;
  final ChatGroupSelectionRepository _groupSelection;
  final ChatGroupAdminRepository _groupAdmin;

  @override
  Future<List<ChatInboxViewData>> listInbox({
    String? cursor,
    int limit = ChatListInboxQuery.defaultLimit,
  }) => _inbox.listInbox(cursor: cursor, limit: limit);

  @override
  Future<List<MessageHomeRow>> listMessageHome({
    String filter = 'all',
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) => _conversation.listMessageHome(
    filter: filter,
    cursor: cursor,
    limit: limit,
  );

  @override
  Future<List<ChatInboxViewData>> listConversations({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) => _conversation.listConversations(cursor: cursor, limit: limit);

  @override
  Future<ChatConversationCreatedViewData> createConversation({
    required String type,
    String? title,
    int? maxGroupSize,
    List<String>? initialMemberIds,
    String? idempotencyKey,
  }) => _conversation.createConversation(
    type: type,
    title: title,
    maxGroupSize: maxGroupSize,
    initialMemberIds: initialMemberIds,
    idempotencyKey: idempotencyKey,
  );

  @override
  Future<ConversationViewData> getConversation(String conversationId) =>
      _conversation.getConversation(conversationId);

  @override
  Future<void> updateConversationTitle(String conversationId, String title) =>
      _conversation.updateConversationTitle(conversationId, title);

  @override
  Future<void> updateConversationSettings({
    required String conversationId,
    bool? muted,
    bool? pinned,
  }) => _conversation.updateConversationSettings(
    conversationId: conversationId,
    muted: muted,
    pinned: pinned,
  );

  @override
  Future<List<ChatConversationTimestamp>> getConversationTimestamps() =>
      _conversation.getConversationTimestamps();

  @override
  Future<List<ConversationViewData>> batchGetConversations(List<String> ids) =>
      _conversation.batchGetConversations(ids);

  @override
  Future<List<ChatMessageViewData>> listMessages({
    required String conversationId,
    String? before,
    int limit = CloudApiDefaults.pageLimit,
  }) => _message.listMessages(
    conversationId: conversationId,
    before: before,
    limit: limit,
  );

  @override
  Future<void> recallMessage({
    required String conversationId,
    required String messageId,
  }) => _message.recallMessage(
    conversationId: conversationId,
    messageId: messageId,
  );

  @override
  Future<ChatMessageSyncViewData> syncMessages({
    required String conversationId,
    required int lastSeq,
    int limit = ChatSyncMessagesQuery.defaultLimit,
  }) => _message.syncMessages(
    conversationId: conversationId,
    lastSeq: lastSeq,
    limit: limit,
  );

  @override
  Future<void> markAsRead({
    required String conversationId,
    required String messageId,
  }) =>
      _message.markAsRead(conversationId: conversationId, messageId: messageId);

  @override
  Future<List<ChatMessageReceipt>> getReceipts({
    required String conversationId,
    required String messageId,
  }) => _message.getReceipts(
    conversationId: conversationId,
    messageId: messageId,
  );

  @override
  Future<List<ConversationMemberListRow>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = ChatListConversationMembersQuery.defaultLimit,
    String? role,
    MemberListSort? sort,
  }) => _member.listMembers(
    conversationId: conversationId,
    cursor: cursor,
    limit: limit,
    role: role,
    sort: sort,
  );

  @override
  Future<List<ConversationMemberListRow>> searchMembers({
    required String conversationId,
    required String query,
    int limit = ChatListConversationMembersQuery.maximumLimit,
  }) => _member.searchMembers(
    conversationId: conversationId,
    query: query,
    limit: limit,
  );

  @override
  Future<void> addMembers({
    required String conversationId,
    required List<String> userIds,
  }) => _member.addMembers(conversationId: conversationId, userIds: userIds);

  @override
  Future<void> removeMember({
    required String conversationId,
    required String userId,
  }) => _member.removeMember(conversationId: conversationId, userId: userId);

  @override
  Future<void> leaveConversation(String conversationId) =>
      _member.leaveConversation(conversationId);

  @override
  Future<List<String>> listMemberUserIds(String conversationId) =>
      _member.listMemberUserIds(conversationId);

  @override
  Future<void> inviteAssistant({required String conversationId}) =>
      _member.inviteAssistant(conversationId: conversationId);

  @override
  Future<void> removeAssistant({required String conversationId}) =>
      _member.removeAssistant(conversationId: conversationId);

  @override
  Future<CursorPage<ChatContactRowViewData>> listContacts({
    String? cursor,
    int limit = ChatListContactsQuery.defaultLimit,
  }) => _contact.listContacts(cursor: cursor, limit: limit);

  @override
  Future<List<ContactHomeRow>> listContactHome({
    String filter = 'all',
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) => _contact.listContactHome(filter: filter, cursor: cursor, limit: limit);

  @override
  Future<List<ChatContactRowViewData>> listGroupCandidates({
    String? conversationId,
    int limit = ChatListGroupCandidatesQuery.defaultLimit,
  }) => _contact.listGroupCandidates(
    conversationId: conversationId,
    limit: limit,
  );

  @override
  Future<CursorPage<SelectableGroupConversationRow>>
  listSelectableGroupConversations({
    String? query,
    ChatSelectableGroupSource source = ChatSelectableGroupSource.all,
    String? cursor,
    int limit = ChatListSelectableGroupConversationsQuery.defaultLimit,
  }) => _groupSelection.listSelectableGroupConversations(
    query: query,
    source: source,
    cursor: cursor,
    limit: limit,
  );

  @override
  Future<CursorPage<ChatContactRowViewData>> listSelectableGroupContactMembers({
    required String conversationId,
    String? query,
    String? cursor,
    int limit = ChatListSelectableGroupContactMembersQuery.defaultLimit,
  }) => _groupSelection.listSelectableGroupContactMembers(
    conversationId: conversationId,
    query: query,
    cursor: cursor,
    limit: limit,
  );

  @override
  Future<ChatGroupSettingsViewData> getGroupSettings(String conversationId) =>
      _groupAdmin.getGroupSettings(conversationId);

  @override
  Future<GroupHome> getGroupHome(String conversationId) =>
      _groupAdmin.getGroupHome(conversationId);

  @override
  Future<void> updateGroupSettings(
    String conversationId,
    ChatGroupSettingsViewData settings, {
    String? idempotencyKey,
  }) => _groupAdmin.updateGroupSettings(
    conversationId,
    settings,
    idempotencyKey: idempotencyKey,
  );

  @override
  Future<void> updateAnnouncement(
    String conversationId,
    String announcement, {
    String? idempotencyKey,
  }) => _groupAdmin.updateAnnouncement(
    conversationId,
    announcement,
    idempotencyKey: idempotencyKey,
  );

  @override
  Future<void> transferOwnership(
    String conversationId,
    String newOwnerId, {
    String? idempotencyKey,
  }) => _groupAdmin.transferOwnership(
    conversationId,
    newOwnerId,
    idempotencyKey: idempotencyKey,
  );

  @override
  Future<void> updateGroupAdmins(
    String conversationId,
    List<String> adminIds, {
    String? idempotencyKey,
  }) => _groupAdmin.updateGroupAdmins(
    conversationId,
    adminIds,
    idempotencyKey: idempotencyKey,
  );

  @override
  Future<void> dissolveConversation(String conversationId) =>
      _groupAdmin.dissolveConversation(conversationId);
}
