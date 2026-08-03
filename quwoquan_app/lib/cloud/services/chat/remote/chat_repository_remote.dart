import "package:quwoquan_app/cloud/services/chat/chat_view_data.dart";
// ignore_for_file: prefer_initializing_formals

import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/chat/models/chat_conversation_timestamp_dto.dart';
import 'package:quwoquan_app/cloud/chat/models/chat_message_receipt_dto.dart';
import 'package:quwoquan_app/cloud/chat/models/conversation_dto.dart';
import 'package:quwoquan_app/cloud/chat/models/message_dto.dart';
import 'package:quwoquan_app/cloud/chat/models/sync_response.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository_api.dart';
import 'package:quwoquan_app/cloud/services/chat/remote/chat_contract_projection_mapper.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:uuid/uuid.dart';

class RemoteChatRepository implements ChatRepository {
  RemoteChatRepository({
    required ChatConversationQuery conversationQuery,
    required ChatConversationCommandWriter conversationCommandWriter,
    required ChatContactQuery contactQuery,
    required ChatInboxQuery inboxQuery,
    required ChatMessageHomeQuery messageHomeQuery,
    required ChatConversationMembershipQuery membershipQuery,
    required ChatConversationMembershipCommandWriter membershipCommandWriter,
    required ChatConversationUserStateCommandWriter userStateCommandWriter,
    required ChatMessageQuery messageQuery,
    required ChatMessageMutationWriter messageMutationWriter,
    ChatConversationQuery? settingsConversationQuery,
    ChatConversationMembershipQuery? memberSearchQuery,
    String Function()? idempotencyKeyFactory,
    ChatContractProjectionMapper mapper = const ChatContractProjectionMapper(),
  }) : _conversationQuery = conversationQuery,
       _settingsConversationQuery =
           settingsConversationQuery ?? conversationQuery,
       _conversationCommandWriter = conversationCommandWriter,
       _contactQuery = contactQuery,
       _inboxQuery = inboxQuery,
       _messageHomeQuery = messageHomeQuery,
       _membershipQuery = membershipQuery,
       _memberSearchQuery = memberSearchQuery ?? membershipQuery,
       _membershipCommandWriter = membershipCommandWriter,
       _userStateCommandWriter = userStateCommandWriter,
       _messageQuery = messageQuery,
       _messageMutationWriter = messageMutationWriter,
       _mapper = mapper,
       _idempotencyKeyFactory = idempotencyKeyFactory ?? const Uuid().v4;

  final ChatConversationQuery _conversationQuery;
  final ChatConversationQuery _settingsConversationQuery;
  final ChatConversationCommandWriter _conversationCommandWriter;
  final ChatContactQuery _contactQuery;
  final ChatInboxQuery _inboxQuery;
  final ChatMessageHomeQuery _messageHomeQuery;
  final ChatConversationMembershipQuery _membershipQuery;
  final ChatConversationMembershipQuery _memberSearchQuery;
  final ChatConversationMembershipCommandWriter _membershipCommandWriter;
  final ChatConversationUserStateCommandWriter _userStateCommandWriter;
  final ChatMessageQuery _messageQuery;
  final ChatMessageMutationWriter _messageMutationWriter;
  final ChatContractProjectionMapper _mapper;
  final String Function() _idempotencyKeyFactory;

  String _resolveIdempotencyKey(String? supplied) {
    final candidate = supplied ?? _idempotencyKeyFactory();
    final normalized = candidate.trim();
    if (normalized.isEmpty) {
      throw ArgumentError.value(
        candidate,
        'idempotencyKey',
        'must not be blank',
      );
    }
    return normalized;
  }

  // ── 会话 ──────────────────────────────────────────────────────────────────

