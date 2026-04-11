import 'package:http/http.dart' as http;
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_contact_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_contact_search_item_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_conversation_created_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_conversation_member_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_group_settings_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_inbox_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_message_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/chat/models/chat_contact_tab_row_dtos.dart';
import 'package:quwoquan_app/cloud/chat/models/chat_conversation_timestamp_dto.dart';
import 'package:quwoquan_app/cloud/chat/models/chat_message_receipt_dto.dart';
import 'package:quwoquan_app/cloud/chat/models/conversation_dto.dart';
import 'package:quwoquan_app/cloud/chat/models/send_message_response.dart';
import 'package:quwoquan_app/cloud/chat/models/sync_response.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_group_settings_extensions.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository_api.dart';
import 'package:quwoquan_app/core/models/search_models.dart';

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
    required String clientPageId,
  }) {
    return CloudRequestHeaders.forSurfaceOperation(
      surfaceId: surface.id,
      routeId: surface.routeId,
      operationId: operationId,
      clientPageId: clientPageId,
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
        clientPageId: ChatRequestPageIds.listInbox,
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
  Future<List<ChatInboxDto>> listConversations({
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
        clientPageId: ChatRequestPageIds.listConversations,
      ),
    );
    final page = CloudResponseDecoder.asCursorPage(
      decoded,
      context: _contextForSurface(
        AppUiSurfaces.chatList,
        operationId: ChatApiMetadata.listConversationsOperation,
      ),
    );
    return page.items.map(ChatInboxDto.fromMap).toList(growable: false);
  }

  @override
  Future<List<ConversationSearchItemView>> searchConversations({
    required String query,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final uri = _uri(
      ChatApiMetadata.searchConversationsPath,
      queryParameters: <String, String>{'query': query, 'limit': '$limit'},
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: _headersForSurface(
        AppUiSurfaces.globalSearchSuggestions,
        operationId: ChatApiMetadata.searchConversationsOperation,
        clientPageId: ChatRequestPageIds.searchConversations,
      ),
    );
    final page = CloudResponseDecoder.asCursorPage(
      decoded,
      context: _contextForSurface(
        AppUiSurfaces.globalSearchSuggestions,
        operationId: ChatApiMetadata.searchConversationsOperation,
      ),
    );
    return page.items
        .map(ConversationSearchItemView.fromMap)
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
    final uri = _uri(ChatApiMetadata.createConversationPath);
    final body = <String, dynamic>{
      'type': type,
      if (title != null && title.isNotEmpty) 'title': title,
      if (circleId != null && circleId.isNotEmpty) 'circleId': circleId,
      if (circleGroupId != null && circleGroupId.isNotEmpty)
        'circleGroupId': circleGroupId,
      if (initialMemberIds != null && initialMemberIds.isNotEmpty)
        'initialMemberIds': initialMemberIds,
    };
    if (maxGroupSize != null) {
      body['maxGroupSize'] = maxGroupSize;
    }
    final decoded = await _httpClient.postJson(
      uri,
      headers: _headersForSurface(
        AppUiSurfaces.startGroupChat,
        operationId: ChatApiMetadata.createConversationOperation,
        clientPageId: ChatRequestPageIds.createConversation,
      ),
      body: body,
    );
    final map = decoded is Map<String, dynamic>
        ? decoded
        : Map<String, dynamic>.from(decoded as Map);
    return ChatConversationCreatedDto.fromMap(map);
  }

  @override
  Future<ConversationDto> getConversation(String conversationId) async {
    final uri = _uri(
      ChatApiMetadata.getConversationPath(conversationId: conversationId),
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: _headersForSurface(
        AppUiSurfaces.chatDetail,
        operationId: ChatApiMetadata.getConversationOperation,
        clientPageId: ChatRequestPageIds.getConversation,
      ),
    );
    return ConversationDto.fromMap(
      Map<String, dynamic>.from(decoded as Map),
    );
  }

  @override
  Future<void> updateConversationTitle(
    String conversationId,
    String title,
  ) async {
    final uri = _uri(
      ChatApiMetadata.getConversationPath(conversationId: conversationId),
    );
    await _httpClient.patchJson(
      uri,
      headers: _headersForSurface(
        AppUiSurfaces.chatSettings,
        operationId: ChatApiMetadata.getConversationOperation,
        clientPageId: ChatRequestPageIds.getConversation,
      ),
      body: <String, dynamic>{'title': title},
    );
  }

  // ── 消息 ──────────────────────────────────────────────────────────────────

  @override
  Future<List<ChatMessageDto>> listMessages({
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
        clientPageId: ChatRequestPageIds.listMessages,
      ),
    );
    final items = CloudResponseDecoder.asCursorPage(
      decoded,
      context: _contextForSurface(
        AppUiSurfaces.chatDetail,
        operationId: ChatApiMetadata.listMessagesOperation,
      ),
    ).items;
    return items.map(ChatMessageDto.fromMap).toList(growable: false);
  }

  @override
  Future<List<MessageSearchItemView>> searchMessages({
    required String query,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final uri = _uri(
      ChatApiMetadata.searchMessagesPath,
      queryParameters: <String, String>{'query': query, 'limit': '$limit'},
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: _headersForSurface(
        AppUiSurfaces.globalSearchSuggestions,
        operationId: ChatApiMetadata.searchMessagesOperation,
        clientPageId: ChatRequestPageIds.searchMessages,
      ),
    );
    final page = CloudResponseDecoder.asCursorPage(
      decoded,
      context: _contextForSurface(
        AppUiSurfaces.globalSearchSuggestions,
        operationId: ChatApiMetadata.searchMessagesOperation,
      ),
    );
    return page.items
        .map(MessageSearchItemView.fromMap)
        .toList(growable: false);
  }

  @override
  Future<SendMessageResponse> sendMessage({
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
    final decoded = await _httpClient.postJson(
      uri,
      headers: _headersForSurface(
        AppUiSurfaces.chatDetail,
        operationId: ChatApiMetadata.sendMessageOperation,
        clientPageId: ChatRequestPageIds.sendMessage,
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
    return SendMessageResponse.fromMap(
      Map<String, dynamic>.from(decoded as Map),
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
        clientPageId: ChatRequestPageIds.recallMessage,
      ),
      body: {},
    );
  }

  @override
  Future<SyncResponse> syncMessages({
    required String conversationId,
    required int lastSeq,
    int limit = CloudApiDefaults.syncMessagesLimit,
  }) async {
    final uri = _uri(
      ChatApiMetadata.syncMessagesPath(conversationId: conversationId),
    );
    final decoded = await _httpClient.postJson(
      uri,
      headers: _headersForSurface(
        AppUiSurfaces.chatDetail,
        operationId: ChatApiMetadata.syncMessagesOperation,
        clientPageId: ChatRequestPageIds.syncMessages,
      ),
      body: {'lastSeq': lastSeq, 'limit': limit},
    );
    return SyncResponse.fromMap(Map<String, dynamic>.from(decoded as Map));
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
        clientPageId: ChatRequestPageIds.markAsRead,
      ),
      body: {},
    );
  }

  @override
  Future<List<ChatMessageReceiptDto>> getReceipts({
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
        clientPageId: ChatRequestPageIds.getReceipts,
      ),
    );
    final items = decoded['items'];
    if (items is List) {
      return items
          .whereType<Map>()
          .map((m) => ChatMessageReceiptDto.fromMap(
                Map<String, dynamic>.from(m),
              ))
          .toList(growable: false);
    }
    return const [];
  }

  // ── 成员管理 ──────────────────────────────────────────────────────────────

  @override
  Future<List<ChatConversationMemberDto>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
    String? role,
    String? sort,
  }) async {
    final uri = _uri(
      ChatApiMetadata.listMembersPath(conversationId: conversationId),
      queryParameters: <String, String>{
        if (cursor != null && cursor.isNotEmpty) 'cursor': cursor,
        'limit': '$limit',
        if (role != null && role.isNotEmpty) 'role': role,
        'sort': sort ?? 'joined_asc',
      },
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: _headersForSurface(
        AppUiSurfaces.chatManage,
        operationId: ChatApiMetadata.listMembersOperation,
        clientPageId: ChatRequestPageIds.listMembers,
      ),
    );
    final items = decoded['items'];
    if (items is! List) {
      return [];
    }
    return items
        .whereType<Map<String, dynamic>>()
        .map(ChatConversationMemberDto.fromMap)
        .toList(growable: false);
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
        clientPageId: ChatRequestPageIds.addMembers,
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
        clientPageId: ChatRequestPageIds.removeMember,
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
        clientPageId: ChatRequestPageIds.inviteAssistant,
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
        clientPageId: ChatRequestPageIds.removeAssistant,
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
        clientPageId: ChatRequestPageIds.updateConversationSettings,
      ),
      body: {'muted': ?muted, 'pinned': ?pinned},
    );
  }

  // ── 联系人 ──────────────────────────────────────────────────────────────

  @override
  Future<List<ChatContactRowDto>> listContacts({
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
        clientPageId: ChatRequestPageIds.listContacts,
      ),
    );
    final items = decoded['items'];
    if (items is! List) {
      return [];
    }
    return items
        .whereType<Map<String, dynamic>>()
        .map(ChatContactRowDto.fromMap)
        .toList(growable: false);
  }

  @override
  Future<List<ChatContactTabCircleRowDto>> listContactTabCircles({
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return const [];
  }

  @override
  Future<List<ChatContactTabFunGroupRowDto>> listContactTabFunGroups({
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return const [];
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

  @override
  Future<List<ChatContactSearchItemDto>> searchContacts({
    required String query,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final uri = _uri(
      ChatApiMetadata.searchContactsPath,
      queryParameters: <String, String>{'query': query, 'limit': '$limit'},
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: _headersForSurface(
        AppUiSurfaces.globalSearchSuggestions,
        operationId: ChatApiMetadata.searchContactsOperation,
        clientPageId: ChatRequestPageIds.searchContacts,
      ),
    );
    final items = decoded['items'];
    if (items is! List) {
      return [];
    }
    return items
        .whereType<Map<String, dynamic>>()
        .map(ChatContactSearchItemDto.fromMap)
        .toList(growable: false);
  }

  // ── 会话时间戳索引 ──────────────────────────────────────────────────────────

  @override
  Future<List<ChatConversationTimestampDto>> getConversationTimestamps() async {
    final uri = _uri(ChatApiMetadata.listConversationTimestampsPath);
    final decoded = await _httpClient.getJson(
      uri,
      headers: _headersForSurface(
        AppUiSurfaces.chatList,
        operationId: ChatApiMetadata.listConversationTimestampsOperation,
        clientPageId: ChatRequestPageIds.listConversationTimestamps,
      ),
    );
    final items = decoded['items'];
    if (items is List) {
      return items
          .whereType<Map>()
          .map((m) => ChatConversationTimestampDto.fromMap(
                Map<String, dynamic>.from(m),
              ))
          .toList(growable: false);
    }
    return const [];
  }

  @override
  Future<List<ConversationDto>> batchGetConversations(
    List<String> ids,
  ) async {
    final uri = _uri(ChatApiMetadata.batchGetConversationsPath);
    final decoded = await _httpClient.postJson(
      uri,
      headers: _headersForSurface(
        AppUiSurfaces.chatList,
        operationId: ChatApiMetadata.batchGetConversationsOperation,
        clientPageId: ChatRequestPageIds.batchGetConversations,
      ),
      body: {'ids': ids},
    );
    final items = decoded['items'];
    if (items is List) {
      return items
          .whereType<Map>()
          .map((m) => ConversationDto.fromMap(Map<String, dynamic>.from(m)))
          .toList(growable: false);
    }
    return const [];
  }

  // ── 群管理 ──────────────────────────────────────────────────────────────────

  @override
  Future<ChatGroupSettingsDto> getGroupSettings(String conversationId) async {
    final uri = _uri(
      ChatApiMetadata.getConversationPath(conversationId: conversationId),
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: _headersForSurface(
        AppUiSurfaces.chatSettings,
        operationId: ChatApiMetadata.getConversationOperation,
        clientPageId: ChatRequestPageIds.getConversation,
      ),
    );
    return ChatGroupSettingsDto.fromMap(
      Map<String, dynamic>.from(decoded as Map),
    );
  }

  @override
  Future<void> updateGroupSettings(
    String conversationId,
    ChatGroupSettingsDto settings,
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
        clientPageId: ChatRequestPageIds.updateConversationSettings,
      ),
      body: settings.toGroupSettingsPatchBody(),
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
        clientPageId: ChatRequestPageIds.transferOwnership,
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
        clientPageId: ChatRequestPageIds.updateGroupAdmins,
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
        clientPageId: ChatRequestPageIds.dissolveConversation,
      ),
    );
  }
}
