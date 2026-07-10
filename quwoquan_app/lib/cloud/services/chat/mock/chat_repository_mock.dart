import 'package:quwoquan_app/cloud/chat/generated/chat_errors.g.dart';
import 'package:quwoquan_app/cloud/chat/models/chat_contact_tab_row_dtos.dart';
import 'package:quwoquan_app/cloud/chat/models/chat_conversation_timestamp_dto.dart';
import 'package:quwoquan_app/cloud/chat/models/chat_message_receipt_dto.dart';
import 'package:quwoquan_app/cloud/chat/models/conversation_dto.dart';
import 'package:quwoquan_app/cloud/chat/models/send_message_response.dart';
import 'package:quwoquan_app/cloud/chat/models/sync_response.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_wire_json_types.dart';
import 'package:quwoquan_app/cloud/runtime/contract_fixture_runtime_loader.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_contact_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_contact_search_item_dto.g.dart';
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
import 'package:quwoquan_app/cloud/services/chat/chat_repository_api.dart';
import 'package:quwoquan_app/cloud/services/chat/mock/chat_mock_data.dart';
import 'package:quwoquan_app/core/models/search_models.dart';
import 'package:quwoquan_app/core/services/cache/conversation_cache_record.dart';

class MockChatRepository implements ChatRepository {
  MockChatRepository({
    List<Map<String, dynamic>>? seedConversations,
    Map<String, List<Map<String, dynamic>>>? seedMembers,
    Map<String, List<Map<String, dynamic>>>? seedMessages,
  }) {
    final contractSeed = ContractFixtureRuntimeLoader.chatSeedSet();
    final contactSeed = ContractFixtureRuntimeLoader.chatSeedSet(
      'chat_contacts_core',
    );
    final mergedContacts = _mergeRowsByKeys(
      _listOfMap(contactSeed?['contacts']),
      ChatMockData.contacts,
      const <String>['userId', 'contactId', 'id'],
    );
    _contactRows = mergedContacts
        .where(_contactRowHasContractAvatar)
        .map(ChatContactRowDto.fromMap)
        .toList(growable: false);
    _contactCircleIds =
        (contactSeed?['circleIds'] as List?)
            ?.map((id) => id.toString())
            .where((id) => id.isNotEmpty)
            .toList(growable: false) ??
        const <String>[];
    _contactGroupConversationIds =
        (contactSeed?['groupConversationIds'] as List?)
            ?.map((id) => id.toString())
            .where((id) => id.isNotEmpty)
            .toSet() ??
        <String>{};

    final contractConversations = _listOfMap(contractSeed?['conversations']);
    final repositoryConversations =
        seedConversations ??
        _mergeRowsById(contractConversations, ChatMockData.conversations);
    final inboxRows =
        seedConversations ??
        _mergeRowsById(contractConversations, ChatMockData.inboxItems);

    _conversationCache = repositoryConversations
        .map(ConversationCacheRecord.fromWireMap)
        .toList(growable: true);
    _inboxOverrides = {
      for (final row in inboxRows)
        ChatInboxDto.fromMap(row).id: ChatInboxDto.fromMap(row),
    };

    final contractMembers = _mapOfList(contractSeed?['members']);
    final initialMembers = seedMembers ?? contractMembers;
    if (initialMembers != null) {
      for (final entry in initialMembers.entries) {
        _membersCache[entry.key] = entry.value
            .map(ChatConversationMemberDto.fromMap)
            .toList(growable: true);
      }
    }

    final contractMessages = _mapOfList(contractSeed?['messages']);
    final initialMessages = seedMessages ?? contractMessages;
    if (initialMessages != null) {
      for (final entry in initialMessages.entries) {
        _messagesCache[entry.key] = entry.value
            .map(ChatMessageDto.fromMap)
            .toList(growable: true);
      }
    }
    _materializeSeededGroupAvatarMetadata();
  }

  int _seqCounter = 100;
  late final List<ConversationCacheRecord> _conversationCache;
  late final List<ChatContactRowDto> _contactRows;
  late final List<String> _contactCircleIds;
  late final Set<String> _contactGroupConversationIds;
  late final Map<String, ChatInboxDto> _inboxOverrides;
  final Map<String, List<ChatConversationMemberDto>> _membersCache =
      <String, List<ChatConversationMemberDto>>{};
  final Map<String, List<ChatMessageDto>> _messagesCache =
      <String, List<ChatMessageDto>>{};
  final Map<String, ChatGroupSettingsDto> _settingsCache =
      <String, ChatGroupSettingsDto>{};

  static final ChatGroupSettingsDto _defaultSettings = ChatGroupSettingsDto();

  /// 联系人头像必须走 avatar 媒体平面；禁止 [media/image] 泄漏进 Mock 收件箱。
  static bool _contactRowHasContractAvatar(Map<String, dynamic> row) {
    final avatar = (row['avatarUrl'] ?? row['avatar'])?.toString().trim() ?? '';
    if (avatar.isEmpty) {
      return false;
    }
    return avatar.toLowerCase().startsWith('media/avatar/');
  }

  static List<Map<String, dynamic>>? _listOfMap(Object? value) {
    if (value is! List) {
      return null;
    }
    return value
        .whereType<Map>()
        .map((item) => item.cast<String, dynamic>())
        .toList(growable: false);
  }

