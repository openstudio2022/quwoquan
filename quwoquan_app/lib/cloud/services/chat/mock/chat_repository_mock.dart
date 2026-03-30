import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_contact_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_contact_search_item_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_conversation_created_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_conversation_member_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_group_settings_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_inbox_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_message_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository_api.dart';
import 'package:quwoquan_app/cloud/services/chat/mock/chat_mock_data.dart';
import 'package:quwoquan_app/core/mock/prototype_mock_data.dart';
import 'package:quwoquan_app/core/models/search_models.dart';

class MockChatRepository implements ChatRepository {
  int _seqCounter = 100;
  final List<Map<String, dynamic>> _conversationCache = ChatMockData
      .conversations
      .map((conversation) => Map<String, dynamic>.from(conversation))
      .toList(growable: true);
  final Map<String, Map<String, dynamic>> _inboxOverrides = {
    for (final item in ChatMockData.inboxItems)
      ((item['conversationId'] ?? item['id'] ?? item['_id']) as String):
          Map<String, dynamic>.from(item),
  };

  // 实例级可变成员缓存（key: conversationId），首次访问时从 ChatMockData 深拷贝初始化
  // 使用实例级（非 static）保证测试隔离；在同一 ProviderContainer 内 Provider 返回同一实例，故应用内有效
  final Map<String, List<Map<String, dynamic>>> _membersCache = {};

  // 实例级可变设置缓存（key: conversationId）
  final Map<String, Map<String, dynamic>> _settingsCache = {};

  static const Map<String, dynamic> _defaultSettings = {
    'qrCodeJoinEnabled': true,
    'joinRequiresApproval': false,
    'nameEditableByAdminOnly': false,
    'privacyShieldAdminOnly': false,
  };

  static String _conversationIdOf(Map<String, dynamic> conversation) {
    return (conversation['_id'] ?? conversation['id'] ?? '').toString();
  }

  List<Map<String, dynamic>> _ensureMembersCache(String conversationId) {
    if (!_membersCache.containsKey(conversationId)) {
      _membersCache[conversationId] = ChatMockData.membersFor(
        conversationId,
      ).map((member) => Map<String, dynamic>.from(member)).toList();
    }
    return _membersCache[conversationId]!;
  }

  void _bumpMembersRosterAfterMemberChange(
    String conversationId,
    int memberCount,
  ) {
    final index = _conversationCache.indexWhere(
      (conversation) => _conversationIdOf(conversation) == conversationId,
    );
    if (index < 0) {
      return;
    }
    final cur = Map<String, dynamic>.from(_conversationCache[index]);
    final prevRev = (cur['membersRosterRevision'] as num?)?.toInt() ?? 0;
    _conversationCache[index] = <String, dynamic>{
      ...cur,
      'memberCount': memberCount,
      'membersRosterRevision': prevRev + 1,
      'updatedAt': DateTime.now().toIso8601String(),
    };
  }

