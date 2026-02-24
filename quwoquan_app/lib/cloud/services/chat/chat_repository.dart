import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';

/// Chat 域 Repository：会话、消息、联系人等业务对象入口。
abstract class ChatRepository {
  Future<List<Map<String, dynamic>>> listConversations({
    String? cursor,
    int limit = 20,
  });

  Future<List<Map<String, dynamic>>> listMessages({
    required String conversationId,
    String? before,
    int limit = 20,
  });
}

class MockChatRepository implements ChatRepository {
  MockChatRepository(this._repository);

  final AppContentRepository _repository;

  @override
  Future<List<Map<String, dynamic>>> listConversations({
    String? cursor,
    int limit = 20,
  }) async {
    // 本地 mock 不做分页；后续可按 cursor 补齐。
    return _repository.chatMockConversations;
  }

  @override
  Future<List<Map<String, dynamic>>> listMessages({
    required String conversationId,
    String? before,
    int limit = 20,
  }) async {
    final list = _repository.chatMessagesFor(conversationId);
    return list;
  }
}

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
    final page = CloudResponseDecoder.asCursorPage(
      decoded,
      context: 'chat.conversation.list',
    );
    return page.items;
  }

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
    final page = CloudResponseDecoder.asCursorPage(
      decoded,
      context: 'chat.message.list',
    );
    return page.items;
  }
}