  static Map<String, List<Map<String, dynamic>>>? _mapOfList(Object? value) {
    if (value is! Map) {
      return null;
    }
    return value.map(
      (key, raw) => MapEntry(
        key.toString(),
        ((raw as List?) ?? const <dynamic>[])
            .whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false),
      ),
    );
  }

  static List<Map<String, dynamic>> _mergeRowsById(
    List<Map<String, dynamic>>? primary,
    List<Map<String, dynamic>> fallback,
  ) {
    final byId = <String, Map<String, dynamic>>{};
    void put(Map<String, dynamic> row, {required bool overwrite}) {
      final id = (row['conversationId'] ?? row['id'] ?? row['_id'] ?? '')
          .toString();
      if (id.isEmpty) {
        return;
      }
      if (overwrite || !byId.containsKey(id)) {
        byId[id] = row;
      }
    }

    for (final row in primary ?? const <Map<String, dynamic>>[]) {
      put(row, overwrite: true);
    }
    for (final row in fallback) {
      put(row, overwrite: false);
    }
    return byId.values.toList(growable: false);
  }

  static List<Map<String, dynamic>> _mergeRowsByKeys(
    List<Map<String, dynamic>>? primary,
    List<Map<String, dynamic>> fallback,
    List<String> keys,
  ) {
    final byId = <String, Map<String, dynamic>>{};
    void put(Map<String, dynamic> row, {required bool overwrite}) {
      var id = '';
      for (final key in keys) {
        id = (row[key] ?? '').toString();
        if (id.isNotEmpty) {
          break;
        }
      }
      if (id.isEmpty) {
        return;
      }
      if (overwrite || !byId.containsKey(id)) {
        byId[id] = row;
      }
    }

    for (final row in primary ?? const <Map<String, dynamic>>[]) {
      put(row, overwrite: true);
    }
    for (final row in fallback) {
      put(row, overwrite: false);
    }
    return byId.values.toList(growable: false);
  }

  ConversationCacheRecord? _findConversation(String conversationId) {
    for (final conversation in _conversationCache) {
      if (conversation.id == conversationId) {
        return conversation;
      }
    }
    return null;
  }

  void _replaceConversation(ConversationCacheRecord next) {
    final index = _conversationCache.indexWhere((item) => item.id == next.id);
    if (index >= 0) {
      _conversationCache[index] = next;
      return;
    }
    _conversationCache.insert(0, next);
  }

  List<ChatConversationMemberDto> _ensureMembersCache(String conversationId) {
    return _membersCache.putIfAbsent(
      conversationId,
      () => ChatMockData.membersFor(
        conversationId,
      ).map(ChatConversationMemberDto.fromMap).toList(growable: true),
    );
  }

  List<ChatMessageDto> _messagesFor(String conversationId) {
    return _messagesCache.putIfAbsent(
      conversationId,
      () => ChatMockData.messagesFor(
        conversationId,
      ).map(ChatMessageDto.fromMap).toList(growable: true),
    );
  }

  ChatInboxDto _effectiveInbox(ConversationCacheRecord record) {
    final base = record.toChatInboxDto();
    final override = _inboxOverrides[record.id];
    if (override == null) {
      return base;
    }
    return override.copyWith(
      id: record.id,
      type: record.type.isEmpty ? override.type : record.type,
      title: record.title.isEmpty ? override.title : record.title,
      avatarUrl: record.avatarUrl.isEmpty
          ? override.avatarUrl
          : record.avatarUrl,
      groupAvatarVersion: record.groupAvatarVersion,
      lastMessagePreview: record.lastMessagePreview.isEmpty
          ? override.lastMessagePreview
          : record.lastMessagePreview,
      lastMessageType: record.lastMessageType.isEmpty
          ? override.lastMessageType
          : record.lastMessageType,
      lastMessageTime:
          _parseIso(record.lastMessageAt) ?? override.lastMessageTime,
      lastSeq: record.lastSeq > 0 ? record.lastSeq : override.lastSeq,
      circleId: record.circleId.isEmpty ? override.circleId : record.circleId,
    );
  }

  void _syncInboxFromConversation(ConversationCacheRecord record) {
    _inboxOverrides[record.id] = _effectiveInbox(record);
  }

  void _materializeSeededGroupAvatarMetadata() {
    for (var index = 0; index < _conversationCache.length; index++) {
      final current = _conversationCache[index];
      if (current.type != 'group' || current.avatarUrl.trim().isEmpty) {
        continue;
      }
      final sourceHash = _groupAvatarSourceHash(
        _ensureMembersCache(current.id),
      );
      if (sourceHash.isEmpty) {
        continue;
      }
      final needsVersion = current.groupAvatarVersion <= 0;
      final needsSourceHash = (current.groupAvatarSourceHash ?? '')
          .trim()
          .isEmpty;
      if (!needsVersion && !needsSourceHash) {
        continue;
      }
      final next = current.copyWith(
        groupAvatarVersion: needsVersion ? 1 : current.groupAvatarVersion,
        groupAvatarSourceHash: needsSourceHash
            ? sourceHash
            : current.groupAvatarSourceHash,
      );
      _conversationCache[index] = next;
      _syncInboxFromConversation(next);
    }
  }

  void _bumpMembersRosterAfterMemberChange(
    String conversationId,
    int memberCount,
  ) {
    final current = _findConversation(conversationId);
    if (current == null) {
      return;
    }
    var next = current.copyWith(
      memberCount: memberCount,
      membersRosterRevision: (current.membersRosterRevision ?? 0) + 1,
      updatedAt: DateTime.now().toIso8601String(),
    );
    if (current.type == 'group') {
      final members = _ensureMembersCache(conversationId);
      final sourceHash = _groupAvatarSourceHash(members);
      if (sourceHash.isNotEmpty &&
          sourceHash != current.groupAvatarSourceHash) {
        final nextVersion = current.groupAvatarVersion + 1;
        next = next.copyWith(
          avatarUrl: _renderedGroupAvatarUrl(
            conversationId,
            sourceHash,
            nextVersion,
          ),
          groupAvatarVersion: nextVersion,
          groupAvatarSourceHash: sourceHash,
        );
      }
    }
    _replaceConversation(next);
    _syncInboxFromConversation(next);
  }

  static String _groupAvatarSourceHash(
    List<ChatConversationMemberDto> members,
  ) {
    return sortChatMemberDtos(
      members,
      'joined_asc',
    ).take(9).map((member) => '${member.userId}:${member.avatarUrl}').join('|');
  }

  static String _renderedGroupAvatarUrl(
    String conversationId,
    String sourceHash,
    int version,
  ) {
    final stableHash = sourceHash.hashCode & 0x7fffffff;
    return '${ChatMockData.groupAvatarFor(conversationId, version: version)}'
        '?h=$stableHash';
  }

  String _matchDirectConversationId(String userId, String displayName) {
    for (final conversation in _conversationCache) {
      final isDirectLike =
          conversation.type == 'direct' || conversation.type == 'encrypted';
      if (!isDirectLike) {
        continue;
      }
      final title = conversation.title.trim();
      if (title.isNotEmpty && title == displayName.trim()) {
        return conversation.id;
      }
    }
    for (final conversation in _conversationCache) {
      final isDirectLike =
          conversation.type == 'direct' || conversation.type == 'encrypted';
      if (!isDirectLike) {
        continue;
      }
      final members = _ensureMembersCache(conversation.id);
      if (members.any((member) => member.userId == userId)) {
        return conversation.id;
      }
    }
    return '';
  }

  @override
  Future<List<ChatInboxDto>> listInbox({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final rows = _conversationCache
        .where(
          (conversation) =>
              conversation.status == 'active' ||
              conversation.status == 'blocked',
        )
        .map(_effectiveInbox)
        .toList(growable: false);
    return rows.take(limit).toList(growable: false);
  }

  @override
  Future<List<MessageHomeRowDto>> listMessageHome({
    String filter = 'all',
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final rows = (await listInbox(cursor: cursor, limit: limit))
        .where((item) {
          switch (filter) {
            case 'unread':
              return item.unreadCount > 0;
            case 'group':
              return item.type == 'group';
            case 'direct':
              return item.type == 'direct' || item.type == 'encrypted';
            case 'notification':
              return false;
            default:
              return true;
          }
        })
        .map(
          (item) => MessageHomeRowDto(
            id: item.id,
            kind: 'conversation',
            conversationId: item.id,
            conversationType: item.type,
            title: item.title,
            summary: item.lastMessagePreview,
            avatarUrl: item.avatarUrl,
            groupAvatarVersion: item.groupAvatarVersion,
            lastActiveAt: item.lastMessageTime,
            unreadCount: item.unreadCount,
            mentionUnreadCount: item.mentionUnreadCount,
            muted: item.muted,
            pinned: item.pinned,
            read: item.unreadCount == 0,
          ),
        )
        .toList(growable: false);
    return rows.take(limit).toList(growable: false);
  }

  @override
  Future<List<ChatInboxDto>> listConversations({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return listInbox(cursor: cursor, limit: limit);
  }

  @override
  Future<List<ConversationSearchItemView>> searchConversations({
    required String query,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final normalizedQuery = query.trim().toLowerCase();
    if (normalizedQuery.isEmpty) {
      return const <ConversationSearchItemView>[];
    }
    return _conversationCache
        .where((conversation) {
          final title = conversation.title.toLowerCase();
          final preview = conversation.lastMessagePreview.toLowerCase();
          return title.contains(normalizedQuery) ||
              preview.contains(normalizedQuery);
        })
        .take(limit)
        .map((conversation) {
          final title = conversation.title;
          final preview = conversation.lastMessagePreview;
          final highlight = title.toLowerCase().contains(normalizedQuery)
              ? title
              : preview;
          return ConversationSearchItemView.fromMap(<String, dynamic>{
            ...conversation.toWireMap(),
            'highlightText': highlight,
            'matchedField': title.toLowerCase().contains(normalizedQuery)
                ? 'title'
                : 'lastMessagePreview',
          });
        })
        .toList(growable: false);
  }

  @override
  Future<ChatConversationCreatedDto> createConversation({
    required String type,
    String? title,
    String? circleId,
    String? circleGroupId,
    String? originType,
    String? bindingType,
    String? lifecyclePolicy,
    int? maxGroupSize,
    List<String>? initialMemberIds,
  }) async {
    if ((type == 'direct' || type == 'encrypted') &&
        initialMemberIds != null &&
        initialMemberIds.length == 1) {
      final peerId = initialMemberIds.first.trim();
      final reusedId = _matchDirectConversationId(
        peerId,
        ChatMockData.nameFor(peerId),
      );
      if (reusedId.isNotEmpty) {
        return ChatConversationCreatedDto(conversationId: reusedId);
      }
    }
    final conversationId = 'conv_new_${DateTime.now().millisecondsSinceEpoch}';
    final now = DateTime.now().toUtc().toIso8601String();
    final record = ConversationCacheRecord(
      id: conversationId,
      type: type,
      title: title ?? '',
      creatorId: ChatMockData.currentUserProfileId,
      circleId: circleId ?? '',
      circleGroupId: circleGroupId,
      originType:
          originType ?? _defaultOriginType(type, circleId, circleGroupId),
      bindingType: bindingType ?? _defaultBindingType(circleId, circleGroupId),
      lifecyclePolicy:
          lifecyclePolicy ?? _defaultLifecyclePolicy(circleId, circleGroupId),
      maxSeq: 0,
      lastSeq: 0,
      memberCount: (initialMemberIds?.length ?? 0) + 1,
      maxGroupSize: maxGroupSize ?? 500,
      status: 'active',
      createdAt: now,
      updatedAt: now,
      settingsUpdatedAt: now,
      lastMessageAt: now,
      membersRosterRevision: 1,
    );
    _replaceConversation(record);
    _syncInboxFromConversation(record);
    if (type == 'group') {
      _contactGroupConversationIds.add(conversationId);
    }
    _membersCache[conversationId] = <ChatConversationMemberDto>[
      ChatConversationMemberDto(
        userId: ChatMockData.currentUserProfileId,
        displayName: '我',
        avatarUrl: ChatMockData.avatarFor(ChatMockData.currentUserProfileId),
        role: 'owner',
        isCurrentUser: true,
        joinedAt: DateTime.parse(now),
      ),
      for (var i = 0; i < (initialMemberIds?.length ?? 0); i++)
        ChatConversationMemberDto(
          userId: initialMemberIds![i],
          displayName: ChatMockData.nameFor(initialMemberIds[i]),
          avatarUrl: ChatMockData.avatarFor(initialMemberIds[i]),
          role: 'member',
          joinedAt: DateTime.parse(now).add(Duration(milliseconds: i + 1)),
        ),
    ];
    return ChatConversationCreatedDto(conversationId: conversationId);
  }

  @override
  Future<ConversationDto> getConversation(String conversationId) async {
    final record =
        _findConversation(conversationId) ??
        (_conversationCache.isNotEmpty ? _conversationCache.first : null);
    if (record == null) {
      return ConversationDto.fromMap(const <String, dynamic>{});
    }
    return ConversationDto.fromMap(record.toWireMap());
  }

  @override
  Future<void> updateConversationTitle(
    String conversationId,
    String title,
  ) async {
    final record = _findConversation(conversationId);
    if (record == null) {
      return;
    }
    final next = record.copyWith(title: title);
    _replaceConversation(next);
    _syncInboxFromConversation(next);
  }

  @override
  Future<List<ChatMessageDto>> listMessages({
    required String conversationId,
    String? before,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    var messages = List<ChatMessageDto>.from(_messagesFor(conversationId));
    if (before != null && before.trim().isNotEmpty) {
      final pivot = messages.indexWhere(
        (message) => message.id == before.trim(),
      );
      if (pivot > 0) {
        messages = messages.take(pivot).toList(growable: false);
      }
    }
    if (limit > 0 && messages.length > limit) {
      messages = messages.take(limit).toList(growable: false);
    }
    return messages;
  }

  @override
  Future<List<MessageSearchItemView>> searchMessages({
    required String query,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final normalizedQuery = query.trim().toLowerCase();
    if (normalizedQuery.isEmpty) {
      return const <MessageSearchItemView>[];
    }
    final results = <MessageSearchItemView>[];
    for (final conversation in _conversationCache) {
      final messages = _messagesFor(conversation.id);
      for (final message in messages) {
        final content = (message.content ?? '').trim();
        final senderName = (message.senderName ?? '').trim();
        if (!content.toLowerCase().contains(normalizedQuery) &&
            !senderName.toLowerCase().contains(normalizedQuery)) {
          continue;
        }
        results.add(
          MessageSearchItemView.fromMap(<String, dynamic>{
            ...message.toMap(),
            'conversationId': conversation.id,
            'conversationTitle': conversation.title,
            'conversationAvatarUrl': conversation.avatarUrl,
            'contentPreview': content,
            'highlightText': content.toLowerCase().contains(normalizedQuery)
                ? content
                : senderName,
            'matchedField': content.toLowerCase().contains(normalizedQuery)
                ? 'content'
                : 'senderDisplayName',
          }),
        );
        if (results.length >= limit) {
          return results;
        }
      }
    }
    return results;
  }

  @override
  Future<SendMessageResponse> sendMessage({
    required String conversationId,
    required String type,
    required String content,
    String? mediaUrl,
    CloudJsonMap? media,
    CloudJsonMap? cardPayload,
    String? replyToMessageId,
    List<String>? mentions,
    String? senderSubAccountId,
    String? personaContextVersion,
    String? senderDisplayNameSnapshot,
    String? senderAvatarUrlSnapshot,
    required String clientMsgId,
  }) async {
    final conversation = _findConversation(conversationId);
    if (conversation != null && conversation.status == 'blocked') {
      throw StateError(ChatErrorCode.blocked.code);
    }
    _seqCounter += 1;
    final now = DateTime.now().toUtc();
    final message = ChatMessageDto(
      id: 'msg_mock_${now.microsecondsSinceEpoch}',
      conversationId: conversationId,
      seq: _seqCounter,
      clientMsgId: clientMsgId,
      senderId: senderSubAccountId ?? ChatMockData.currentUserProfileId,
      senderName: senderDisplayNameSnapshot,
      senderAvatar: senderAvatarUrlSnapshot,
      senderSubAccountId: senderSubAccountId,
      type: type,
      content: content,
      mediaUrl: mediaUrl,
      media: media,
      cardPayload: cardPayload,
      replyToMessageId: replyToMessageId,
      mentions: mentions,
      status: 'sent',
      timestamp: now,
    );
    final messages = _messagesFor(conversationId)..add(message);
    final record = _findConversation(conversationId);
    if (record != null) {
      final next = record.copyWith(
        maxSeq: _seqCounter,
        lastSeq: _seqCounter,
        messageCount: messages.length,
        lastMessagePreview: content,
        lastMessageType: type,
        lastMessageAt: now.toIso8601String(),
        updatedAt: now.toIso8601String(),
      );
      _replaceConversation(next);
      _syncInboxFromConversation(next);
    }
    return SendMessageResponse(
      id: message.id,
      seq: message.seq,
      timestamp: now,
    );
  }

  @override
  Future<void> recallMessage({
    required String conversationId,
    required String messageId,
  }) async {
    final messages = _messagesFor(conversationId);
    final index = messages.indexWhere((message) => message.id == messageId);
    if (index < 0) {
      return;
    }
    messages[index] = messages[index].copyWith(
      status: 'recalled',
      recalledAt: DateTime.now().toUtc(),
    );
  }

  @override
  Future<SyncResponse> syncMessages({
    required String conversationId,
    required int lastSeq,
    int limit = CloudApiDefaults.syncMessagesLimit,
  }) async {
    final all = _messagesFor(
      conversationId,
    ).where((message) => message.seq > lastSeq).toList(growable: false);
    final page = limit > 0 && all.length > limit
        ? all.take(limit).toList(growable: false)
        : all;
    return SyncResponse(messages: page, hasMore: all.length > page.length);
  }

  @override
  Future<void> markAsRead({
    required String conversationId,
    required String messageId,
  }) async {
    final inbox = _inboxOverrides[conversationId];
    if (inbox != null) {
      _inboxOverrides[conversationId] = inbox.copyWith(
        unreadCount: 0,
        mentionUnreadCount: 0,
      );
    }
  }

  @override
  Future<List<ChatMessageReceiptDto>> getReceipts({
    required String conversationId,
    required String messageId,
  }) async {
    final messages = await listMessages(
      conversationId: conversationId,
      limit: CloudApiDefaults.pageLimit,
    );
    final exists = messages.any((message) => message.id == messageId);
    if (!exists) {
      return const <ChatMessageReceiptDto>[];
    }
    return [
      ChatMessageReceiptDto(
        userId: ChatMockData.currentUserProfileId,
        readAt: DateTime.now().toUtc(),
      ),
    ];
  }

  @override
  Future<List<ChatConversationMemberDto>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
    String? role,
    String? sort,
  }) async {
    var rows = List<ChatConversationMemberDto>.from(
      _ensureMembersCache(conversationId),
    );
    rows = sortChatMemberDtos(rows, sort);
    if (role != null && role.isNotEmpty) {
      rows = rows.where((member) => member.role == role).toList();
    }
    if (limit > 0 && rows.length > limit) {
      rows = rows.take(limit).toList(growable: false);
    }
    return rows;
  }

  @override
  Future<void> addMembers({
    required String conversationId,
    required List<String> userIds,
  }) async {
    final members = _ensureMembersCache(conversationId);
    final existingIds = members.map((member) => member.userId).toSet();
    var latestJoinedAt = DateTime.fromMillisecondsSinceEpoch(0, isUtc: true);
    for (final member in members) {
      final joinedAt = member.joinedAt;
      if (joinedAt != null && joinedAt.isAfter(latestJoinedAt)) {
        latestJoinedAt = joinedAt;
      }
    }
    var added = 0;
    for (final userId in userIds) {
      if (existingIds.contains(userId)) {
        continue;
      }
      added += 1;
      members.add(
        ChatConversationMemberDto(
          userId: userId,
          displayName: ChatMockData.nameFor(userId),
          avatarUrl: ChatMockData.avatarFor(userId),
          role: 'member',
          joinedAt: latestJoinedAt.add(Duration(milliseconds: added)),
        ),
      );
    }
    if (added > 0) {
      _bumpMembersRosterAfterMemberChange(conversationId, members.length);
    }
  }

  @override
  Future<void> removeMember({
    required String conversationId,
    required String userId,
  }) async {
    final members = _ensureMembersCache(conversationId)
      ..removeWhere((member) => member.userId == userId);
    _bumpMembersRosterAfterMemberChange(conversationId, members.length);
  }

  @override
  Future<void> inviteAssistant({
    required String conversationId,
    String? skillId,
  }) async {
    final members = _ensureMembersCache(conversationId);
    if (members.any((member) => member.memberType == 'assistant')) {
      return;
    }
    members.add(
      ChatConversationMemberDto(
        userId: 'fixture_assistant_primary',
        displayName: '小助手',
        avatarUrl: ChatMockData.avatarFor('fixture_assistant_primary'),
        role: 'member',
        memberType: 'assistant',
        joinedAt: DateTime.now().toUtc(),
      ),
    );
    _bumpMembersRosterAfterMemberChange(conversationId, members.length);
  }

  @override
  Future<void> removeAssistant({required String conversationId}) async {
    final members = _ensureMembersCache(conversationId)
      ..removeWhere((member) => member.memberType == 'assistant');
    if (members.isEmpty) {
      return;
    }
    _bumpMembersRosterAfterMemberChange(conversationId, members.length);
  }

  @override
  Future<void> updateConversationSettings({
    required String conversationId,
    bool? muted,
    bool? pinned,
  }) async {
    final record = _findConversation(conversationId);
    if (record == null) {
      return;
    }
    final next = record.copyWith(muted: muted, pinned: pinned);
    _replaceConversation(next);
    final current = _effectiveInbox(next);
    _inboxOverrides[conversationId] = current.copyWith(
      muted: muted ?? current.muted,
      pinned: pinned ?? current.pinned,
    );
  }

  @override
  Future<List<ChatContactRowDto>> listContacts({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return _contactRows.take(limit).toList(growable: false);
  }

  @override
  Future<List<ContactHomeRowDto>> listContactHome({
    String filter = 'all',
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final rows = <ContactHomeRowDto>[];
    if (filter == 'all' || filter == 'mutual') {
      for (final contact in _contactRows) {
        if (filter == 'mutual' && contact.relationState != 'mutual') {
          continue;
        }
        rows.add(
          ContactHomeRowDto(
            id: contact.userId,
            kind: 'user',
            objectId: contact.userId,
            userId: contact.userId,
            conversationId: _matchDirectConversationId(
              contact.userId,
              contact.displayName,
            ),
            title: contact.displayName,
            subtitle: _firstNonEmpty(
              contact.bio,
              contact.metFrom,
              contact.lastInteraction,
            ),
            avatarUrl: contact.avatarUrl,
            relationState: contact.relationState,
            summaryIntersections: _firstTwoNonEmpty(
              contact.metFrom,
              contact.bio,
            ),
            lastActiveAt: _parseIso(contact.lastInteraction),
            sortKey: contact.lastInteraction,
            isStarred: contact.isStarred,
          ),
        );
      }
    }
    if (filter == 'all' || filter == 'circle') {
      final circles = await listContactTabCircles(limit: limit);
      rows.addAll(
        circles.map(
          (circle) => ContactHomeRowDto(
            id: circle.circleId,
            kind: 'circle',
            objectId: circle.circleId,
            circleId: circle.circleId,
            title: circle.displayName,
            subtitle: circle.subtitle,
            avatarUrl: circle.avatarUrl,
          ),
        ),
      );
    }
    if (filter == 'all' || filter == 'group') {
      final groups = await listContactTabFunGroups(limit: limit);
      rows.addAll(
        groups.map(
          (group) => ContactHomeRowDto(
            id: group.conversationId,
            kind: 'group',
            objectId: group.conversationId,
            conversationId: group.conversationId,
            title: group.displayName,
            subtitle: group.subtitle,
            avatarUrl: group.avatarUrl,
            summaryIntersections: _firstTwoNonEmpty(group.subtitle),
          ),
        ),
      );
    }
    return rows.take(limit).toList(growable: false);
  }

  @override
  Future<List<ChatContactRowDto>> listGroupCandidates({
    String? conversationId,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final locked = <String>{ChatMockData.currentUserProfileId};
    final normalizedConversationId = conversationId?.trim() ?? '';
    if (normalizedConversationId.isNotEmpty) {
      locked.addAll(
        _ensureMembersCache(
          normalizedConversationId,
        ).map((member) => member.userId).where((id) => id.isNotEmpty),
      );
    }
    return _contactRows
        .where(
          (contact) =>
              contact.relationState == 'mutual' &&
              contact.userId.isNotEmpty &&
              !locked.contains(contact.userId),
        )
        .take(limit)
        .toList(growable: false);
  }

  // ── 从群聊中选择联系人 ──────────────────────────────────────────────────────

  /// viewer 的互关联系人 userId 集合（与 listGroupCandidates 同源）。
  Set<String> _mutualContactIdSet() {
    return _contactRows
        .where((c) => c.relationState == 'mutual' && c.userId.isNotEmpty)
        .map((c) => c.userId)
        .toSet();
  }

  @override
  Future<List<SelectableGroupConversationRowDto>>
  listSelectableGroupConversations({
    String? query,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final mutualIds = _mutualContactIdSet();
    if (mutualIds.isEmpty) {
      return const <SelectableGroupConversationRowDto>[];
    }
    final normalizedQuery = (query ?? '').trim().toLowerCase();
    final rows = <SelectableGroupConversationRowDto>[];
    for (final conversation in _conversationCache) {
      if (conversation.type != 'group' || conversation.id.isEmpty) {
        continue;
      }
      if (conversation.status.isNotEmpty && conversation.status != 'active') {
        continue;
      }
      if (normalizedQuery.isNotEmpty &&
          !conversation.title.toLowerCase().contains(normalizedQuery)) {
        continue;
      }
      final members = _ensureMembersCache(conversation.id);
      final friendIds = members
          .where(
            (m) =>
                m.userId.isNotEmpty &&
                m.memberType == 'user' &&
                m.userId != ChatMockData.currentUserProfileId &&
                mutualIds.contains(m.userId),
          )
          .map((m) => m.userId)
          .toSet();
      if (friendIds.isEmpty) {
        continue;
      }
      rows.add(
        SelectableGroupConversationRowDto(
          conversationId: conversation.id,
          title: conversation.title.isNotEmpty
              ? conversation.title
              : conversation.id,
          avatarUrl: conversation.avatarUrl,
          friendMemberCount: friendIds.length,
          memberCount: conversation.memberCount > 0
              ? conversation.memberCount
              : members.length,
        ),
      );
      if (rows.length >= limit) {
        break;
      }
    }
    return rows;
  }

  @override
  Future<List<ChatContactRowDto>> listSelectableGroupContactMembers({
    required String conversationId,
    String? query,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final normalizedConversationId = conversationId.trim();
    // 图五仅从图四（已校验存在的群）进入；未知会话在 Mock 下返回空列表，
    // not-found 的结构化错误语义由云侧 api_integration 验证。
    if (_findConversation(normalizedConversationId) == null) {
      return const <ChatContactRowDto>[];
    }
    final mutualIds = _mutualContactIdSet();
    final contactById = <String, ChatContactRowDto>{
      for (final c in _contactRows.where((c) => c.userId.isNotEmpty))
        c.userId: c,
    };
    final normalizedQuery = (query ?? '').trim().toLowerCase();
    final members = _ensureMembersCache(normalizedConversationId);
    final out = <ChatContactRowDto>[];
    final seen = <String>{};
    for (final m in members) {
      final id = m.userId;
      if (id.isEmpty || id == ChatMockData.currentUserProfileId) {
        continue;
      }
      if (m.memberType != 'user') {
        continue;
      }
      if (!mutualIds.contains(id) || seen.contains(id)) {
        continue;
      }
      final contact = contactById[id];
      final displayName = (contact?.displayName.isNotEmpty ?? false)
          ? contact!.displayName
          : (m.displayName.isNotEmpty ? m.displayName : id);
      if (normalizedQuery.isNotEmpty &&
          !displayName.toLowerCase().contains(normalizedQuery)) {
        continue;
      }
      seen.add(id);
      out.add(
        (contact ??
                ChatContactRowDto(
                  userId: id,
                  displayName: displayName,
                  avatarUrl: m.avatarUrl,
                ))
            .copyWith(relationState: 'mutual', source: 'group'),
      );
      if (out.length >= limit) {
        break;
      }
    }
    return out;
  }

  @override
  Future<List<ChatContactTabCircleRowDto>> listContactTabCircles({
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final circleSeed = ContractFixtureRuntimeLoader.circleSeedSet();
    final circles = _listOfMap(circleSeed?['circles']);
    if (circles != null && _contactCircleIds.isNotEmpty) {
      final ids = _contactCircleIds.toSet();
      return circles
          .where((circle) => ids.contains(circle['id']?.toString()))
          .take(limit)
          .map(
            (circle) => ChatContactTabCircleRowDto(
              circleId: circle['id']?.toString() ?? '',
              displayName: circle['name']?.toString() ?? '',
              avatarUrl:
                  circle['avatarUrl']?.toString() ??
                  circle['coverUrl']?.toString() ??
                  '',
              subtitle: circle['description']?.toString() ?? '',
            ),
          )
          .toList(growable: false);
    }
    return ChatMockData.contactTabCircles
        .take(limit)
        .map(ChatContactTabCircleRowDto.fromMap)
        .toList(growable: false);
  }

  @override
  Future<List<ChatContactTabFunGroupRowDto>> listContactTabFunGroups({
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    if (_contactGroupConversationIds.isNotEmpty) {
      return _conversationCache
          .where(
            (conversation) =>
                _contactGroupConversationIds.contains(conversation.id),
          )
          .take(limit)
          .map(
            (conversation) => ChatContactTabFunGroupRowDto(
              conversationId: conversation.id,
              displayName: conversation.title,
              avatarUrl: conversation.avatarUrl,
              subtitle: conversation.lastMessagePreview,
            ),
          )
          .toList(growable: false);
    }
    return ChatMockData.contactTabFunGroups
        .take(limit)
        .map(ChatContactTabFunGroupRowDto.fromMap)
        .toList(growable: false);
  }

  @override
  Future<List<String>> listMemberUserIds(String conversationId) async {
    return _ensureMembersCache(conversationId)
        .map((member) => member.userId)
        .where((id) => id.isNotEmpty)
        .toList(growable: false);
  }

  @override
  Future<List<ChatContactSearchItemDto>> searchContacts({
    required String query,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final normalizedQuery = query.trim().toLowerCase();
    return _contactRows
        .where(
          (contact) =>
              contact.displayName.toLowerCase().contains(normalizedQuery),
        )
        .take(limit)
        .map((contact) {
          final conversationId = _matchDirectConversationId(
            contact.userId,
            contact.displayName,
          );
          return ChatContactSearchItemDto(
            contactId: contact.userId,
            displayName: contact.displayName,
            avatarUrl: contact.avatarUrl,
            conversationId: conversationId.isEmpty ? null : conversationId,
            conversationType: conversationId.isEmpty ? null : 'direct',
            subtitle: '联系人',
            highlightText: contact.displayName,
            matchedField: 'displayName',
          );
        })
        .toList(growable: false);
  }

  @override
  Future<List<ChatConversationTimestampDto>> getConversationTimestamps() async {
    return _conversationCache
        .where(
          (conversation) =>
              conversation.status == 'active' ||
              conversation.status == 'blocked',
        )
        .map((conversation) {
          final inbox = _effectiveInbox(conversation);
          return ChatConversationTimestampDto(
            conversationId: conversation.id,
            updatedAt: conversation.updatedAt,
            settingsUpdatedAt: conversation.settingsTimestamp,
            lastMessageAt: conversation.lastMessageAt,
            lastMessageTime: conversation.lastMessageAt,
            lastMessagePreview: inbox.lastMessagePreview,
            unreadCount: inbox.unreadCount,
            type: conversation.type,
          );
        })
        .toList(growable: false);
  }

  @override
  Future<List<ConversationDto>> batchGetConversations(List<String> ids) async {
    return _conversationCache
        .where((conversation) => ids.contains(conversation.id))
        .map(
          (conversation) => ConversationDto.fromMap(conversation.toWireMap()),
        )
        .toList(growable: false);
  }

  @override
  Future<ChatGroupSettingsDto> getGroupSettings(String conversationId) async {
    final conversation = _findConversation(conversationId);
    final settings = _settingsCache[conversationId] ?? _defaultSettings;
    return settings.copyWith(
      conversationType: conversation?.type ?? settings.conversationType,
      circleId: conversation?.circleId ?? settings.circleId,
    );
  }

  @override
  Future<GroupHomeDto> getGroupHome(String conversationId) async {
    final conversation = _findConversation(conversationId);
    if (conversation == null) {
      return GroupHomeDto();
    }
    final members = _ensureMembersCache(conversationId);
    final current = members.firstWhere(
      (member) => member.isCurrentUser,
      orElse: () =>
          members.isNotEmpty ? members.first : ChatConversationMemberDto(),
    );
    final canManage = current.role == 'owner' || current.role == 'admin';
    final canDissolve =
        current.role == 'owner' && conversation.circleId.trim().isEmpty;
    final resolvedMemberCount = members.isNotEmpty
        ? members.length
        : conversation.memberCount;
    return GroupHomeDto(
      conversationId: conversation.id,
      title: conversation.title,
      avatarUrl: conversation.avatarUrl,
      groupAvatarVersion: conversation.groupAvatarVersion,
      circleId: conversation.circleId,
      circleGroupId: conversation.circleGroupId ?? '',
      sourceCircleTitle: conversation.circleId,
      memberCount: resolvedMemberCount,
      capabilities: const <String>['album', 'file', 'event', 'member'],
      originType: conversation.originType,
      bindingType: conversation.bindingType,
      lifecyclePolicy: conversation.lifecyclePolicy,
      canManageMembers: canManage,
      canDissolve: canDissolve,
    );
  }

  @override
  Future<void> updateGroupSettings(
    String conversationId,
    ChatGroupSettingsDto settings,
  ) async {
    _settingsCache[conversationId] = settings;
  }

  @override
  Future<void> transferOwnership(
    String conversationId,
    String newOwnerId,
  ) async {
    final members = _ensureMembersCache(conversationId);
    _membersCache[conversationId] = members
        .map((member) {
          if (member.userId == newOwnerId) {
            return member.copyWith(role: 'owner');
          }
          if (member.role == 'owner') {
            return member.copyWith(role: 'member');
          }
          return member;
        })
        .toList(growable: true);
  }

  @override
  Future<void> updateGroupAdmins(
    String conversationId,
    List<String> adminIds,
  ) async {
    final members = _ensureMembersCache(conversationId);
    _membersCache[conversationId] = members
        .map((member) {
          if (member.role == 'owner') {
            return member;
          }
          return member.copyWith(
            role: adminIds.contains(member.userId) ? 'admin' : 'member',
          );
        })
        .toList(growable: true);
  }

  @override
  Future<void> dissolveConversation(String conversationId) async {
    _conversationCache.removeWhere(
      (conversation) => conversation.id == conversationId,
    );
    _membersCache.remove(conversationId);
    _messagesCache.remove(conversationId);
    _settingsCache.remove(conversationId);
    _inboxOverrides.remove(conversationId);
    _contactGroupConversationIds.remove(conversationId);
  }
}

String _defaultOriginType(
  String type,
  String? circleId,
  String? circleGroupId,
) {
  if (type != 'group') {
    return 'direct_init';
  }
  if ((circleGroupId ?? '').trim().isNotEmpty) {
    return 'circle_self_built_group';
  }
  if ((circleId ?? '').trim().isNotEmpty) {
    return 'circle_default_group';
  }
  return 'ad_hoc_group';
}

String _defaultBindingType(String? circleId, String? circleGroupId) {
  if ((circleGroupId ?? '').trim().isNotEmpty) {
    return 'circle_group';
  }
  if ((circleId ?? '').trim().isNotEmpty) {
    return 'circle';
  }
  return 'none';
}

String _defaultLifecyclePolicy(String? circleId, String? circleGroupId) {
  if ((circleGroupId ?? '').trim().isNotEmpty ||
      (circleId ?? '').trim().isNotEmpty) {
    return 'bound_to_circle';
  }
  return 'persistent';
}

DateTime? _parseIso(String value) {
  final normalized = value.trim();
  if (normalized.isEmpty) {
    return null;
  }
  return DateTime.tryParse(normalized);
}

String _firstNonEmpty(String a, String b, String c) {
  for (final value in <String>[a, b, c]) {
    final trimmed = value.trim();
    if (trimmed.isNotEmpty) {
      return trimmed;
    }
  }
  return '';
}

List<String> _firstTwoNonEmpty(String a, [String b = '']) {
  final out = <String>[];
  for (final value in <String>[a, b]) {
    final trimmed = value.trim();
    if (trimmed.isNotEmpty && !out.contains(trimmed)) {
      out.add(trimmed);
    }
    if (out.length == 2) {
      break;
    }
  }
  return List<String>.unmodifiable(out);
}
