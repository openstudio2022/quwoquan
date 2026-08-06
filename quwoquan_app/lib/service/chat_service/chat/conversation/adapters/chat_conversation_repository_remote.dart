// ignore_for_file: prefer_initializing_formals

import 'package:quwoquan_app/service/chat_service/chat/chat_inbox_view/application/public/chat_inbox_view_data.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/chat_conversation_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/conversation_query.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation_user_state/application/public/conversation_user_state_command_writer.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/chat_conversation_view_data.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/domain/conversation_dto.dart';
import 'package:quwoquan_app/runtime/transport/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/runtime/transport/models/cursor_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:uuid/uuid.dart';

/// Conversation-owned App facade. Generated object ports own transport and
/// decoding; this adapter only maps explicit App view state and coordinates the
/// conversation governance surface.
final class RemoteChatConversationRepository
    implements
        ChatConversationRepository,
        ChatContactRepository,
        ChatGroupSelectionRepository,
        ChatGroupAdminRepository {
  RemoteChatConversationRepository({
    required ConversationQuery conversationQuery,
    required ChatConversationCommandWriter conversationCommandWriter,
    required ChatContactQuery contactQuery,
    required ChatMessageHomeQuery messageHomeQuery,
    required ChatConversationMembershipCommandWriter membershipCommandWriter,
    required ConversationUserStateCommandWriter userStateCommandWriter,
    ConversationQuery? settingsConversationQuery,
    String Function()? idempotencyKeyFactory,
  }) : _conversationQuery = conversationQuery,
       _settingsConversationQuery =
           settingsConversationQuery ?? conversationQuery,
       _conversationCommandWriter = conversationCommandWriter,
       _contactQuery = contactQuery,
       _messageHomeQuery = messageHomeQuery,
       _membershipCommandWriter = membershipCommandWriter,
       _userStateCommandWriter = userStateCommandWriter,
       _idempotencyKeyFactory = idempotencyKeyFactory ?? const Uuid().v4;

  final ConversationQuery _conversationQuery;
  final ConversationQuery _settingsConversationQuery;
  final ChatConversationCommandWriter _conversationCommandWriter;
  final ChatContactQuery _contactQuery;
  final ChatMessageHomeQuery _messageHomeQuery;
  final ChatConversationMembershipCommandWriter _membershipCommandWriter;
  final ConversationUserStateCommandWriter _userStateCommandWriter;
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
    return page.items
        .map(ChatInboxViewData.fromConversation)
        .toList(growable: false);
  }

  @override
  Future<ChatConversationCreatedViewData> createConversation({
    required String type,
    String? title,
    int? maxGroupSize,
    List<String>? initialMemberIds,
    String? idempotencyKey,
  }) async {
    final conversation = await _conversationCommandWriter.createConversation(
      ChatCreateConversationCommand(
        type: type,
        title: title,
        maxGroupSize: maxGroupSize,
        initialMemberIds: initialMemberIds ?? const <String>[],
      ),
      idempotencyKey: _resolveIdempotencyKey(idempotencyKey),
    );
    return ChatConversationCreatedViewData.fromWire(conversation);
  }

  @override
  Future<ConversationViewData> getConversation(String conversationId) async {
    final conversation = await _conversationQuery.getConversation(
      ChatGetConversationQuery(conversationId: conversationId),
    );
    return ConversationViewData.fromWire(conversation);
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

  @override
  Future<List<ChatConversationTimestamp>> getConversationTimestamps() async {
    final page = await _conversationQuery.listConversationTimestamps(
      ChatListConversationTimestampsQuery(),
    );
    return page.items;
  }

  @override
  Future<List<ConversationViewData>> batchGetConversations(
    List<String> ids,
  ) async {
    final page = await _conversationQuery.batchGetConversations(
      ChatBatchGetConversationsQuery(conversationIds: ids),
    );
    return page.items
        .map(ConversationViewData.fromWire)
        .toList(growable: false);
  }

  @override
  Future<CursorPage<ChatContactRowViewData>> listContacts({
    String? cursor,
    int limit = ChatListContactsQuery.defaultLimit,
  }) async {
    final page = await _contactQuery.listContacts(
      ChatListContactsQuery(cursor: cursor, limit: limit),
    );
    return CursorPage<ChatContactRowViewData>(
      items: page.items
          .map(ChatContactRowViewData.fromWire)
          .toList(growable: false),
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
    int limit = ChatListGroupCandidatesQuery.defaultLimit,
  }) async {
    final page = await _contactQuery.listGroupCandidates(
      ChatListGroupCandidatesQuery(
        conversationId: conversationId,
        limit: limit,
      ),
    );
    return page.items.map(_groupCandidateToContact).toList(growable: false);
  }

  @override
  Future<CursorPage<SelectableGroupConversationRow>>
  listSelectableGroupConversations({
    String? query,
    ChatSelectableGroupSource source = ChatSelectableGroupSource.all,
    String? cursor,
    int limit = ChatListSelectableGroupConversationsQuery.defaultLimit,
  }) async {
    final page = await _contactQuery.listSelectableGroupConversations(
      ChatListSelectableGroupConversationsQuery(
        query: query,
        source: switch (source) {
          ChatSelectableGroupSource.all => null,
          ChatSelectableGroupSource.group =>
            SelectableGroupConversationSource.group,
          ChatSelectableGroupSource.circle =>
            SelectableGroupConversationSource.circle,
        },
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
    int limit = ChatListSelectableGroupContactMembersQuery.defaultLimit,
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
          .map(_selectableContactToContact)
          .toList(growable: false),
      nextCursor: page.nextCursor,
    );
  }

  @override
  Future<ChatGroupSettingsViewData> getGroupSettings(
    String conversationId,
  ) async {
    final conversation = await _settingsConversationQuery.getConversation(
      ChatGetConversationQuery(conversationId: conversationId),
    );
    return ChatGroupSettingsViewData.fromWire(conversation);
  }

  @override
  Future<GroupHome> getGroupHome(String conversationId) {
    return _conversationQuery.getGroupHome(
      ChatGetGroupHomeQuery(conversationId: conversationId),
    );
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

ChatContactRowViewData _groupCandidateToContact(GroupCandidateRow item) {
  return ChatContactRowViewData(
    userId: item.userId,
    userHandle: item.userHandle,
    displayName: item.displayName,
    avatarUrl: item.avatarUrl,
    bio: item.bio,
    metFrom: item.metFrom,
    lastInteraction: item.lastInteraction,
    relationState: item.relationState.wireName,
    source: item.source.wireName,
    isStarred: item.isStarred,
  );
}

ChatContactRowViewData _selectableContactToContact(
  SelectableGroupContactMemberRow item,
) {
  return ChatContactRowViewData(
    userId: item.userId,
    userHandle: item.userHandle,
    displayName: item.displayName,
    avatarUrl: item.avatarUrl,
    relationState: item.relationState.wireName,
    source: item.source.wireName,
  );
}