  @override
  Future<List<ChatInboxDto>> listInbox({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final rows = _conversationCache
        .where((conversation) => conversation['status'] == 'active')
        .map((conversation) {
          final conversationId = _conversationIdOf(conversation);
          final override = _inboxOverrides[conversationId] ?? const {};
          return <String, dynamic>{...conversation, ...override};
        })
        .toList(growable: false);
    final capped = limit > 0 && limit < rows.length
        ? rows.take(limit).toList(growable: false)
        : rows;
    return capped.map(ChatInboxDto.fromMap).toList(growable: false);
  }

  @override
  Future<List<Map<String, dynamic>>> listConversations({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final rows = _conversationCache
        .where((conversation) => conversation['status'] == 'active')
        .map((conversation) => Map<String, dynamic>.from(conversation))
        .toList(growable: false);
    if (limit > 0 && limit < rows.length) {
      return rows.take(limit).toList(growable: false);
    }
    return rows;
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
          final title = (conversation['title'] ?? '').toString().toLowerCase();
          final preview = (conversation['lastMessagePreview'] ?? '')
              .toString()
              .toLowerCase();
          return title.contains(normalizedQuery) ||
              preview.contains(normalizedQuery);
        })
        .take(limit)
        .map((conversation) {
          final title = (conversation['title'] ?? '').toString();
          final preview = (conversation['lastMessagePreview'] ?? '').toString();
          final highlight = title.toLowerCase().contains(normalizedQuery)
              ? title
              : preview;
          return ConversationSearchItemView.fromMap(<String, dynamic>{
            ...conversation,
            'conversationId':
                conversation['conversationId'] ?? conversation['_id'],
            'highlightText': highlight,
            'matchedField': title.toLowerCase().contains(normalizedQuery)
                ? 'title'
                : 'last_message',
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
    int? maxGroupSize,
    List<String>? initialMemberIds,
  }) async {
    final conversationId = 'conv_new_${DateTime.now().millisecondsSinceEpoch}';
    final nowUtc = DateTime.now().toUtc();
    final now = nowUtc.toIso8601String();
    final conversation = <String, dynamic>{
      '_id': conversationId,
      'id': conversationId,
      'type': type,
      'title': title ?? '',
      'circleId': circleId,
      'circleGroupId': circleGroupId,
      'maxGroupSize': maxGroupSize ?? 500,
      'status': 'active',
      'memberCount': (initialMemberIds?.length ?? 0) + 1,
      'membersRosterRevision': 1,
      'maxSeq': 0,
      'createdAt': now,
      'updatedAt': now,
      'creatorId': ChatMockData.currentUserProfileId,
      'lastMessagePreview': '',
      'lastMessageTime': now,
    };
    _conversationCache.insert(0, conversation);
    _membersCache[conversationId] = [
      <String, dynamic>{
        'userId': ChatMockData.currentUserProfileId,
        'displayName': '我',
        'avatarUrl': ChatMockData.avatarFor(ChatMockData.currentUserProfileId),
        'role': 'owner',
        'isCurrentUser': true,
        'joinedAt': nowUtc.toIso8601String(),
      },
      for (var i = 0; i < (initialMemberIds?.length ?? 0); i++)
        <String, dynamic>{
          'userId': initialMemberIds![i],
          'displayName': ChatMockData.nameFor(initialMemberIds[i]),
          'avatarUrl': ChatMockData.avatarFor(initialMemberIds[i]),
          'role': 'member',
          'isCurrentUser': false,
          'joinedAt': nowUtc
              .add(Duration(milliseconds: i + 1))
              .toIso8601String(),
        },
    ];
    return ChatConversationCreatedDto.fromMap(conversation);
  }

  @override
  Future<Map<String, dynamic>> getConversation(String conversationId) async {
    return Map<String, dynamic>.from(
      _conversationCache.firstWhere(
        (conversation) => _conversationIdOf(conversation) == conversationId,
        orElse: () => _conversationCache.first,
      ),
    );
  }

  @override
  Future<void> updateConversationTitle(
    String conversationId,
    String title,
  ) async {
    final index = _conversationCache.indexWhere(
      (c) => _conversationIdOf(c) == conversationId,
    );
    if (index < 0) {
      return;
    }
    final cur = Map<String, dynamic>.from(_conversationCache[index]);
    cur['title'] = title;
    _conversationCache[index] = cur;
    final inbox = _inboxOverrides[conversationId];
    if (inbox != null) {
      _inboxOverrides[conversationId] = Map<String, dynamic>.from(inbox)
        ..['title'] = title;
    }
  }

  @override
  Future<List<ChatMessageDto>> listMessages({
    required String conversationId,
    String? before,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return ChatMockData.messagesFor(conversationId)
        .map(ChatMessageDto.fromMap)
        .toList(growable: false);
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
    for (final conversation in ChatMockData.conversations) {
      final conversationId =
          (conversation['_id'] ?? conversation['conversationId'] ?? '')
              .toString();
      final conversationTitle = conversation['title']?.toString();
      final conversationAvatarUrl = conversation['avatarUrl']?.toString();
      final messages = ChatMockData.messagesFor(conversationId);
      for (final message in messages) {
        final content = (message['content'] ?? '').toString();
        final senderName =
            (message['senderDisplayName'] ??
                    message['senderDisplayNameSnapshot'] ??
                    message['senderName'] ??
                    '')
                .toString();
        if (!content.toLowerCase().contains(normalizedQuery) &&
            !senderName.toLowerCase().contains(normalizedQuery)) {
          continue;
        }
        results.add(
          MessageSearchItemView.fromMap(<String, dynamic>{
            ...message,
            'conversationId': conversationId,
            'conversationTitle': conversationTitle,
            'conversationAvatarUrl': conversationAvatarUrl,
            'contentPreview': content,
            'highlightText': content.toLowerCase().contains(normalizedQuery)
                ? content
                : senderName,
            'matchedField': content.toLowerCase().contains(normalizedQuery)
                ? 'content'
                : 'sender',
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
  Future<Map<String, dynamic>> sendMessage({
    required String conversationId,
    required String type,
    required String content,
    String? mediaUrl,
    Map<String, dynamic>? media,
    Map<String, dynamic>? cardPayload,
    String? replyToMessageId,
    List<String>? mentions,
    String? senderPersonaId,
    String? senderProfileSubjectId,
    String? personaContextVersion,
    required String clientMsgId,
  }) async {
    _seqCounter++;
    return {
      'messageId': 'msg_mock_${DateTime.now().millisecondsSinceEpoch}',
      'seq': _seqCounter,
      'timestamp': DateTime.now().toIso8601String(),
    };
  }

  @override
  Future<void> recallMessage({
    required String conversationId,
    required String messageId,
  }) async {}

  @override
  Future<Map<String, dynamic>> syncMessages({
    required String conversationId,
    required int lastSeq,
    int limit = CloudApiDefaults.syncMessagesLimit,
  }) async {
    final msgs = ChatMockData.messagesFor(conversationId);
    return {'messages': msgs, 'hasMore': false};
  }

  @override
  Future<void> markAsRead({
    required String conversationId,
    required String messageId,
  }) async {}

  @override
  Future<List<Map<String, dynamic>>> getReceipts({
    required String conversationId,
    required String messageId,
  }) async {
    return [];
  }

  @override
  Future<List<ChatConversationMemberDto>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
    String? role,
    String? sort,
  }) async {
    var rows = _ensureMembersCache(conversationId)
        .map((m) => ChatConversationMemberDto.fromMap(m))
        .toList();
    rows = sortChatMemberDtos(rows, sort);
    if (role != null && role.isNotEmpty) {
      rows = rows.where((m) => m.role == role).toList();
    }
    if (limit > 0 && rows.length > limit) {
      rows = rows.take(limit).toList();
    }
    return rows;
  }

  @override
  Future<void> addMembers({
    required String conversationId,
    required List<String> userIds,
  }) async {
    final members = _ensureMembersCache(conversationId);
    final existingIds = members
        .map((member) => (member['userId'] ?? '').toString())
        .toSet();
    var maxJoinedMs = 0;
    for (final m in members) {
      final d = DateTime.tryParse((m['joinedAt'] ?? '').toString());
      if (d != null && d.millisecondsSinceEpoch > maxJoinedMs) {
        maxJoinedMs = d.millisecondsSinceEpoch;
      }
    }
    var step = 0;
    for (final userId in userIds) {
      if (existingIds.contains(userId)) {
        continue;
      }
      step++;
      final joinedAt = DateTime.fromMillisecondsSinceEpoch(
        maxJoinedMs + step,
        isUtc: true,
      ).toIso8601String();
      members.add(<String, dynamic>{
        'userId': userId,
        'displayName': ChatMockData.nameFor(userId),
        'avatarUrl': ChatMockData.avatarFor(userId),
        'role': 'member',
        'isCurrentUser': false,
        'joinedAt': joinedAt,
      });
    }
    if (step > 0) {
      _bumpMembersRosterAfterMemberChange(conversationId, members.length);
    }
  }

  @override
  Future<void> removeMember({
    required String conversationId,
    required String userId,
  }) async {
    final members = _ensureMembersCache(conversationId)
      ..removeWhere((member) => member['userId'] == userId);
    _bumpMembersRosterAfterMemberChange(conversationId, members.length);
  }

  @override
  Future<void> inviteAssistant({
    required String conversationId,
    String? skillId,
  }) async {}

  @override
  Future<void> removeAssistant({required String conversationId}) async {}

  @override
  Future<void> updateConversationSettings({
    required String conversationId,
    bool? muted,
    bool? pinned,
  }) async {}

  @override
  Future<List<ChatContactRowDto>> listContacts({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return PrototypeMockData.chatMockContacts
        .map(ChatContactRowDto.fromMap)
        .take(limit)
        .toList(growable: false);
  }

  @override
  Future<List<Map<String, dynamic>>> listContactTabCircles({
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return ChatMockData.contactTabCircles
        .take(limit)
        .map((e) => Map<String, dynamic>.from(e))
        .toList(growable: false);
  }

  @override
  Future<List<Map<String, dynamic>>> listContactTabFunGroups({
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return ChatMockData.contactTabFunGroups
        .take(limit)
        .map((e) => Map<String, dynamic>.from(e))
        .toList(growable: false);
  }

  @override
  Future<List<String>> listMemberUserIds(String conversationId) async {
    return ChatMockData.membersFor(conversationId)
        .map((m) => m['userId']?.toString() ?? '')
        .where((id) => id.isNotEmpty)
        .toList(growable: false);
  }

  @override
  Future<List<ChatContactSearchItemDto>> searchContacts({
    required String query,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final normalizedQuery = query.trim().toLowerCase();
    return PrototypeMockData.chatMockContacts
        .where(
          (c) =>
              (c['displayName'] as String?)?.toLowerCase().contains(
                normalizedQuery,
              ) ??
              false,
        )
        .take(limit)
        .map((contact) {
          final displayName = (contact['displayName'] ?? '').toString();
          final matchedConversation = ChatMockData.conversations.firstWhere(
            (conversation) =>
                (conversation['type'] == 'direct' ||
                    conversation['type'] == 'encrypted') &&
                (conversation['title']?.toString().trim() == displayName),
            orElse: () => <String, dynamic>{},
          );
          return ChatContactSearchItemDto.fromMap(<String, dynamic>{
            ...contact,
            'contactId': contact['userId'],
            'conversationId':
                matchedConversation['_id'] ?? matchedConversation['id'] ?? '',
            'conversationType': matchedConversation['type'] ?? 'direct',
            'subtitle': '联系人',
            'highlightText': displayName,
            'matchedField': 'displayName',
          });
        })
        .toList(growable: false);
  }

  @override
  Future<List<Map<String, dynamic>>> getConversationTimestamps() async {
    return _conversationCache
        .where((conversation) => conversation['status'] == 'active')
        .map((c) {
          return {
            'id': c['_id'] ?? c['id'],
            'updatedAt': c['updatedAt'] ?? DateTime.now().toIso8601String(),
            'type': c['type'] ?? 'direct',
          };
        })
        .toList();
  }

  @override
  Future<List<Map<String, dynamic>>> batchGetConversations(
    List<String> ids,
  ) async {
    return _conversationCache
        .where((c) => ids.contains(c['_id'] ?? c['id']))
        .toList();
  }

  @override
  Future<ChatGroupSettingsDto> getGroupSettings(String conversationId) async {
    final conversation = await getConversation(conversationId);
    final merged = Map<String, dynamic>.from(conversation)
      ..addAll(_settingsCache[conversationId] ?? _defaultSettings);
    return ChatGroupSettingsDto.fromMap(merged);
  }

  @override
  Future<void> updateGroupSettings(
    String conversationId,
    ChatGroupSettingsDto settings,
  ) async {
    _settingsCache[conversationId] = <String, dynamic>{
      'qrCodeJoinEnabled': settings.qrCodeJoinEnabled,
      'joinRequiresApproval': settings.joinRequiresApproval,
      'nameEditableByAdminOnly': settings.nameEditableByAdminOnly,
      'privacyShieldAdminOnly': settings.privacyShieldAdminOnly,
    };
  }

  @override
  Future<void> transferOwnership(
    String conversationId,
    String newOwnerId,
  ) async {
    final members = await listMembers(conversationId: conversationId);
    final asMaps = members.map((m) => m.toMap()).toList();
    for (final m in asMaps) {
      if (m['isCurrentUser'] == true) m['role'] = 'member';
      if (m['userId'] == newOwnerId) m['role'] = 'owner';
    }
    _membersCache[conversationId] = asMaps;
  }

  @override
  Future<void> updateGroupAdmins(
    String conversationId,
    List<String> adminIds,
  ) async {
    final members = await listMembers(conversationId: conversationId);
    final asMaps = members.map((m) => m.toMap()).toList();
    for (final m in asMaps) {
      if (m['role'] == 'owner') continue;
      m['role'] = adminIds.contains(m['userId']) ? 'admin' : 'member';
    }
    _membersCache[conversationId] = asMaps;
  }

  @override
  Future<void> dissolveConversation(String conversationId) async {
    _conversationCache.removeWhere(
      (conversation) => _conversationIdOf(conversation) == conversationId,
    );
    _membersCache.remove(conversationId);
    _settingsCache.remove(conversationId);
    _inboxOverrides.remove(conversationId);
  }
}
