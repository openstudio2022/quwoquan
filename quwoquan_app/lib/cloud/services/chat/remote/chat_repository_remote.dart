// ignore_for_file: prefer_initializing_formals

import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_wire_json_types.dart';
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
import 'package:quwoquan_app/cloud/runtime/generated/chat/contact_home_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/group_home_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/message_home_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/selectable_group_conversation_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_api_metadata.g.dart';
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

part 'chat_repository_remote_decoders.dart';

/// 在 surface/operation 基础头之上合并当前用户与分身上下文（如 [CloudRequestHeaders.withPersonaContext]）。
typedef ChatRemoteMergeRequestContext =
    Future<Map<String, String>> Function(Map<String, String> baseHeaders);

class RemoteChatRepository implements ChatRepository {
  RemoteChatRepository({
    CloudHttpClient? httpClient,
    String? baseUrl,
    ChatRemoteMergeRequestContext? mergeRequestContext,
  }) : _httpClient = httpClient ?? CloudHttpClient(),
       _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim(),
       _mergeRequestContext = mergeRequestContext;

  final CloudHttpClient _httpClient;
  final String _baseUrl;
  final ChatRemoteMergeRequestContext? _mergeRequestContext;

  Uri _uri(String path, {Map<String, String>? queryParameters}) {
    return Uri.parse(
      '$_baseUrl$path',
    ).replace(queryParameters: queryParameters);
  }