  @override
  Future<List<ChatInboxViewData>> listInbox({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final page = await _inboxQuery.listInbox(
      ChatListInboxQuery(cursor: cursor, limit: limit),
    );
    return page.items.map(_mapper.toInbox).toList(growable: false);
  }

  @override
  Future<List<MessageHomeRow>> listMessageHome({
    String filter = 'all',
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final page = await _messageHomeQuery.listMessageHome(
      ChatListMessageHomeQuery(filter: filter, cursor: cursor, limit: limit),
    );
    return page.items;
  }

  @override
  Future<List<ChatInboxViewData>> listConversations({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final page = await _conversationQuery.listConversations(
      ChatListConversationsQuery(cursor: cursor, limit: limit),
    );
    return page.items.map(_mapper.conversationToInbox).toList(growable: false);
  }

  @override
  Future<ChatConversationCreatedViewData> createConversation({
    required String type,
    String? title,
    int? maxGroupSize,
    List<String>? initialMemberIds,
    String? idempotencyKey,
  }) async {
    final commandIdempotencyKey = _resolveIdempotencyKey(idempotencyKey);
    final conversation = await _conversationCommandWriter.createConversation(
      ChatCreateConversationCommand(
        type: type,
        title: title,
        maxGroupSize: maxGroupSize,
        initialMemberIds: initialMemberIds ?? const <String>[],
      ),
      idempotencyKey: commandIdempotencyKey,
    );
    return _mapper.toCreated(conversation);
  }

  @override
  Future<ConversationViewData> getConversation(String conversationId) async {
    final conversation = await _conversationQuery.getConversation(
      ChatGetConversationQuery(conversationId: conversationId),
    );
    return _mapper.toConversation(conversation);
  }

  @override
  Future<void> updateConversationTitle(
    String conversationId,
    String title,
  ) async {
    await _conversationCommandWriter.updateConversationTitle(
      ChatUpdateConversationTitleCommand(
        conversationId: conversationId,
        title: title,
      ),
      idempotencyKey: _resolveIdempotencyKey(null),
    );
  }

  // ── 消息 ──────────────────────────────────────────────────────────────────

  @override
  Future<List<ChatMessageViewData>> listMessages({
    required String conversationId,
    String? before,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final normalizedBefore = before?.trim() ?? '';
    final beforeSeq = normalizedBefore.isEmpty
        ? null
        : int.tryParse(normalizedBefore);
    if (normalizedBefore.isNotEmpty && beforeSeq == null) {
      throw ArgumentError.value(before, 'before', 'must be a message sequence');
    }
    final page = await _messageQuery.listMessages(
      ChatListMessagesQuery(
        conversationId: conversationId,
        beforeSeq: beforeSeq,
        limit: limit,
      ),
    );
    return page.items.map(ChatMessageViewData.fromWire).toList(growable: false);
  }

  @override
  Future<void> recallMessage({
    required String conversationId,
    required String messageId,
  }) async {
    await _messageMutationWriter.recallMessage(
      ChatRecallMessageCommand(
        conversationId: conversationId,
        messageId: messageId,
      ),
      idempotencyKey: _resolveIdempotencyKey(null),
    );
  }

  @override
  Future<SyncResponse> syncMessages({
    required String conversationId,
    required int lastSeq,
    int limit = CloudApiDefaults.syncMessagesLimit,
  }) async {
    final slice = await _messageQuery.syncMessages(
      ChatSyncMessagesQuery(
        conversationId: conversationId,
        lastSeq: lastSeq,
        limit: limit,
      ),
    );
    return _mapper.toSyncResponse(slice);
  }

  // ── 已读回执 ──────────────────────────────────────────────────────────────

  @override
  Future<void> markAsRead({
    required String conversationId,
    required String messageId,
  }) async {
    await _userStateCommandWriter.markMessageRead(
      ChatMarkConversationMessageReadCommand(
        conversationId: conversationId,
        messageId: messageId,
      ),
      idempotencyKey: _resolveIdempotencyKey(null),
    );
  }

  @override
  Future<List<ChatMessageReceiptDto>> getReceipts({
    required String conversationId,
    required String messageId,
  }) async {
    final page = await _conversationQuery.getMessageReceipts(
      ChatGetMessageReceiptsQuery(
        conversationId: conversationId,
        messageId: messageId,
      ),
    );
    return page.items.map(_mapper.toReceipt).toList(growable: false);
  }

  // ── 成员管理 ──────────────────────────────────────────────────────────────

  @override
  Future<List<ConversationMemberListRow>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
    String? role,
    String? sort,
  }) async {
    final page = await _membershipQuery.listMembers(
      ChatListConversationMembersQuery(
        conversationId: conversationId,
        cursor: cursor,
        limit: limit,
        role: role,
        sort: sort ?? 'joined_asc',
      ),
    );
    return page.items;
  }

  @override
  Future<List<ConversationMemberListRow>> searchMembers({
    required String conversationId,
    required String query,
    int limit = CloudApiDefaults.chatMemberSearchLimit,
  }) async {
    final page = await _memberSearchQuery.listMembers(
      ChatListConversationMembersQuery(
        conversationId: conversationId,
        query: query.trim(),
        limit: limit.clamp(1, CloudApiDefaults.chatMemberSearchLimit),
        sort: 'display_name_asc',
      ),
    );
    return page.items;
  }

  @override
  Future<void> addMembers({
    required String conversationId,
    required List<String> userIds,
  }) async {
    await _membershipCommandWriter.addMembers(
      ChatAddConversationMembersCommand(
        conversationId: conversationId,
        userIds: userIds,
      ),
      idempotencyKey: _resolveIdempotencyKey(null),
    );
  }

  @override
  Future<void> leaveConversation(String conversationId) async {
    await _membershipCommandWriter.leaveConversation(
      ChatLeaveConversationCommand(conversationId: conversationId),
      idempotencyKey: _resolveIdempotencyKey(null),
    );
  }

  @override
  Future<void> removeMember({
    required String conversationId,
    required String userId,
  }) async {
    await _membershipCommandWriter.removeMember(
      ChatRemoveConversationMemberCommand(
        conversationId: conversationId,
        userId: userId,
      ),
      idempotencyKey: _resolveIdempotencyKey(null),
    );
  }

  // ── 助手 ──────────────────────────────────────────────────────────────────

  @override
  Future<void> inviteAssistant({required String conversationId}) async {
    await _membershipCommandWriter.inviteAssistant(
      ChatInviteConversationAssistantCommand(conversationId: conversationId),
      idempotencyKey: _resolveIdempotencyKey(null),
    );
  }

  @override
  Future<void> removeAssistant({required String conversationId}) async {
    await _membershipCommandWriter.removeAssistant(
      ChatRemoveConversationAssistantCommand(conversationId: conversationId),
      idempotencyKey: _resolveIdempotencyKey(null),
    );
  }

  // ── 设置 ──────────────────────────────────────────────────────────────────

  @override
  Future<void> updateConversationSettings({
    required String conversationId,
    bool? muted,
    bool? pinned,
  }) async {
    await _userStateCommandWriter.updateConversationSettings(
      ChatUpdateConversationSettingsCommand(
        conversationId: conversationId,
        muted: muted,
        pinned: pinned,
      ),
      idempotencyKey: _resolveIdempotencyKey(null),
    );
  }

  // ── 联系人 ──────────────────────────────────────────────────────────────

  @override
  Future<CursorPage<ChatContactRowViewData>> listContacts({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final page = await _contactQuery.listContacts(
      ChatListContactsQuery(cursor: cursor, limit: limit),
    );
    return CursorPage<ChatContactRowViewData>(
      items: page.items.map(_mapper.toContact).toList(growable: false),
      nextCursor: page.nextCursor,
    );
  }

  @override
  Future<List<ContactHomeRow>> listContactHome({
    String filter = 'all',
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    if ((cursor?.trim() ?? '').isNotEmpty) {
      throw ArgumentError.value(
        cursor,
        'cursor',
        'ListContactHome canonical contract does not support cursor',
      );
    }
    final page = await _contactQuery.listContactHome(
      ChatListContactHomeQuery(filter: filter, limit: limit),
    );
    return page.items;
  }

  @override
  Future<List<ChatContactRowViewData>> listGroupCandidates({
    String? conversationId,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final page = await _contactQuery.listGroupCandidates(
      ChatListGroupCandidatesQuery(
        conversationId: conversationId,
        limit: limit,
      ),
    );
    return page.items
        .map(_mapper.groupCandidateToContact)
        .toList(growable: false);
  }

  // ── 从群聊/圈子中选择联系人 ─────────────────────────────────────────────────

  @override
  Future<CursorPage<SelectableGroupConversationRow>>
  listSelectableGroupConversations({
    String? query,
    ChatSelectableGroupSource source = ChatSelectableGroupSource.all,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final page = await _contactQuery.listSelectableGroupConversations(
      ChatListSelectableGroupConversationsQuery(
        query: query,
        source: source.wireValue,
        cursor: cursor,
        limit: limit,
      ),
    );
    return CursorPage<SelectableGroupConversationRow>(
      items: page.items,
      nextCursor: page.nextCursor,
    );
  }

  @override
  Future<CursorPage<ChatContactRowViewData>> listSelectableGroupContactMembers({
    required String conversationId,
    String? query,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final page = await _contactQuery.listSelectableGroupContactMembers(
      ChatListSelectableGroupContactMembersQuery(
        conversationId: conversationId,
        query: query,
        cursor: cursor,
        limit: limit,
      ),
    );
    return CursorPage<ChatContactRowViewData>(
      items: page.items
          .map(_mapper.selectableContactToContact)
          .toList(growable: false),
      nextCursor: page.nextCursor,
    );
  }

  @override
  Future<List<String>> listMemberUserIds(String conversationId) async {
    final members = await listMembers(
      conversationId: conversationId,
      limit: 500,
    );
    return members
        .map((m) => m.userId)
        .where((id) => id.isNotEmpty)
        .toList(growable: false);
  }

  // ── 会话时间戳索引 ──────────────────────────────────────────────────────────

  @override
  Future<List<ChatConversationTimestampDto>> getConversationTimestamps() async {
    final page = await _conversationQuery.listConversationTimestamps(
      ChatListConversationTimestampsQuery(),
    );
    return page.items.map(_mapper.toTimestamp).toList(growable: false);
  }

  @override
  Future<List<ConversationViewData>> batchGetConversations(
    List<String> ids,
  ) async {
    final page = await _conversationQuery.batchGetConversations(
      ChatBatchGetConversationsQuery(conversationIds: ids),
    );
    return page.items.map(_mapper.toConversation).toList(growable: false);
  }

  // ── 群管理 ──────────────────────────────────────────────────────────────────

  @override
  Future<ChatGroupSettingsViewData> getGroupSettings(
    String conversationId,
  ) async {
    final conversation = await _settingsConversationQuery.getConversation(
      ChatGetConversationQuery(conversationId: conversationId),
    );
    return _mapper.toGroupSettings(conversation);
  }

  @override
  Future<GroupHome> getGroupHome(String conversationId) async {
    final home = await _conversationQuery.getGroupHome(
      ChatGetGroupHomeQuery(conversationId: conversationId),
    );
    return home;
  }

  @override
  Future<void> updateGroupSettings(
    String conversationId,
    ChatGroupSettingsViewData settings,
  ) async {
    await _conversationCommandWriter.updateGroupGovernanceSettings(
      ChatUpdateGroupGovernanceSettingsCommand(
        conversationId: conversationId,
        nameEditableByAdminOnly: settings.nameEditableByAdminOnly,
      ),
      idempotencyKey: _resolveIdempotencyKey(null),
    );
  }

  @override
  Future<void> updateAnnouncement(
    String conversationId,
    String announcement,
  ) async {
    await _conversationCommandWriter.updateAnnouncement(
      ChatUpdateAnnouncementCommand(
        conversationId: conversationId,
        announcement: announcement,
      ),
      idempotencyKey: _resolveIdempotencyKey(null),
    );
  }

  @override
  Future<void> transferOwnership(
    String conversationId,
    String newOwnerId,
  ) async {
    await _membershipCommandWriter.transferOwnership(
      ChatTransferConversationOwnershipCommand(
        conversationId: conversationId,
        newOwnerId: newOwnerId,
      ),
      idempotencyKey: _resolveIdempotencyKey(null),
    );
  }

  @override
  Future<void> updateGroupAdmins(
    String conversationId,
    List<String> adminIds,
  ) async {
    await _membershipCommandWriter.updateAdmins(
      ChatUpdateConversationAdminsCommand(
        conversationId: conversationId,
        adminIds: adminIds,
      ),
      idempotencyKey: _resolveIdempotencyKey(null),
    );
  }

  @override
  Future<void> dissolveConversation(String conversationId) async {
    await _conversationCommandWriter.dissolveConversation(
      ChatDissolveConversationCommand(conversationId: conversationId),
      idempotencyKey: _resolveIdempotencyKey(null),
    );
  }
}
