import 'package:http/http.dart' as http;
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_inbox_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/services/chat/mock/chat_mock_data.dart';

/// Chat 域 Repository：会话、消息、成员、联系人等业务对象入口。
/// 接口与 contracts/metadata/messages/conversation/service.yaml 17 个 API 一一对应。
abstract class ChatRepository {
  // ── 会话 ────────────────────────────────────────────────────────────────────
  Future<List<ChatInboxDto>> listInbox({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<List<Map<String, dynamic>>> listConversations({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<Map<String, dynamic>> createConversation({
    required String type,
    String? title,
    String? circleId,
    int? maxGroupSize,
  });

  Future<Map<String, dynamic>> getConversation(String conversationId);

  // ── 消息 ────────────────────────────────────────────────────────────────────
  Future<List<Map<String, dynamic>>> listMessages({
    required String conversationId,
    String? before,
    int limit = CloudApiDefaults.pageLimit,
  });

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
  });

  Future<void> recallMessage({
    required String conversationId,
    required String messageId,
  });

  Future<Map<String, dynamic>> syncMessages({
    required String conversationId,
    required int lastSeq,
    int limit = CloudApiDefaults.syncMessagesLimit,
  });

  // ── 已读回执 ──────────────────────────────────────────────────────────────
  Future<void> markAsRead({
    required String conversationId,
    required String messageId,
  });

  Future<List<Map<String, dynamic>>> getReceipts({
    required String conversationId,
    required String messageId,
  });

  // ── 成员管理 ──────────────────────────────────────────────────────────────
  Future<List<Map<String, dynamic>>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
    String? role,
  });

  Future<void> addMembers({
    required String conversationId,
    required List<String> userIds,
  });

  Future<void> removeMember({
    required String conversationId,
    required String userId,
  });

  // ── 助手参与 ──────────────────────────────────────────────────────────────
  Future<void> inviteAssistant({
    required String conversationId,
    String? skillId,
  });

  Future<void> removeAssistant({required String conversationId});

  // ── 用户设置 ──────────────────────────────────────────────────────────────
  Future<void> updateConversationSettings({
    required String conversationId,
    bool? muted,
    bool? pinned,
  });

