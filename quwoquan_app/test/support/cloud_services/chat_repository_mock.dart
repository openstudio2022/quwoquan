// Test-only ChatRepository double. Production and all App environments use Remote.
import 'package:quwoquan_app/cloud/chat/models/chat_conversation_timestamp_dto.dart';
import 'package:quwoquan_app/cloud/chat/models/chat_message_receipt_dto.dart';
import 'package:quwoquan_app/cloud/chat/models/conversation_dto.dart';
import 'package:quwoquan_app/cloud/chat/models/sync_response.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_contact_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_conversation_created_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_conversation_member_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_group_settings_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_inbox_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_message_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/contact_home_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/group_home_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/message_home_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/selectable_group_conversation_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository_api.dart';

import 'repository_mock_reexports.dart';

/// local_contract 专用 App DTO 薄适配器。
///
/// 所有 fixture/state 行为都委托给 pure Dart [AlphaChatStateEngine]；
/// 此类只承担 `quwoquan_app` DTO 映射，不持有第二份 chat 状态。
class MockChatRepository implements ChatRepository {
  MockChatRepository({
    AlphaChatStateEngine? engine,
    List<Map<String, dynamic>>? seedConversations,
    Map<String, List<Map<String, dynamic>>>? seedMembers,
    Map<String, List<Map<String, dynamic>>>? seedMessages,
  }) : _engine = _resolveEngine(
         engine: engine,
         seedConversations: seedConversations,
         seedMembers: seedMembers,
         seedMessages: seedMessages,
       );

  final AlphaChatStateEngine _engine;