  Future<Map<String, String>> _resolveHeaders(
    AppUiSurface surface, {
    required String operationId,
    required String clientPageId,
  }) async {
    final base = CloudRequestHeaders.forSurfaceOperation(
      surfaceId: surface.id,
      routeId: surface.routeId,
      operationId: operationId,
      clientPageId: clientPageId,
    );
    final merger = _mergeRequestContext;
    if (merger == null) {
      return base;
    }
    return merger(base);
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
      headers: await _resolveHeaders(
        AppUiSurfaces.chatList,
        operationId: ChatApiMetadata.listInboxOperation,
        clientPageId: ChatRequestPageIds.listInbox,
      ),
    );
    return _decodeCursorPageItems(
      decoded,
      context: _contextForSurface(
        AppUiSurfaces.chatList,
        operationId: ChatApiMetadata.listInboxOperation,
      ),
      fromMap: ChatInboxDto.fromMap,
    );
  }

  @override
  Future<List<MessageHomeRowDto>> listMessageHome({
    String filter = 'all',
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final uri = _uri(
      ChatApiMetadata.listMessageHomePath,
      queryParameters: <String, String>{
        'filter': filter,
        if (cursor != null && cursor.isNotEmpty) 'cursor': cursor,
        'limit': '$limit',
      },
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: await _resolveHeaders(
        AppUiSurfaces.chatList,
        operationId: ChatApiMetadata.listMessageHomeOperation,
        clientPageId: ChatRequestPageIds.listMessageHome,
      ),
    );
    return _decodeCursorPageItems(
      decoded,
      context: _contextForSurface(
        AppUiSurfaces.chatList,
        operationId: ChatApiMetadata.listMessageHomeOperation,
      ),
      fromMap: MessageHomeRowDto.fromMap,
    );
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
      headers: await _resolveHeaders(
        AppUiSurfaces.chatList,
        operationId: ChatApiMetadata.listConversationsOperation,
        clientPageId: ChatRequestPageIds.listConversations,
      ),
    );
    return _decodeCursorPageItems(
      decoded,
      context: _contextForSurface(
        AppUiSurfaces.chatList,
        operationId: ChatApiMetadata.listConversationsOperation,
      ),
      fromMap: ChatInboxDto.fromMap,
    );
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
      headers: await _resolveHeaders(
        AppUiSurfaces.globalSearchSuggestions,
        operationId: ChatApiMetadata.searchConversationsOperation,
        clientPageId: ChatRequestPageIds.searchConversations,
      ),
    );
    return _decodeCursorPageItems(
      decoded,
      context: _contextForSurface(
        AppUiSurfaces.globalSearchSuggestions,
        operationId: ChatApiMetadata.searchConversationsOperation,
      ),
      fromMap: ConversationSearchItemView.fromMap,
    );
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
    final uri = _uri(ChatApiMetadata.createConversationPath);
    final body = <String, dynamic>{
      'type': type,
      if (title != null && title.isNotEmpty) 'title': title,
      if (circleId != null && circleId.isNotEmpty) 'circleId': circleId,
      if (circleGroupId != null && circleGroupId.isNotEmpty)
        'circleGroupId': circleGroupId,
      if (originType != null && originType.isNotEmpty) 'originType': originType,
      if (bindingType != null && bindingType.isNotEmpty)
        'bindingType': bindingType,
      if (lifecyclePolicy != null && lifecyclePolicy.isNotEmpty)
        'lifecyclePolicy': lifecyclePolicy,
      if (initialMemberIds != null && initialMemberIds.isNotEmpty)
        'initialMemberIds': initialMemberIds,
    };
    if (maxGroupSize != null) {
      body['maxGroupSize'] = maxGroupSize;
    }
    final decoded = await _httpClient.postJson(
      uri,
      headers: await _resolveHeaders(
        AppUiSurfaces.startGroupChat,
        operationId: ChatApiMetadata.createConversationOperation,
        clientPageId: ChatRequestPageIds.createConversation,
      ),
      body: body,
    );
    final map = CloudResponseDecoder.asObject(
      decoded,
      context: ChatRequestPageIds.createConversation,
    );
    return ChatConversationCreatedDto.fromMap(map);
  }

  @override
  Future<ConversationDto> getConversation(String conversationId) async {
    final uri = _uri(
      ChatApiMetadata.getConversationPath(conversationId: conversationId),
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: await _resolveHeaders(
        AppUiSurfaces.chatDetail,
        operationId: ChatApiMetadata.getConversationOperation,
        clientPageId: ChatRequestPageIds.getConversation,
      ),
    );
    return ConversationDto.fromMap(
      CloudResponseDecoder.asObject(
        decoded,
        context: ChatRequestPageIds.getConversation,
      ),
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
      headers: await _resolveHeaders(
        AppUiSurfaces.chatSettings,
        operationId: ChatApiMetadata.updateConversationTitleOperation,
        clientPageId: ChatRequestPageIds.updateConversationTitle,
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
      headers: await _resolveHeaders(
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
      headers: await _resolveHeaders(
        AppUiSurfaces.globalSearchSuggestions,
        operationId: ChatApiMetadata.searchMessagesOperation,
        clientPageId: ChatRequestPageIds.searchMessages,
      ),
    );
    return _decodeCursorPageItems(
      decoded,
      context: _contextForSurface(
        AppUiSurfaces.globalSearchSuggestions,
        operationId: ChatApiMetadata.searchMessagesOperation,
      ),
      fromMap: MessageSearchItemView.fromMap,
    );
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
    final uri = _uri(
      ChatApiMetadata.sendMessagePath(conversationId: conversationId),
    );
    final decoded = await _httpClient.postJson(
      uri,
      headers: await _resolveHeaders(
        AppUiSurfaces.chatDetail,
        operationId: ChatApiMetadata.sendMessageOperation,
        clientPageId: ChatRequestPageIds.sendMessage,
      ),
      body: {
        'type': type,
        'content': content,
        'clientMsgId': clientMsgId,
        if (mediaUrl != null && mediaUrl.isNotEmpty) 'mediaUrl': mediaUrl,
        'media': ?media,
        'cardPayload': ?cardPayload,
        if (replyToMessageId != null && replyToMessageId.isNotEmpty)
          'replyToMessageId': replyToMessageId,
        if (mentions != null && mentions.isNotEmpty) 'mentions': mentions,
        if (senderSubAccountId != null && senderSubAccountId.isNotEmpty)
          'senderSubAccountId': senderSubAccountId,
        if (personaContextVersion != null && personaContextVersion.isNotEmpty)
          'personaContextVersion': personaContextVersion,
        if (senderDisplayNameSnapshot != null &&
            senderDisplayNameSnapshot.isNotEmpty)
          'senderDisplayNameSnapshot': senderDisplayNameSnapshot,
        if (senderAvatarUrlSnapshot != null &&
            senderAvatarUrlSnapshot.isNotEmpty)
          'senderAvatarUrlSnapshot': senderAvatarUrlSnapshot,
      },
    );
    return SendMessageResponse.fromMap(
      CloudResponseDecoder.asObject(
        decoded,
        context: ChatRequestPageIds.sendMessage,
      ),
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
      headers: await _resolveHeaders(
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
      headers: await _resolveHeaders(
        AppUiSurfaces.chatDetail,
        operationId: ChatApiMetadata.syncMessagesOperation,
        clientPageId: ChatRequestPageIds.syncMessages,
      ),
      body: {'lastSeq': lastSeq, 'limit': limit},
    );
    return SyncResponse.fromMap(
      CloudResponseDecoder.asObject(
        decoded,
        context: ChatRequestPageIds.syncMessages,
      ),
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
      headers: await _resolveHeaders(
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
      headers: await _resolveHeaders(
        AppUiSurfaces.chatDetail,
        operationId: ChatApiMetadata.getReceiptsOperation,
        clientPageId: ChatRequestPageIds.getReceipts,
      ),
    );
    return _decodeObjectItems(
      decoded,
      context: ChatRequestPageIds.getReceipts,
      fromMap: ChatMessageReceiptDto.fromMap,
    );
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
      headers: await _resolveHeaders(
        AppUiSurfaces.chatManage,
        operationId: ChatApiMetadata.listMembersOperation,
        clientPageId: ChatRequestPageIds.listMembers,
      ),
    );
    return _decodeObjectItems(
      decoded,
      context: ChatRequestPageIds.listMembers,
      fromMap: ChatConversationMemberDto.fromMap,
    );
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
      headers: await _resolveHeaders(
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
      headers: await _resolveHeaders(
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
      headers: await _resolveHeaders(
        AppUiSurfaces.chatDetail,
        operationId: ChatApiMetadata.inviteAssistantOperation,
        clientPageId: ChatRequestPageIds.inviteAssistant,
      ),
      body: {if (skillId != null && skillId.isNotEmpty) 'skillId': skillId},
    );
  }

  @override
  Future<void> removeAssistant({required String conversationId}) async {
    final uri = _uri(
      ChatApiMetadata.removeAssistantPath(conversationId: conversationId),
    );
    await _httpClient.deleteJson(
      uri,
      headers: await _resolveHeaders(
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
      headers: await _resolveHeaders(
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
      headers: await _resolveHeaders(
        AppUiSurfaces.chatList,
        operationId: ChatApiMetadata.listContactsOperation,
        clientPageId: ChatRequestPageIds.listContacts,
      ),
    );
    return _decodeObjectItems(
      decoded,
      context: ChatRequestPageIds.listContacts,
      fromMap: ChatContactRowDto.fromMap,
    );
  }

  @override
  Future<List<ContactHomeRowDto>> listContactHome({
    String filter = 'all',
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final uri = _uri(
      ChatApiMetadata.listContactHomePath,
      queryParameters: <String, String>{
        'filter': filter,
        if (cursor != null && cursor.isNotEmpty) 'cursor': cursor,
        'limit': '$limit',
      },
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: await _resolveHeaders(
        AppUiSurfaces.chatList,
        operationId: ChatApiMetadata.listContactHomeOperation,
        clientPageId: ChatRequestPageIds.listContactHome,
      ),
    );
    return _decodeCursorPageItems(
      decoded,
      context: _contextForSurface(
        AppUiSurfaces.chatList,
        operationId: ChatApiMetadata.listContactHomeOperation,
      ),
      fromMap: ContactHomeRowDto.fromMap,
    );
  }

  @override
  Future<List<ChatContactRowDto>> listGroupCandidates({
    String? conversationId,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final normalizedConversationId = conversationId?.trim() ?? '';
    final uri = _uri(
      ChatApiMetadata.listGroupCandidatesPath,
      queryParameters: <String, String>{
        if (normalizedConversationId.isNotEmpty)
          'conversationId': normalizedConversationId,
        'limit': '$limit',
      },
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: await _resolveHeaders(
        AppUiSurfaces.startGroupChat,
        operationId: ChatApiMetadata.listGroupCandidatesOperation,
        clientPageId: ChatRequestPageIds.listGroupCandidates,
      ),
    );
    return _decodeObjectItems(
      decoded,
      context: ChatRequestPageIds.listGroupCandidates,
      fromMap: ChatContactRowDto.fromMap,
    );
  }

  // ── 从群聊中选择联系人 ──────────────────────────────────────────────────────

  @override
  Future<List<SelectableGroupConversationRowDto>>
  listSelectableGroupConversations({
    String? query,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final normalizedQuery = query?.trim() ?? '';
    final uri = _uri(
      ChatApiMetadata.listSelectableGroupConversationsPath,
      queryParameters: <String, String>{
        if (normalizedQuery.isNotEmpty) 'query': normalizedQuery,
        'limit': '$limit',
      },
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: await _resolveHeaders(
        AppUiSurfaces.startGroupChat,
        operationId: ChatApiMetadata.listSelectableGroupConversationsOperation,
        clientPageId: ChatRequestPageIds.listSelectableGroupConversations,
      ),
    );
    return _decodeObjectItems(
      decoded,
      context: ChatRequestPageIds.listSelectableGroupConversations,
      fromMap: SelectableGroupConversationRowDto.fromMap,
    );
  }

  @override
  Future<List<ChatContactRowDto>> listSelectableGroupContactMembers({
    required String conversationId,
    String? query,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final normalizedQuery = query?.trim() ?? '';
    final uri = _uri(
      ChatApiMetadata.listSelectableGroupContactMembersPath(
        conversationId: conversationId,
      ),
      queryParameters: <String, String>{
        if (normalizedQuery.isNotEmpty) 'query': normalizedQuery,
        'limit': '$limit',
      },
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: await _resolveHeaders(
        AppUiSurfaces.startGroupChat,
        operationId: ChatApiMetadata.listSelectableGroupContactMembersOperation,
        clientPageId: ChatRequestPageIds.listSelectableGroupContactMembers,
      ),
    );
    return _decodeObjectItems(
      decoded,
      context: ChatRequestPageIds.listSelectableGroupContactMembers,
      fromMap: ChatContactRowDto.fromMap,
    );
  }

  @override
  Future<List<ChatContactTabCircleRowDto>> listContactTabCircles({
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final uri = _uri(
      CircleApiMetadata.listCirclesPath,
      queryParameters: <String, String>{'limit': '$limit'},
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: await _resolveHeaders(
        AppUiSurfaces.chatList,
        operationId: ChatApiMetadata.listContactsOperation,
        clientPageId: ChatRequestPageIds.listContacts,
      ),
    );
    final obj = CloudResponseDecoder.asObject(
      decoded,
      context: ChatRequestPageIds.listContacts,
    );
    final items = obj['items'];
    if (items is! List) {
      return const <ChatContactTabCircleRowDto>[];
    }
    return items
        .whereType<Map<String, dynamic>>()
        .take(limit)
        .map(
          (m) => ChatContactTabCircleRowDto.fromMap(<String, dynamic>{
            'circleId': m['circleId'] ?? m['id'],
            'displayName': m['displayName'] ?? m['name'],
            'avatarUrl': m['avatarUrl'] ?? m['coverUrl'],
            'subtitle': m['description'] ?? '',
          }),
        )
        .toList(growable: false);
  }

  @override
  Future<List<ChatContactTabFunGroupRowDto>> listContactTabFunGroups({
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final conversations = await listConversations(limit: limit);
    return conversations
        .where((item) => item.type == 'group')
        .take(limit)
        .map(
          (item) => ChatContactTabFunGroupRowDto(
            conversationId: item.id,
            displayName: item.title,
            avatarUrl: item.avatarUrl,
            subtitle: item.lastMessagePreview,
          ),
        )
        .toList(growable: false);
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
      headers: await _resolveHeaders(
        AppUiSurfaces.globalSearchSuggestions,
        operationId: ChatApiMetadata.searchContactsOperation,
        clientPageId: ChatRequestPageIds.searchContacts,
      ),
    );
    return _decodeObjectItems(
      decoded,
      context: ChatRequestPageIds.searchContacts,
      fromMap: ChatContactSearchItemDto.fromMap,
    );
  }

  // ── 会话时间戳索引 ──────────────────────────────────────────────────────────

  @override
  Future<List<ChatConversationTimestampDto>> getConversationTimestamps() async {
    final uri = _uri(ChatApiMetadata.listConversationTimestampsPath);
    final decoded = await _httpClient.getJson(
      uri,
      headers: await _resolveHeaders(
        AppUiSurfaces.chatList,
        operationId: ChatApiMetadata.listConversationTimestampsOperation,
        clientPageId: ChatRequestPageIds.listConversationTimestamps,
      ),
    );
    return _decodeObjectItems(
      decoded,
      context: ChatRequestPageIds.listConversationTimestamps,
      fromMap: ChatConversationTimestampDto.fromMap,
    );
  }

  @override
  Future<List<ConversationDto>> batchGetConversations(List<String> ids) async {
    final uri = _uri(ChatApiMetadata.batchGetConversationsPath);
    final decoded = await _httpClient.postJson(
      uri,
      headers: await _resolveHeaders(
        AppUiSurfaces.chatList,
        operationId: ChatApiMetadata.batchGetConversationsOperation,
        clientPageId: ChatRequestPageIds.batchGetConversations,
      ),
      body: {'ids': ids},
    );
    return _decodeObjectItems(
      decoded,
      context: ChatRequestPageIds.batchGetConversations,
      fromMap: ConversationDto.fromMap,
    );
  }

  // ── 群管理 ──────────────────────────────────────────────────────────────────

  @override
  Future<ChatGroupSettingsDto> getGroupSettings(String conversationId) async {
    final uri = _uri(
      ChatApiMetadata.getConversationPath(conversationId: conversationId),
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: await _resolveHeaders(
        AppUiSurfaces.chatSettings,
        operationId: ChatApiMetadata.getConversationOperation,
        clientPageId: ChatRequestPageIds.getConversation,
      ),
    );
    return ChatGroupSettingsDto.fromMap(
      CloudResponseDecoder.asObject(
        decoded,
        context: ChatRequestPageIds.getConversation,
      ),
    );
  }

  @override
  Future<GroupHomeDto> getGroupHome(String conversationId) async {
    final uri = _uri(
      ChatApiMetadata.getGroupHomePath(conversationId: conversationId),
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: await _resolveHeaders(
        AppUiSurfaces.chatSettings,
        operationId: ChatApiMetadata.getGroupHomeOperation,
        clientPageId: ChatRequestPageIds.getGroupHome,
      ),
    );
    return GroupHomeDto.fromMap(
      CloudResponseDecoder.asObject(
        decoded,
        context: _contextForSurface(
          AppUiSurfaces.chatSettings,
          operationId: ChatApiMetadata.getGroupHomeOperation,
        ),
      ),
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
      headers: await _resolveHeaders(
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
      headers: await _resolveHeaders(
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
      headers: await _resolveHeaders(
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
      headers: await _resolveHeaders(
        AppUiSurfaces.chatManage,
        operationId: ChatApiMetadata.dissolveConversationOperation,
        clientPageId: ChatRequestPageIds.dissolveConversation,
      ),
    );
  }
}