  // ── 联系人 ──────────────────────────────────────────────────────────────
  Future<List<Map<String, dynamic>>> listContacts({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<List<Map<String, dynamic>>> searchContacts({required String query});

  // ── 会话时间戳索引（端云同步） ─────────────────────────────────────────────
  Future<List<Map<String, dynamic>>> getConversationTimestamps();

  Future<List<Map<String, dynamic>>> batchGetConversations(List<String> ids);

  // ── 群管理 ──────────────────────────────────────────────────────────────────
  Future<Map<String, dynamic>> getGroupSettings(String conversationId);

  Future<void> updateGroupSettings(
    String conversationId,
    Map<String, dynamic> settings,
  );

  Future<void> transferOwnership(String conversationId, String newOwnerId);

  Future<void> updateGroupAdmins(String conversationId, List<String> adminIds);

  Future<void> dissolveConversation(String conversationId);
}

// ═══════════════════════════════════════════════════════════════════════════════
// Mock 实现
// ═══════════════════════════════════════════════════════════════════════════════

class MockChatRepository implements ChatRepository {
  int _seqCounter = 100;

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

  @override
  Future<List<ChatInboxDto>> listInbox({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final rows = ChatMockData.inboxItems;
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
    return ChatMockData.conversations;
  }

  @override
  Future<Map<String, dynamic>> createConversation({
    required String type,
    String? title,
    String? circleId,
    int? maxGroupSize,
  }) async {
    return {
      '_id': 'conv_new_${DateTime.now().millisecondsSinceEpoch}',
      'type': type,
      'title': title ?? '',
      'circleId': circleId,
      'maxGroupSize': maxGroupSize ?? 1000,
      'status': 'active',
      'memberCount': 1,
      'maxSeq': 0,
      'createdAt': DateTime.now().toIso8601String(),
      'updatedAt': DateTime.now().toIso8601String(),
    };
  }

  @override
  Future<Map<String, dynamic>> getConversation(String conversationId) async {
    return ChatMockData.conversations.firstWhere(
      (c) => c['_id'] == conversationId,
      orElse: () => ChatMockData.conversations.first,
    );
  }

  @override
  Future<List<Map<String, dynamic>>> listMessages({
    required String conversationId,
    String? before,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return ChatMockData.messagesFor(conversationId);
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
  Future<List<Map<String, dynamic>>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
    String? role,
  }) async {
    if (!_membersCache.containsKey(conversationId)) {
      _membersCache[conversationId] = ChatMockData.membersFor(
        conversationId,
      ).map((m) => Map<String, dynamic>.from(m)).toList();
    }
    return _membersCache[conversationId]!
        .map((m) => Map<String, dynamic>.from(m))
        .toList();
  }

  @override
  Future<void> addMembers({
    required String conversationId,
    required List<String> userIds,
  }) async {}

  @override
  Future<void> removeMember({
    required String conversationId,
    required String userId,
  }) async {}

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
  Future<List<Map<String, dynamic>>> listContacts({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return ChatMockData.contacts;
  }

  @override
  Future<List<Map<String, dynamic>>> searchContacts({
    required String query,
  }) async {
    return ChatMockData.contacts
        .where(
          (c) =>
              (c['displayName'] as String?)?.toLowerCase().contains(
                query.toLowerCase(),
              ) ??
              false,
        )
        .toList();
  }

  @override
  Future<List<Map<String, dynamic>>> getConversationTimestamps() async {
    return ChatMockData.conversations.map((c) {
      return {
        'id': c['_id'] ?? c['id'],
        'updatedAt': c['updatedAt'] ?? DateTime.now().toIso8601String(),
        'type': c['type'] ?? 'direct',
      };
    }).toList();
  }

  @override
  Future<List<Map<String, dynamic>>> batchGetConversations(
    List<String> ids,
  ) async {
    return ChatMockData.conversations
        .where((c) => ids.contains(c['_id'] ?? c['id']))
        .toList();
  }

  @override
  Future<Map<String, dynamic>> getGroupSettings(String conversationId) async {
    return Map<String, dynamic>.from(
      _settingsCache[conversationId] ?? _defaultSettings,
    );
  }

  @override
  Future<void> updateGroupSettings(
    String conversationId,
    Map<String, dynamic> settings,
  ) async {
    final current = Map<String, dynamic>.from(
      _settingsCache[conversationId] ?? _defaultSettings,
    );
    current.addAll(settings);
    _settingsCache[conversationId] = current;
  }

  @override
  Future<void> transferOwnership(
    String conversationId,
    String newOwnerId,
  ) async {
    final members = await listMembers(conversationId: conversationId);
    for (final m in members) {
      if (m['isCurrentUser'] == true) m['role'] = 'member';
      if (m['userId'] == newOwnerId) m['role'] = 'owner';
    }
    _membersCache[conversationId] = members;
  }

  @override
  Future<void> updateGroupAdmins(
    String conversationId,
    List<String> adminIds,
  ) async {
    final members = await listMembers(conversationId: conversationId);
    for (final m in members) {
      if (m['role'] == 'owner') continue;
      m['role'] = adminIds.contains(m['userId']) ? 'admin' : 'member';
    }
    _membersCache[conversationId] = members;
  }

  @override
  Future<void> dissolveConversation(String conversationId) async {}
}

// ═══════════════════════════════════════════════════════════════════════════════
// Remote 实现
// ═══════════════════════════════════════════════════════════════════════════════

class RemoteChatRepository implements ChatRepository {
  RemoteChatRepository({
    CloudHttpClient? httpClient,
    http.Client? client,
    String? baseUrl,
  }) : _httpClient =
           httpClient ?? CloudHttpClient(client: client ?? http.Client()),
       _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim();

  final CloudHttpClient _httpClient;
  final String _baseUrl;

  Uri _uri(String path, {Map<String, String>? queryParameters}) {
    return Uri.parse(
      '$_baseUrl$path',
    ).replace(queryParameters: queryParameters);
  }

  Map<String, String> _headersForSurface(
    AppUiSurface surface, {
    required String operationId,
    required String legacyPageId,
  }) {
    return CloudRequestHeaders.forSurfaceOperation(
      surfaceId: surface.id,
      routeId: surface.routeId,
      operationId: operationId,
      legacyPageId: legacyPageId,
    );
  }

  String _contextForSurface(
    AppUiSurface surface, {
    required String operationId,
  }) {
    return CloudRequestHeaders.contextForSurfaceOperation(
      surfaceId: surface.id,
      operationId: operationId,
    );
  }

  // ── 会话 ──────────────────────────────────────────────────────────────────

  @override
  Future<List<ChatInboxDto>> listInbox({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final uri = _uri(
      ChatApiMetadata.listInboxPath,
      queryParameters: <String, String>{
        if (cursor != null && cursor.isNotEmpty) 'cursor': cursor,
        'limit': '$limit',
      },
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: _headersForSurface(
        AppUiSurfaces.chatList,
        operationId: ChatApiMetadata.listInboxOperation,
        legacyPageId: ChatRequestPageIds.listInbox,
      ),
    );
    final page = CloudResponseDecoder.asCursorPage(
      decoded,
      context: _contextForSurface(
        AppUiSurfaces.chatList,
        operationId: ChatApiMetadata.listInboxOperation,
      ),
    );
    return page.items.map(ChatInboxDto.fromMap).toList(growable: false);
  }

  @override
  Future<List<Map<String, dynamic>>> listConversations({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final uri = _uri(
      ChatApiMetadata.listConversationsPath,
      queryParameters: <String, String>{
        if (cursor != null && cursor.isNotEmpty) 'cursor': cursor,
        'limit': '$limit',
      },
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: _headersForSurface(
        AppUiSurfaces.chatList,
        operationId: ChatApiMetadata.listConversationsOperation,
        legacyPageId: ChatRequestPageIds.listConversations,
      ),
    );
    return CloudResponseDecoder.asCursorPage(
      decoded,
      context: _contextForSurface(
        AppUiSurfaces.chatList,
        operationId: ChatApiMetadata.listConversationsOperation,
      ),
    ).items;
  }

  @override
  Future<Map<String, dynamic>> createConversation({
    required String type,
    String? title,
    String? circleId,
    int? maxGroupSize,
  }) async {
    final uri = _uri(ChatApiMetadata.createConversationPath);
    return await _httpClient.postJson(
      uri,
      headers: _headersForSurface(
        AppUiSurfaces.chatList,
        operationId: ChatApiMetadata.createConversationOperation,
        legacyPageId: ChatRequestPageIds.createConversation,
      ),
      body: {
        'type': type,
        'title': ?title,
        'circleId': ?circleId,
        'maxGroupSize': ?maxGroupSize,
      },
    );
  }

  @override
  Future<Map<String, dynamic>> getConversation(String conversationId) async {
    final uri = _uri(
      ChatApiMetadata.getConversationPath(conversationId: conversationId),
    );
    return await _httpClient.getJson(
      uri,
      headers: _headersForSurface(
        AppUiSurfaces.chatDetail,
        operationId: ChatApiMetadata.getConversationOperation,
        legacyPageId: ChatRequestPageIds.getConversation,
      ),
    );
  }

  // ── 消息 ──────────────────────────────────────────────────────────────────

  @override
  Future<List<Map<String, dynamic>>> listMessages({
    required String conversationId,
    String? before,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final uri = _uri(
      ChatApiMetadata.listMessagesPath(conversationId: conversationId),
      queryParameters: <String, String>{
        if (before != null && before.isNotEmpty) 'before': before,
        'limit': '$limit',
      },
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: _headersForSurface(
        AppUiSurfaces.chatDetail,
        operationId: ChatApiMetadata.listMessagesOperation,
        legacyPageId: ChatRequestPageIds.listMessages,
      ),
    );
    return CloudResponseDecoder.asCursorPage(
      decoded,
      context: _contextForSurface(
        AppUiSurfaces.chatDetail,
        operationId: ChatApiMetadata.listMessagesOperation,
      ),
    ).items;
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
    final uri = _uri(
      ChatApiMetadata.sendMessagePath(conversationId: conversationId),
    );
    return await _httpClient.postJson(
      uri,
      headers: _headersForSurface(
        AppUiSurfaces.chatDetail,
        operationId: ChatApiMetadata.sendMessageOperation,
        legacyPageId: ChatRequestPageIds.sendMessage,
      ),
      body: {
        'type': type,
        'content': content,
        'clientMsgId': clientMsgId,
        'mediaUrl': ?mediaUrl,
        'media': ?media,
        'cardPayload': ?cardPayload,
        'replyToMessageId': ?replyToMessageId,
        'mentions': ?mentions,
        'senderPersonaId': ?senderPersonaId,
        'senderProfileSubjectId': ?senderProfileSubjectId,
        'personaContextVersion': ?personaContextVersion,
      },
    );
  }

  @override
  Future<void> recallMessage({
    required String conversationId,
    required String messageId,
  }) async {
    final uri = _uri(
      ChatApiMetadata.recallMessagePath(
        conversationId: conversationId,
        messageId: messageId,
      ),
    );
    await _httpClient.postJson(
      uri,
      headers: _headersForSurface(
        AppUiSurfaces.chatDetail,
        operationId: ChatApiMetadata.recallMessageOperation,
        legacyPageId: ChatRequestPageIds.recallMessage,
      ),
      body: {},
    );
  }

  @override
  Future<Map<String, dynamic>> syncMessages({
    required String conversationId,
    required int lastSeq,
    int limit = CloudApiDefaults.syncMessagesLimit,
  }) async {
    final uri = _uri(
      ChatApiMetadata.syncMessagesPath(conversationId: conversationId),
    );
    return await _httpClient.postJson(
      uri,
      headers: _headersForSurface(
        AppUiSurfaces.chatDetail,
        operationId: ChatApiMetadata.syncMessagesOperation,
        legacyPageId: ChatRequestPageIds.syncMessages,
      ),
      body: {'lastSeq': lastSeq, 'limit': limit},
    );
  }

  // ── 已读回执 ──────────────────────────────────────────────────────────────

  @override
  Future<void> markAsRead({
    required String conversationId,
    required String messageId,
  }) async {
    final uri = _uri(
      ChatApiMetadata.markAsReadPath(
        conversationId: conversationId,
        messageId: messageId,
      ),
    );
    await _httpClient.postJson(
      uri,
      headers: _headersForSurface(
        AppUiSurfaces.chatDetail,
        operationId: ChatApiMetadata.markAsReadOperation,
        legacyPageId: ChatRequestPageIds.markAsRead,
      ),
      body: {},
    );
  }

  @override
  Future<List<Map<String, dynamic>>> getReceipts({
    required String conversationId,
    required String messageId,
  }) async {
    final uri = _uri(
      ChatApiMetadata.getReceiptsPath(
        conversationId: conversationId,
        messageId: messageId,
      ),
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: _headersForSurface(
        AppUiSurfaces.chatDetail,
        operationId: ChatApiMetadata.getReceiptsOperation,
        legacyPageId: ChatRequestPageIds.getReceipts,
      ),
    );
    final items = decoded['items'];
    if (items is List) {
      return items.cast<Map<String, dynamic>>();
    }
    return [];
  }

  // ── 成员管理 ──────────────────────────────────────────────────────────────

  @override
  Future<List<Map<String, dynamic>>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
    String? role,
  }) async {
    final uri = _uri(
      ChatApiMetadata.listMembersPath(conversationId: conversationId),
      queryParameters: <String, String>{
        if (cursor != null && cursor.isNotEmpty) 'cursor': cursor,
        'limit': '$limit',
        if (role != null && role.isNotEmpty) 'role': role,
      },
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: _headersForSurface(
        AppUiSurfaces.chatManage,
        operationId: ChatApiMetadata.listMembersOperation,
        legacyPageId: ChatRequestPageIds.listMembers,
      ),
    );
    final items = decoded['items'];
    if (items is List) {
      return items.cast<Map<String, dynamic>>();
    }
    return [];
  }

  @override
  Future<void> addMembers({
    required String conversationId,
    required List<String> userIds,
  }) async {
    final uri = _uri(
      ChatApiMetadata.addMembersPath(conversationId: conversationId),
    );
    await _httpClient.postJson(
      uri,
      headers: _headersForSurface(
        AppUiSurfaces.chatAddMembers,
        operationId: ChatApiMetadata.addMembersOperation,
        legacyPageId: ChatRequestPageIds.addMembers,
      ),
      body: {'userIds': userIds},
    );
  }

  @override
  Future<void> removeMember({
    required String conversationId,
    required String userId,
  }) async {
    final uri = _uri(
      ChatApiMetadata.removeMemberPath(
        conversationId: conversationId,
        userId: userId,
      ),
    );
    await _httpClient.deleteJson(
      uri,
      headers: _headersForSurface(
        AppUiSurfaces.chatManage,
        operationId: ChatApiMetadata.removeMemberOperation,
        legacyPageId: ChatRequestPageIds.removeMember,
      ),
    );
  }

  // ── 助手 ──────────────────────────────────────────────────────────────────

  @override
  Future<void> inviteAssistant({
    required String conversationId,
    String? skillId,
  }) async {
    final uri = _uri(
      ChatApiMetadata.inviteAssistantPath(conversationId: conversationId),
    );
    await _httpClient.postJson(
      uri,
      headers: _headersForSurface(
        AppUiSurfaces.chatDetail,
        operationId: ChatApiMetadata.inviteAssistantOperation,
        legacyPageId: ChatRequestPageIds.inviteAssistant,
      ),
      body: {'skillId': ?skillId},
    );
  }

  @override
  Future<void> removeAssistant({required String conversationId}) async {
    final uri = _uri(
      ChatApiMetadata.removeAssistantPath(conversationId: conversationId),
    );
    await _httpClient.deleteJson(
      uri,
      headers: _headersForSurface(
        AppUiSurfaces.chatDetail,
        operationId: ChatApiMetadata.removeAssistantOperation,
        legacyPageId: ChatRequestPageIds.removeAssistant,
      ),
    );
  }

  // ── 设置 ──────────────────────────────────────────────────────────────────

  @override
  Future<void> updateConversationSettings({
    required String conversationId,
    bool? muted,
    bool? pinned,
  }) async {
    final uri = _uri(
      ChatApiMetadata.updateConversationSettingsPath(
        conversationId: conversationId,
      ),
    );
    await _httpClient.patchJson(
      uri,
      headers: _headersForSurface(
        AppUiSurfaces.chatSettings,
        operationId: ChatApiMetadata.updateConversationSettingsOperation,
        legacyPageId: ChatRequestPageIds.updateConversationSettings,
      ),
      body: {'muted': ?muted, 'pinned': ?pinned},
    );
  }

  // ── 联系人 ──────────────────────────────────────────────────────────────

  @override
  Future<List<Map<String, dynamic>>> listContacts({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final uri = _uri(
      ChatApiMetadata.listContactsPath,
      queryParameters: <String, String>{
        if (cursor != null && cursor.isNotEmpty) 'cursor': cursor,
        'limit': '$limit',
      },
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: _headersForSurface(
        AppUiSurfaces.chatList,
        operationId: ChatApiMetadata.listContactsOperation,
        legacyPageId: ChatRequestPageIds.listContacts,
      ),
    );
    final items = decoded['items'];
    if (items is List) {
      return items.cast<Map<String, dynamic>>();
    }
    return [];
  }

  @override
  Future<List<Map<String, dynamic>>> searchContacts({
    required String query,
  }) async {
    final uri = _uri(
      ChatApiMetadata.searchContactsPath,
      queryParameters: <String, String>{'q': query},
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: _headersForSurface(
        AppUiSurfaces.chatList,
        operationId: ChatApiMetadata.searchContactsOperation,
        legacyPageId: ChatRequestPageIds.searchContacts,
      ),
    );
    final items = decoded['items'];
    if (items is List) {
      return items.cast<Map<String, dynamic>>();
    }
    return [];
  }

  // ── 会话时间戳索引 ──────────────────────────────────────────────────────────

  @override
  Future<List<Map<String, dynamic>>> getConversationTimestamps() async {
    final uri = _uri(ChatApiMetadata.listConversationTimestampsPath);
    final decoded = await _httpClient.getJson(
      uri,
      headers: _headersForSurface(
        AppUiSurfaces.chatList,
        operationId: ChatApiMetadata.listConversationTimestampsOperation,
        legacyPageId: ChatRequestPageIds.listConversationTimestamps,
      ),
    );
    final items = decoded['items'];
    if (items is List) {
      return items.cast<Map<String, dynamic>>();
    }
    return [];
  }

  @override
  Future<List<Map<String, dynamic>>> batchGetConversations(
    List<String> ids,
  ) async {
    final uri = _uri(ChatApiMetadata.batchGetConversationsPath);
    final decoded = await _httpClient.postJson(
      uri,
      headers: _headersForSurface(
        AppUiSurfaces.chatList,
        operationId: ChatApiMetadata.batchGetConversationsOperation,
        legacyPageId: ChatRequestPageIds.batchGetConversations,
      ),
      body: {'ids': ids},
    );
    final items = decoded['items'];
    if (items is List) {
      return items.cast<Map<String, dynamic>>();
    }
    return [];
  }

  // ── 群管理 ──────────────────────────────────────────────────────────────────

  @override
  Future<Map<String, dynamic>> getGroupSettings(String conversationId) async {
    final uri = _uri(
      ChatApiMetadata.getConversationPath(conversationId: conversationId),
    );
    return await _httpClient.getJson(
      uri,
      headers: _headersForSurface(
        AppUiSurfaces.chatSettings,
        operationId: ChatApiMetadata.getConversationOperation,
        legacyPageId: ChatRequestPageIds.getConversation,
      ),
    );
  }

  @override
  Future<void> updateGroupSettings(
    String conversationId,
    Map<String, dynamic> settings,
  ) async {
    final uri = _uri(
      ChatApiMetadata.updateConversationSettingsPath(
        conversationId: conversationId,
      ),
    );
    await _httpClient.patchJson(
      uri,
      headers: _headersForSurface(
        AppUiSurfaces.chatSettings,
        operationId: ChatApiMetadata.updateConversationSettingsOperation,
        legacyPageId: ChatRequestPageIds.updateConversationSettings,
      ),
      body: settings,
    );
  }

  @override
  Future<void> transferOwnership(
    String conversationId,
    String newOwnerId,
  ) async {
    final uri = _uri(
      ChatApiMetadata.transferOwnershipPath(conversationId: conversationId),
    );
    await _httpClient.patchJson(
      uri,
      headers: _headersForSurface(
        AppUiSurfaces.chatTransferOwnership,
        operationId: ChatApiMetadata.transferOwnershipOperation,
        legacyPageId: ChatRequestPageIds.transferOwnership,
      ),
      body: {'newOwnerId': newOwnerId},
    );
  }

  @override
  Future<void> updateGroupAdmins(
    String conversationId,
    List<String> adminIds,
  ) async {
    final uri = _uri(
      ChatApiMetadata.updateGroupAdminsPath(conversationId: conversationId),
    );
    await _httpClient.putJson(
      uri,
      headers: _headersForSurface(
        AppUiSurfaces.chatAdmins,
        operationId: ChatApiMetadata.updateGroupAdminsOperation,
        legacyPageId: ChatRequestPageIds.updateGroupAdmins,
      ),
      body: {'adminIds': adminIds},
    );
  }

  @override
  Future<void> dissolveConversation(String conversationId) async {
    final uri = _uri(
      ChatApiMetadata.dissolveConversationPath(conversationId: conversationId),
    );
    await _httpClient.deleteJson(
      uri,
      headers: _headersForSurface(
        AppUiSurfaces.chatManage,
        operationId: ChatApiMetadata.dissolveConversationOperation,
        legacyPageId: ChatRequestPageIds.dissolveConversation,
      ),
    );
  }
}
