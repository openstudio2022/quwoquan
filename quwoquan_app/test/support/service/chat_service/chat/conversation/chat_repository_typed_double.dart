// Test-only ChatRepository double. Production and all App environments use Remote.
import 'package:quwoquan_app/service/chat_service/chat/conversation/domain/conversation_dto.dart';
import 'package:quwoquan_app/service/chat_service/chat/chat_inbox_view/application/public/chat_inbox_view_data.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/chat_conversation_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/chat_conversation_view_data.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_view_data.dart';
import 'package:quwoquan_app/runtime/transport/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/runtime/transport/models/cursor_page.dart';
import 'package:quwoquan_app/runtime/di/chat_repository_facade.dart';
import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';

import 'conversation_state_typed_double.dart';

/// local_contract 专用 App DTO 薄适配器。
///
/// 所有 fixture/state 行为都委托给 pure Dart [InMemoryChatStateEngine]；
/// 此类只承担 `quwoquan_app` DTO 映射，不持有第二份 chat 状态。
class MockChatRepository implements ChatRepository {
  MockChatRepository({
    InMemoryChatStateEngine? engine,
    List<Map<String, dynamic>>? seedConversations,
    Map<String, List<Map<String, dynamic>>>? seedMembers,
    Map<String, List<Map<String, dynamic>>>? seedMessages,
  }) : _engine = _resolveEngine(
         engine: engine,
         seedConversations: seedConversations,
         seedMembers: seedMembers,
         seedMessages: seedMessages,
       );

  final InMemoryChatStateEngine _engine;

  @override
  Future<List<ChatInboxViewData>> listInbox({
    String? cursor,
    int limit = ChatListInboxQuery.defaultLimit,
  }) async => _engine
      .listInbox(limit: limit)
      .map(_chatInboxItem)
      .map(ChatInboxViewData.fromWire)
      .toList(growable: false);