  @override
  Future<List<ChatInboxDto>> listInbox({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async => _engine
      .listInbox(limit: limit)
      .map((row) => ChatInboxDto.fromMap(_appMap(row)))
      .toList(growable: false);

  @override
  Future<List<MessageHomeRowDto>> listMessageHome({
    String filter = 'all',
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async => _engine
      .listMessageHome(filter: filter, limit: limit)
      .map((row) => MessageHomeRowDto.fromMap(_appMap(row)))
      .toList(growable: false);

  @override
  Future<List<ChatInboxDto>> listConversations({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async => _engine
      .listConversations(limit: limit)
      .map((row) => ChatInboxDto.fromMap(_appMap(row)))
      .toList(growable: false);

  @override
  Future<ChatConversationCreatedDto> createConversation({
    required String type,
    String? title,
    int? maxGroupSize,
    List<String>? initialMemberIds,
    String? idempotencyKey,
  }) async {
    return ChatConversationCreatedDto.fromMap(
      _appMap(
        _engine.createConversation(
          type: type,
          title: title,
          maxGroupSize: maxGroupSize,
          initialMemberIds: initialMemberIds,
        ),
      ),
    );
  }

  @override
  Future<ConversationDto> getConversation(String conversationId) async =>
      ConversationDto.fromMap(_appMap(_engine.getConversation(conversationId)));

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
  Future<List<ChatMessageDto>> listMessages({
    required String conversationId,
    String? before,
    int limit = CloudApiDefaults.pageLimit,
  }) async => _engine
      .listMessages(
        conversationId: conversationId,
        before: before,
        limit: limit,
      )
      .map((row) => ChatMessageDto.fromMap(_appMap(row)))
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
  Future<SyncResponse> syncMessages({
    required String conversationId,
    required int lastSeq,
    int limit = CloudApiDefaults.syncMessagesLimit,
  }) async {
    final page = _engine.syncMessages(
      conversationId: conversationId,
      lastSeq: lastSeq,
      limit: limit,
    );
    return SyncResponse(
      messages: page.messages
          .map((row) => ChatMessageDto.fromMap(_appMap(row)))
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
  Future<List<ChatMessageReceiptDto>> getReceipts({
    required String conversationId,
    required String messageId,
  }) async => _engine
      .getReceipts(conversationId: conversationId, messageId: messageId)
      .map((row) => ChatMessageReceiptDto.fromMap(_appMap(row)))
      .toList(growable: false);

  @override
  Future<List<ChatConversationMemberDto>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
    String? role,
    String? sort,
  }) async => _engine
      .listMembers(
        conversationId: conversationId,
        limit: limit,
        role: role,
        sort: sort,
      )
      .map((row) => ChatConversationMemberDto.fromMap(_appMap(row)))
      .toList(growable: false);

  @override
  Future<List<ChatConversationMemberDto>> searchMembers({
    required String conversationId,
    required String query,
    int limit = CloudApiDefaults.chatMemberSearchLimit,
  }) async => _engine
      .listMembers(
        conversationId: conversationId,
        limit: limit.clamp(1, CloudApiDefaults.chatMemberSearchLimit),
        query: query,
        sort: 'display_name_asc',
      )
      .map((row) => ChatConversationMemberDto.fromMap(_appMap(row)))
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
  Future<void> inviteAssistant({
    required String conversationId,
    String? skillId,
  }) async =>
      _engine.inviteAssistant(conversationId: conversationId, skillId: skillId);

  @override
  Future<void> removeAssistant({required String conversationId}) async =>
      _engine.removeAssistant(conversationId: conversationId);

  @override
  Future<CursorPage<ChatContactRowDto>> listContacts({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final page = _engine.listContacts(cursor: cursor, limit: limit);
    return CursorPage<ChatContactRowDto>(
      items: page.items
          .map((row) => ChatContactRowDto.fromMap(_appMap(row)))
          .toList(growable: false),
      nextCursor: page.nextCursor,
    );
  }

  @override
  Future<List<ContactHomeRowDto>> listContactHome({
    String filter = 'all',
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async => _engine
      .listContactHome(filter: filter, limit: limit)
      .map((row) => ContactHomeRowDto.fromMap(_appMap(row)))
      .toList(growable: false);

  @override
  Future<List<ChatContactRowDto>> listGroupCandidates({
    String? conversationId,
    int limit = CloudApiDefaults.pageLimit,
  }) async => _engine
      .listGroupCandidates(conversationId: conversationId, limit: limit)
      .map((row) => ChatContactRowDto.fromMap(_appMap(row)))
      .toList(growable: false);

  @override
  Future<CursorPage<SelectableGroupConversationRowDto>>
  listSelectableGroupConversations({
    String? query,
    ChatSelectableGroupSource source = ChatSelectableGroupSource.all,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final page = _engine.listSelectableGroupConversations(
      query: query,
      source: source.wireValue,
      cursor: cursor,
      limit: limit,
    );
    return CursorPage<SelectableGroupConversationRowDto>(
      items: page.items
          .map((row) => SelectableGroupConversationRowDto.fromMap(_appMap(row)))
          .toList(growable: false),
      nextCursor: page.nextCursor,
    );
  }

  @override
  Future<CursorPage<ChatContactRowDto>> listSelectableGroupContactMembers({
    required String conversationId,
    String? query,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final page = _engine.listSelectableGroupContactMembers(
      conversationId: conversationId,
      query: query,
      cursor: cursor,
      limit: limit,
    );
    return CursorPage<ChatContactRowDto>(
      items: page.items
          .map((row) => ChatContactRowDto.fromMap(_appMap(row)))
          .toList(growable: false),
      nextCursor: page.nextCursor,
    );
  }

  @override
  Future<List<ChatConversationTimestampDto>>
  getConversationTimestamps() async => _engine
      .getConversationTimestamps()
      .map((row) => ChatConversationTimestampDto.fromMap(_appMap(row)))
      .toList(growable: false);

  @override
  Future<List<ConversationDto>> batchGetConversations(List<String> ids) async =>
      _engine
          .batchGetConversations(ids)
          .map((row) => ConversationDto.fromMap(_appMap(row)))
          .toList(growable: false);

  @override
  Future<ChatGroupSettingsDto> getGroupSettings(String conversationId) async =>
      ChatGroupSettingsDto.fromMap(
        _appMap(_engine.getGroupSettings(conversationId)),
      );

  @override
  Future<GroupHomeDto> getGroupHome(String conversationId) async =>
      GroupHomeDto.fromMap(_appMap(_engine.getGroupHome(conversationId)));

  @override
  Future<void> updateGroupSettings(
    String conversationId,
    ChatGroupSettingsDto settings,
  ) async => _engine.updateGroupSettings(
    conversationId,
    Map<String, Object?>.from(settings.toMap()),
  );

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

AlphaChatStateEngine _resolveEngine({
  required AlphaChatStateEngine? engine,
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
  return AlphaChatStateEngine(
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
