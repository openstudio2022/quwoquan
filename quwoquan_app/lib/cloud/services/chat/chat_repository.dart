import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/services/chat/mock/chat_mock_data.dart';

/// Chat 域 Repository：会话、消息、成员、联系人等业务对象入口。
/// 接口与 contracts/metadata/messages/conversation/service.yaml 17 个 API 一一对应。
abstract class ChatRepository {
  // ── 会话 ────────────────────────────────────────────────────────────────────
  Future<List<Map<String, dynamic>>> listConversations({
    String? cursor,
    int limit = 20,
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
    int limit = 20,
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
    required String clientMsgId,
  });

  Future<void> recallMessage({
    required String conversationId,
    required String messageId,
  });

  Future<Map<String, dynamic>> syncMessages({
    required String conversationId,
    required int lastSeq,
    int limit = 500,
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
    int limit = 20,
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
    int limit = 20,
  });

  Future<List<Map<String, dynamic>>> searchContacts({required String query});
}

// ═══════════════════════════════════════════════════════════════════════════════
// Mock 实现
// ═══════════════════════════════════════════════════════════════════════════════

class MockChatRepository implements ChatRepository {
  int _seqCounter = 100;

  @override
  Future<List<Map<String, dynamic>>> listConversations({
    String? cursor,
    int limit = 20,
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
    int limit = 20,
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
    int limit = 500,
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
    int limit = 20,
    String? role,
  }) async {
    return ChatMockData.membersFor(conversationId);
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
    int limit = 20,
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
              (c['displayName'] as String?)
                  ?.toLowerCase()
                  .contains(query.toLowerCase()) ??
              false,
        )
        .toList();
  }
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

  // ── 会话 ──────────────────────────────────────────────────────────────────

  @override
  Future<List<Map<String, dynamic>>> listConversations({
    String? cursor,
    int limit = 20,
  }) async {
    final uri = Uri.parse('$_baseUrl/v1/chat/conversations').replace(
      queryParameters: <String, String>{
        if (cursor != null && cursor.isNotEmpty) 'cursor': cursor,
        'limit': '$limit',
      },
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage('chat.conversation.list'),
    );
    return CloudResponseDecoder.asCursorPage(
      decoded,
      context: 'chat.conversation.list',
    ).items;
  }

  @override
  Future<Map<String, dynamic>> createConversation({
    required String type,
    String? title,
    String? circleId,
    int? maxGroupSize,
  }) async {
    final uri = Uri.parse('$_baseUrl/v1/chat/conversations');
    return await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage('chat.conversation.create'),
      body: {
        'type': type,
        if (title != null) 'title': title,
        if (circleId != null) 'circleId': circleId,
        if (maxGroupSize != null) 'maxGroupSize': maxGroupSize,
      },
    );
  }

  @override
  Future<Map<String, dynamic>> getConversation(String conversationId) async {
    final uri =
        Uri.parse('$_baseUrl/v1/chat/conversations/$conversationId');
    return await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage('chat.conversation.detail'),
    );
  }

  // ── 消息 ──────────────────────────────────────────────────────────────────

  @override
  Future<List<Map<String, dynamic>>> listMessages({
    required String conversationId,
    String? before,
    int limit = 20,
  }) async {
    final uri = Uri.parse(
      '$_baseUrl/v1/chat/conversations/$conversationId/messages',
    ).replace(
      queryParameters: <String, String>{
        if (before != null && before.isNotEmpty) 'before': before,
        'limit': '$limit',
      },
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage('chat.message.list'),
    );
    return CloudResponseDecoder.asCursorPage(
      decoded,
      context: 'chat.message.list',
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
    required String clientMsgId,
  }) async {
    final uri = Uri.parse(
      '$_baseUrl/v1/chat/conversations/$conversationId/messages',
    );
    return await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage('chat.message.send'),
      body: {
        'type': type,
        'content': content,
        'clientMsgId': clientMsgId,
        if (mediaUrl != null) 'mediaUrl': mediaUrl,
        if (media != null) 'media': media,
        if (cardPayload != null) 'cardPayload': cardPayload,
        if (replyToMessageId != null) 'replyToMessageId': replyToMessageId,
        if (mentions != null) 'mentions': mentions,
      },
    );
  }

  @override
  Future<void> recallMessage({
    required String conversationId,
    required String messageId,
  }) async {
    final uri = Uri.parse(
      '$_baseUrl/v1/chat/conversations/$conversationId/messages/$messageId/recall',
    );
    await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage('chat.message.recall'),
      body: {},
    );
  }

  @override
  Future<Map<String, dynamic>> syncMessages({
    required String conversationId,
    required int lastSeq,
    int limit = 500,
  }) async {
    final uri = Uri.parse(
      '$_baseUrl/v1/chat/conversations/$conversationId/sync',
    );
    return await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage('chat.message.sync'),
      body: {'lastSeq': lastSeq, 'limit': limit},
    );
  }

  // ── 已读回执 ──────────────────────────────────────────────────────────────

  @override
  Future<void> markAsRead({
    required String conversationId,
    required String messageId,
  }) async {
    final uri = Uri.parse(
      '$_baseUrl/v1/chat/conversations/$conversationId/messages/$messageId/read',
    );
    await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage('chat.message.read'),
      body: {},
    );
  }

  @override
  Future<List<Map<String, dynamic>>> getReceipts({
    required String conversationId,
    required String messageId,
  }) async {
    final uri = Uri.parse(
      '$_baseUrl/v1/chat/conversations/$conversationId/messages/$messageId/receipts',
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage('chat.message.receipts'),
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
    int limit = 20,
    String? role,
  }) async {
    final uri = Uri.parse(
      '$_baseUrl/v1/chat/conversations/$conversationId/members',
    ).replace(
      queryParameters: <String, String>{
        if (cursor != null && cursor.isNotEmpty) 'cursor': cursor,
        'limit': '$limit',
        if (role != null && role.isNotEmpty) 'role': role,
      },
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage('chat.member.list'),
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
    final uri = Uri.parse(
      '$_baseUrl/v1/chat/conversations/$conversationId/members',
    );
    await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage('chat.member.add'),
      body: {'userIds': userIds},
    );
  }

  @override
  Future<void> removeMember({
    required String conversationId,
    required String userId,
  }) async {
    final uri = Uri.parse(
      '$_baseUrl/v1/chat/conversations/$conversationId/members/$userId',
    );
    await _httpClient.deleteJson(
      uri,
      headers: CloudRequestHeaders.forPage('chat.member.remove'),
    );
  }

  // ── 助手 ──────────────────────────────────────────────────────────────────

  @override
  Future<void> inviteAssistant({
    required String conversationId,
    String? skillId,
  }) async {
    final uri = Uri.parse(
      '$_baseUrl/v1/chat/conversations/$conversationId/assistant',
    );
    await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage('chat.assistant.invite'),
      body: {if (skillId != null) 'skillId': skillId},
    );
  }

  @override
  Future<void> removeAssistant({required String conversationId}) async {
    final uri = Uri.parse(
      '$_baseUrl/v1/chat/conversations/$conversationId/assistant',
    );
    await _httpClient.deleteJson(
      uri,
      headers: CloudRequestHeaders.forPage('chat.assistant.remove'),
    );
  }

  // ── 设置 ──────────────────────────────────────────────────────────────────

  @override
  Future<void> updateConversationSettings({
    required String conversationId,
    bool? muted,
    bool? pinned,
  }) async {
    final uri = Uri.parse(
      '$_baseUrl/v1/chat/conversations/$conversationId/settings',
    );
    await _httpClient.patchJson(
      uri,
      headers: CloudRequestHeaders.forPage('chat.settings.update'),
      body: {
        if (muted != null) 'muted': muted,
        if (pinned != null) 'pinned': pinned,
      },
    );
  }

  // ── 联系人 ──────────────────────────────────────────────────────────────

  @override
  Future<List<Map<String, dynamic>>> listContacts({
    String? cursor,
    int limit = 20,
  }) async {
    final uri = Uri.parse('$_baseUrl/v1/chat/contacts').replace(
      queryParameters: <String, String>{
        if (cursor != null && cursor.isNotEmpty) 'cursor': cursor,
        'limit': '$limit',
      },
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage('chat.contacts.list'),
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
    final uri = Uri.parse('$_baseUrl/v1/chat/contacts/search').replace(
      queryParameters: <String, String>{'q': query},
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage('chat.contacts.search'),
    );
    final items = decoded['items'];
    if (items is List) {
      return items.cast<Map<String, dynamic>>();
    }
    return [];
  }
}