  @override
  Future<List<MessageHomeRow>> listMessageHome({
    String filter = 'all',
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async => _engine
      .listMessageHome(filter: filter, limit: limit)
      .map((row) => MessageHomeRow.fromWire(_appMap(row)))
      .toList(growable: false);

  @override
  Future<List<ChatInboxViewData>> listConversations({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async => _engine
      .listConversations(limit: limit)
      .map(_chatInboxItem)
      .map(ChatInboxViewData.fromWire)
      .toList(growable: false);

  @override
  Future<ChatConversationCreatedViewData> createConversation({
    required String type,
    String? title,
    int? maxGroupSize,
    List<String>? initialMemberIds,
    String? idempotencyKey,
  }) async {
    final result = _engine.createConversation(
      type: type,
      title: title,
      maxGroupSize: maxGroupSize,
      initialMemberIds: initialMemberIds,
    );
    return ChatConversationCreatedViewData(
      conversationId: _textValue(result['conversationId']),
    );
  }

  @override
  Future<ConversationViewData> getConversation(String conversationId) async =>
      ConversationViewData.fromWire(
        _chatConversation(_engine.getConversation(conversationId)),
      );

  @override
  Future<void> updateConversationTitle(
    String conversationId,
    String title,
  ) async => _engine.updateConversationTitle(conversationId, title);

  @override
  Future<void> updateConversationSettings({
    required String conversationId,
    bool? muted,
    bool? pinned,
  }) async => _engine.updateConversationSettings(
    conversationId: conversationId,
    muted: muted,
    pinned: pinned,
  );

  @override
  Future<List<ChatMessageViewData>> listMessages({
    required String conversationId,
    String? before,
    int limit = CloudApiDefaults.pageLimit,
  }) async => _engine
      .listMessages(
        conversationId: conversationId,
        before: before,
        limit: limit,
      )
      .map((row) => ChatMessageView.fromWire(_appMap(row)))
      .map(ChatMessageViewData.fromWire)
      .toList(growable: false);

  @override
  Future<void> recallMessage({
    required String conversationId,
    required String messageId,
  }) async => _engine.recallMessage(
    conversationId: conversationId,
    messageId: messageId,
  );

  @override
  Future<ChatMessageSyncViewData> syncMessages({
    required String conversationId,
    required int lastSeq,
    int limit = ChatSyncMessagesQuery.defaultLimit,
  }) async {
    final page = _engine.syncMessages(
      conversationId: conversationId,
      lastSeq: lastSeq,
      limit: limit,
    );
    return ChatMessageSyncViewData(
      messages: page.messages
          .map((row) => ChatMessageView.fromWire(_appMap(row)))
          .map(ChatMessageViewData.fromWire)
          .toList(growable: false),
      hasMore: page.hasMore,
    );
  }

  @override
  Future<void> markAsRead({
    required String conversationId,
    required String messageId,
  }) async =>
      _engine.markAsRead(conversationId: conversationId, messageId: messageId);

  @override
  Future<List<ChatMessageReceipt>> getReceipts({
    required String conversationId,
    required String messageId,
  }) async => _engine
      .getReceipts(conversationId: conversationId, messageId: messageId)
      .map((row) => ChatMessageReceipt.fromWire(_appMap(row)))
      .toList(growable: false);

  @override
  Future<List<ConversationMemberListRow>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = ChatListConversationMembersQuery.defaultLimit,
    String? role,
    String? sort,
  }) async => _engine
      .listMembers(
        conversationId: conversationId,
        limit: limit,
        role: role,
        sort: sort,
      )
      .map(_conversationMember)
      .toList(growable: false);

  @override
  Future<List<ConversationMemberListRow>> searchMembers({
    required String conversationId,
    required String query,
    int limit = ChatListConversationMembersQuery.maximumLimit,
  }) async => _engine
      .listMembers(
        conversationId: conversationId,
        limit: limit.clamp(1, ChatListConversationMembersQuery.maximumLimit),
        query: query,
        sort: 'display_name_asc',
      )
      .map(_conversationMember)
      .toList(growable: false);

  @override
  Future<void> addMembers({
    required String conversationId,
    required List<String> userIds,
  }) async =>
      _engine.addMembers(conversationId: conversationId, userIds: userIds);

  @override
  Future<void> removeMember({
    required String conversationId,
    required String userId,
  }) async =>
      _engine.removeMember(conversationId: conversationId, userId: userId);

  @override
  Future<void> leaveConversation(String conversationId) async =>
      _engine.leaveConversation(conversationId);

  @override
  Future<List<String>> listMemberUserIds(String conversationId) async =>
      _engine.listMemberUserIds(conversationId);

  @override
  Future<void> inviteAssistant({required String conversationId}) async =>
      _engine.inviteAssistant(conversationId: conversationId);

  @override
  Future<void> removeAssistant({required String conversationId}) async =>
      _engine.removeAssistant(conversationId: conversationId);

  @override
  Future<CursorPage<ChatContactRowViewData>> listContacts({
    String? cursor,
    int limit = ChatListContactsQuery.defaultLimit,
  }) async {
    final page = _engine.listContacts(cursor: cursor, limit: limit);
    return CursorPage<ChatContactRowViewData>(
      items: page.items.map(_chatContactView).toList(growable: false),
      nextCursor: page.nextCursor,
    );
  }

  @override
  Future<List<ContactHomeRow>> listContactHome({
    String filter = 'all',
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async => _engine
      .listContactHome(filter: filter, limit: limit)
      .map(_contactHomeRow)
      .toList(growable: false);

  @override
  Future<List<ChatContactRowViewData>> listGroupCandidates({
    String? conversationId,
    int limit = ChatListGroupCandidatesQuery.defaultLimit,
  }) async => _engine
      .listGroupCandidates(conversationId: conversationId, limit: limit)
      .map(_chatContactView)
      .toList(growable: false);

  @override
  Future<CursorPage<SelectableGroupConversationRow>>
  listSelectableGroupConversations({
    String? query,
    ChatSelectableGroupSource source = ChatSelectableGroupSource.all,
    String? cursor,
    int limit = ChatListSelectableGroupConversationsQuery.defaultLimit,
  }) async {
    final page = _engine.listSelectableGroupConversations(
      query: query,
      source: source.wireValue,
      cursor: cursor,
      limit: limit,
    );
    return CursorPage<SelectableGroupConversationRow>(
      items: page.items
          .map((row) => SelectableGroupConversationRow.fromWire(_appMap(row)))
          .toList(growable: false),
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
    final page = _engine.listSelectableGroupContactMembers(
      conversationId: conversationId,
      query: query,
      cursor: cursor,
      limit: limit,
    );
    return CursorPage<ChatContactRowViewData>(
      items: page.items.map(_chatContactView).toList(growable: false),
      nextCursor: page.nextCursor,
    );
  }

  @override
  Future<List<ChatConversationTimestamp>> getConversationTimestamps() async =>
      _engine
          .getConversationTimestamps()
          .map((row) => ChatConversationTimestamp.fromWire(_appMap(row)))
          .toList(growable: false);

  @override
  Future<List<ConversationViewData>> batchGetConversations(
    List<String> ids,
  ) async => _engine
      .batchGetConversations(ids)
      .map(_chatConversation)
      .map(ConversationViewData.fromWire)
      .toList(growable: false);

  @override
  Future<ChatGroupSettingsViewData> getGroupSettings(
    String conversationId,
  ) async {
    final row = _engine.getGroupSettings(conversationId);
    return ChatGroupSettingsViewData(
      nameEditableByAdminOnly: row['nameEditableByAdminOnly'] == true,
      conversationType: _textValue(row['conversationType']),
      circleId: _textValue(row['circleId']),
      circleGroupId: _textValue(row['circleGroupId']),
    );
  }

  @override
  Future<GroupHome> getGroupHome(String conversationId) async =>
      GroupHome.fromWire(_appMap(_engine.getGroupHome(conversationId)));

  @override
  Future<void> updateGroupSettings(
    String conversationId,
    ChatGroupSettingsViewData settings,
  ) async => _engine.updateGroupSettings(conversationId, <String, Object?>{
    'nameEditableByAdminOnly': settings.nameEditableByAdminOnly,
    'conversationType': settings.conversationType,
    'circleId': settings.circleId,
    'circleGroupId': settings.circleGroupId,
  });

  @override
  Future<void> updateAnnouncement(
    String conversationId,
    String announcement,
  ) async => _engine.updateAnnouncement(conversationId, announcement);

  @override
  Future<void> transferOwnership(
    String conversationId,
    String newOwnerId,
  ) async => _engine.transferOwnership(conversationId, newOwnerId);

  @override
  Future<void> updateGroupAdmins(
    String conversationId,
    List<String> adminIds,
  ) async => _engine.updateGroupAdmins(conversationId, adminIds);

  @override
  Future<void> dissolveConversation(String conversationId) async =>
      _engine.dissolveConversation(conversationId);
}

Map<String, dynamic> _appMap(ChatFixtureObject row) =>
    Map<String, dynamic>.from(row);

ChatInboxItemView _chatInboxItem(ChatFixtureObject row) => ChatInboxItemView(
  id: _textValue(row['id']),
  type: _textValue(row['type']),
  title: _textValue(row['title']),
  avatarUrl: _textValue(row['avatarUrl']),
  groupAvatarVersion: _intValue(row['groupAvatarVersion']),
  lastMessagePreview: _textValue(row['lastMessagePreview']),
  lastMessageType: MessageType.fromWire(
    row['lastMessageType'],
    'ChatInboxItemView.lastMessageType',
  ),
  lastMessageTime: _requiredDate(row['lastMessageTime']),
  lastSeq: _intValue(row['lastSeq']),
  unreadCount: _intValue(row['unreadCount']),
  mentionUnreadCount: _intValue(row['mentionUnreadCount']),
  muted: row['muted'] == true,
  pinned: row['pinned'] == true,
  circleId: _optionalText(row['circleId']),
);

ChatConversation _chatConversation(ChatFixtureObject row) {
  final now = DateTime.utc(2026, 7, 20);
  final id = _textValue(row['id']);
  final updatedAt = _optionalDate(row['updatedAt']) ?? now;
  return ChatConversation(
    id: id,
    conversationId: _optionalText(row['conversationId']) ?? id,
    type: _textValue(row['type']),
    title: _textValue(row['title']),
    avatarUrl: _textValue(row['avatarUrl']),
    groupAvatarVersion: _intValue(row['groupAvatarVersion']),
    creatorId: _textValue(row['creatorId']),
    circleId: _textValue(row['circleId']),
    circleGroupId: _textValue(row['circleGroupId']),
    gatheringId: _textValue(row['gatheringId']),
    gatheringSourceVersion: _intValue(row['gatheringSourceVersion']),
    accessMode: ConversationAccessMode.fromWire(
      row['accessMode'] ?? 'active',
      'ChatConversation.accessMode',
    ),
    postingPolicy: ConversationPostingPolicy.fromWire(
      row['postingPolicy'] ?? 'member_chat',
      'ChatConversation.postingPolicy',
    ),
    entityId: _textValue(row['entityId']),
    originType: _textValue(row['originType'], fallback: 'direct_init'),
    maxSeq: _intValue(row['maxSeq']),
    memberCount: _intValue(row['memberCount']),
    membersRosterRevision: _intValue(row['membersRosterRevision'], fallback: 1),
    maxGroupSize: _intValue(row['maxGroupSize'], fallback: 1000),
    receiptEnabled: row['receiptEnabled'] != false,
    announcement: _textValue(row['announcement']),
    announcementUpdatedBy: _textValue(row['announcementUpdatedBy']),
    announcementUpdatedAt:
        _optionalDate(row['announcementUpdatedAt']) ?? updatedAt,
    nameEditableByAdminOnly: row['nameEditableByAdminOnly'] == true,
    lastMessageId: _textValue(row['lastMessageId']),
    lastMessagePreview: _textValue(row['lastMessagePreview']),
    lastMessageType: MessageType.fromWire(
      row['lastMessageType'] ?? 'text',
      'ChatConversation.lastMessageType',
    ),
    lastMessageTime: _optionalDate(row['lastMessageTime']) ?? updatedAt,
    messageCount: _intValue(row['messageCount']),
    status: _textValue(row['status'], fallback: 'active'),
    createdAt: _optionalDate(row['createdAt']) ?? now,
    updatedAt: updatedAt,
  );
}

ChatContactRowViewData _chatContactView(ChatFixtureObject row) =>
    ChatContactRowViewData(
      userId: _textValue(row['userId']),
      userHandle: _textValue(row['userHandle']),
      displayName: _textValue(row['displayName']),
      avatarUrl: _textValue(row['avatarUrl']),
      bio: _textValue(row['bio']),
      metFrom: _textValue(row['metFrom']),
      lastInteraction: _textValue(row['lastInteraction']),
      relationState: _textValue(
        row['relationState'],
        fallback: 'not_following',
      ),
      source: _textValue(row['source']),
      isStarred: row['isStarred'] == true,
    );

ConversationMemberListRow _conversationMember(ChatFixtureObject row) =>
    ConversationMemberListRow(
      userId: _textValue(row['userId']),
      userHandle: _textValue(row['userHandle']),
      displayName: _textValue(row['displayName']),
      avatarUrl: _textValue(row['avatarUrl']),
      role: _textValue(row['role'], fallback: 'member'),
      memberType: _textValue(row['memberType'], fallback: 'user'),
      joinedAt: _optionalDate(row['joinedAt']),
      isCurrentUser: row['isCurrentUser'] == true,
    );

ContactHomeRow _contactHomeRow(ChatFixtureObject row) => ContactHomeRow(
  id: _textValue(row['id']),
  kind: _textValue(row['kind']),
  objectId: _textValue(row['objectId']),
  userId: _optionalText(row['userId']),
  userHandle: _textValue(row['userHandle']),
  conversationId: _optionalText(row['conversationId']),
  circleId: _optionalText(row['circleId']),
  circleGroupId: _optionalText(row['circleGroupId']),
  entityId: _optionalText(row['entityId']),
  title: _textValue(row['title']),
  subtitle: _textValue(row['subtitle']),
  avatarUrl: _textValue(row['avatarUrl']),
  relationState: _optionalText(row['relationState']),
  summaryIntersections: switch (row['summaryIntersections']) {
    List values =>
      values.map((value) => value.toString()).toList(growable: false),
    _ => const <String>[],
  },
  sourceEntityTitle: _optionalText(row['sourceEntityTitle']),
  sourceCircleTitle: _optionalText(row['sourceCircleTitle']),
  memberCount: row['memberCount'] == null
      ? null
      : _intValue(row['memberCount']),
  contactCount: _intValue(row['contactCount']),
  lastActiveAt: _optionalDate(row['lastActiveAt']),
  sortKey: _textValue(row['sortKey']),
  isStarred: row['isStarred'] as bool?,
);

String _textValue(Object? value, {String fallback = ''}) {
  final normalized = value?.toString().trim() ?? '';
  return normalized.isEmpty ? fallback : normalized;
}

String? _optionalText(Object? value) {
  final normalized = _textValue(value);
  return normalized.isEmpty ? null : normalized;
}

int _intValue(Object? value, {int fallback = 0}) => switch (value) {
  int number => number,
  num number => number.toInt(),
  String text => int.tryParse(text) ?? fallback,
  _ => fallback,
};

DateTime _requiredDate(Object? value) =>
    _optionalDate(value) ??
    (throw FormatException('fixture timestamp is required'));

DateTime? _optionalDate(Object? value) => switch (value) {
  DateTime date => date,
  String text when text.trim().isNotEmpty => DateTime.parse(text),
  _ => null,
};

InMemoryChatStateEngine _resolveEngine({
  required InMemoryChatStateEngine? engine,
  required List<Map<String, dynamic>>? seedConversations,
  required Map<String, List<Map<String, dynamic>>>? seedMembers,
  required Map<String, List<Map<String, dynamic>>>? seedMessages,
}) {
  if (engine != null) {
    if (seedConversations != null ||
        seedMembers != null ||
        seedMessages != null) {
      throw ArgumentError(
        'engine 与 seedConversations/seedMembers/seedMessages 不能同时传入',
      );
    }
    return engine;
  }
  return InMemoryChatStateEngine(
    seedConversations: _fixtureRows(seedConversations),
    seedMembers: _fixtureRowMap(seedMembers),
    seedMessages: _fixtureRowMap(seedMessages),
  );
}

List<ChatFixtureObject>? _fixtureRows(List<Map<String, dynamic>>? rows) =>
    rows?.map((row) => Map<String, Object?>.from(row)).toList(growable: false);

Map<String, List<ChatFixtureObject>>? _fixtureRowMap(
  Map<String, List<Map<String, dynamic>>>? rows,
) => rows?.map(
  (key, value) => MapEntry(
    key,
    value.map((row) => Map<String, Object?>.from(row)).toList(growable: false),
  ),
);
