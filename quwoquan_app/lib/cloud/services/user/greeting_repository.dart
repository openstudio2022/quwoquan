import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/greeting_reply_result_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_request_page_ids.g.dart';

/// 打招呼请求 DTO
class GreetingRequestDto {
  const GreetingRequestDto({
    required this.id,
    required this.requesterSubAccountId,
    required this.targetSubAccountId,
    this.requestMessage,
    required this.status,
    required this.source,
    this.promotedConversationId,
    this.expireAt,
    this.decisionAt,
    required this.createdAt,
    required this.updatedAt,
  });

  final String id;
  final String requesterSubAccountId;
  final String targetSubAccountId;
  final String? requestMessage;

  /// pending / replied / ignored / blocked / cancelled / expired
  final String status;
  final String source;
  final String? promotedConversationId;
  final DateTime? expireAt;
  final DateTime? decisionAt;
  final DateTime createdAt;
  final DateTime updatedAt;

  bool get isPending => status == 'pending';
  bool get isReplied => status == 'replied';

  factory GreetingRequestDto.fromMap(Map<String, dynamic> map) {
    return GreetingRequestDto(
      id: (map['id'] as String?) ?? '',
      requesterSubAccountId: (map['requesterSubAccountId'] as String?) ?? '',
      targetSubAccountId: (map['targetSubAccountId'] as String?) ?? '',
      requestMessage: map['requestMessage'] as String?,
      status: (map['status'] as String?) ?? 'pending',
      source: (map['source'] as String?) ?? 'profile',
      promotedConversationId: map['promotedConversationId'] as String?,
      expireAt: map['expireAt'] != null
          ? DateTime.tryParse(map['expireAt'] as String)
          : null,
      decisionAt: map['decisionAt'] != null
          ? DateTime.tryParse(map['decisionAt'] as String)
          : null,
      createdAt:
          DateTime.tryParse((map['createdAt'] ?? '') as String) ??
          DateTime.now(),
      updatedAt:
          DateTime.tryParse((map['updatedAt'] ?? '') as String) ??
          DateTime.now(),
    );
  }
}

/// 打招呼 Repository（三层模式）
///
/// 对应云侧路由（contracts/metadata/user/greeting_request/service.yaml）：
///   POST   /v1/user/greeting-request
///   GET    /v1/user/greeting-request/inbox
///   GET    /v1/user/greeting-request/outbox
///   POST   /v1/user/greeting-request/{requestId}/reply
///   POST   /v1/user/greeting-request/{requestId}/ignore
///   DELETE /v1/user/greeting-request/{requestId}
abstract class GreetingRepository {
  Future<GreetingRequestDto> sendGreeting({
    required String targetSubAccountId,
    String? requestMessage,
    String source = 'profile',
  });

  Future<List<GreetingRequestDto>> listInbox({
    String status = 'pending',
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<List<GreetingRequestDto>> listOutbox({
    String status = 'pending',
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<GreetingReplyResultDto> replyGreeting(String requestId);

  Future<GreetingRequestDto> ignoreGreeting(String requestId);

  Future<GreetingRequestDto> cancelGreeting(String requestId);
}

/// Mock 实现
class MockGreetingRepository extends GreetingRepository {
  MockGreetingRepository({
    List<GreetingRequestDto> seedInbox = const <GreetingRequestDto>[],
    List<GreetingRequestDto> seedOutbox = const <GreetingRequestDto>[],
  }) : _inbox = List<GreetingRequestDto>.from(seedInbox),
       _outbox = List<GreetingRequestDto>.from(seedOutbox);

  final List<GreetingRequestDto> _inbox;
  final List<GreetingRequestDto> _outbox;

  @override
  Future<GreetingRequestDto> sendGreeting({
    required String targetSubAccountId,
    String? requestMessage,
    String source = 'profile',
  }) async {
    final dto = GreetingRequestDto(
      id: 'mock_gr_${DateTime.now().millisecondsSinceEpoch}',
      requesterSubAccountId: 'mock_me',
      targetSubAccountId: targetSubAccountId,
      requestMessage: requestMessage,
      status: 'pending',
      source: source,
      createdAt: DateTime.now(),
      updatedAt: DateTime.now(),
    );
    _outbox.add(dto);
    return dto;
  }

  @override
  Future<List<GreetingRequestDto>> listInbox({
    String status = 'pending',
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async => _inbox.where((g) => g.status == status).toList();

  @override
  Future<List<GreetingRequestDto>> listOutbox({
    String status = 'pending',
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async => _outbox.where((g) => g.status == status).toList();

  @override
  Future<GreetingReplyResultDto> replyGreeting(String requestId) async {
    final conversationId = 'mock_conv_$requestId';
    final index = _inbox.indexWhere((g) => g.id == requestId);
    if (index >= 0) {
      final current = _inbox[index];
      _inbox[index] = GreetingRequestDto(
        id: current.id,
        requesterSubAccountId: current.requesterSubAccountId,
        targetSubAccountId: current.targetSubAccountId,
        requestMessage: current.requestMessage,
        status: 'replied',
        source: current.source,
        promotedConversationId: conversationId,
        expireAt: current.expireAt,
        decisionAt: DateTime.now(),
        createdAt: current.createdAt,
        updatedAt: DateTime.now(),
      );
    }
    return GreetingReplyResultDto.fromMap(<String, dynamic>{
      'conversationId': conversationId,
    });
  }

  @override
  Future<GreetingRequestDto> ignoreGreeting(String requestId) async {
    final idx = _inbox.indexWhere((g) => g.id == requestId);
    if (idx >= 0) {
      final current = _inbox[idx];
      final ignored = GreetingRequestDto(
        id: current.id,
        requesterSubAccountId: current.requesterSubAccountId,
        targetSubAccountId: current.targetSubAccountId,
        requestMessage: current.requestMessage,
        status: 'ignored',
        source: current.source,
        promotedConversationId: current.promotedConversationId,
        expireAt: current.expireAt,
        decisionAt: DateTime.now(),
        createdAt: current.createdAt,
        updatedAt: DateTime.now(),
      );
      _inbox[idx] = ignored;
      return ignored;
    }
    return GreetingRequestDto(
      id: requestId,
      requesterSubAccountId: '',
      targetSubAccountId: '',
      status: 'ignored',
      source: 'profile',
      createdAt: DateTime.now(),
      updatedAt: DateTime.now(),
    );
  }

  @override
  Future<GreetingRequestDto> cancelGreeting(String requestId) async {
    _outbox.removeWhere((g) => g.id == requestId);
    return GreetingRequestDto(
      id: requestId,
      requesterSubAccountId: '',
      targetSubAccountId: '',
      status: 'cancelled',
      source: 'profile',
      createdAt: DateTime.now(),
      updatedAt: DateTime.now(),
    );
  }
}

/// Remote 实现
class RemoteGreetingRepository extends GreetingRepository {
  RemoteGreetingRepository({CloudHttpClient? httpClient, String? baseUrl})
    : _httpClient = httpClient ?? CloudHttpClient(),
      _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim();

  final CloudHttpClient _httpClient;
  final String _baseUrl;

  Uri _uri(String path) => Uri.parse('$_baseUrl$path');

  Map<String, String> _headersFor(String pageId) =>
      CloudRequestHeaders.forPage(pageId);

  List<GreetingRequestDto> _decodeGreetingList(
    Object? decoded, {
    required String context,
  }) {
    final body = CloudResponseDecoder.asObject(decoded, context: context);
    return CloudResponseDecoder.mapList(
      body,
      'items',
    ).map(GreetingRequestDto.fromMap).toList(growable: false);
  }

  @override
  Future<GreetingRequestDto> sendGreeting({
    required String targetSubAccountId,
    String? requestMessage,
    String source = 'profile',
  }) async {
    final uri = _uri(UserApiMetadata.sendGreetingRequestPath);
    final body = <String, dynamic>{
      'targetSubAccountId': targetSubAccountId,
      'source': source,
    };
    if (requestMessage != null) {
      body['requestMessage'] = requestMessage;
    }
    final decoded = await _httpClient.postJson(
      uri,
      headers: _headersFor(UserRequestPageIds.sendGreetingRequest),
      body: body,
    );
    return GreetingRequestDto.fromMap(
      CloudResponseDecoder.asObject(
        decoded,
        context: UserRequestPageIds.sendGreetingRequest,
      ),
    );
  }

  @override
  Future<List<GreetingRequestDto>> listInbox({
    String status = 'pending',
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final queryParameters = <String, String>{
      'status': status,
      'limit': '$limit',
    };
    if (cursor != null) {
      queryParameters['cursor'] = cursor;
    }
    final uri = Uri.parse(
      '$_baseUrl${UserApiMetadata.listGreetingInboxPath}',
    ).replace(queryParameters: queryParameters);
    final decoded = await _httpClient.getJson(
      uri,
      headers: _headersFor(UserRequestPageIds.listGreetingInbox),
    );
    return _decodeGreetingList(
      decoded,
      context: UserRequestPageIds.listGreetingInbox,
    );
  }

  @override
  Future<List<GreetingRequestDto>> listOutbox({
    String status = 'pending',
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final queryParameters = <String, String>{
      'status': status,
      'limit': '$limit',
    };
    if (cursor != null) {
      queryParameters['cursor'] = cursor;
    }
    final uri = Uri.parse(
      '$_baseUrl${UserApiMetadata.listGreetingOutboxPath}',
    ).replace(queryParameters: queryParameters);
    final decoded = await _httpClient.getJson(
      uri,
      headers: _headersFor(UserRequestPageIds.listGreetingOutbox),
    );
    return _decodeGreetingList(
      decoded,
      context: UserRequestPageIds.listGreetingOutbox,
    );
  }

  @override
  Future<GreetingReplyResultDto> replyGreeting(String requestId) async {
    final uri = _uri(
      UserApiMetadata.replyGreetingRequestPath(requestId: requestId),
    );
    final decoded = await _httpClient.postJson(
      uri,
      headers: _headersFor(UserRequestPageIds.replyGreetingRequest),
      body: const <String, dynamic>{},
    );
    return GreetingReplyResultDto.fromMap(
      CloudResponseDecoder.asObject(
        decoded,
        context: UserRequestPageIds.replyGreetingRequest,
      ),
    );
  }

  @override
  Future<GreetingRequestDto> ignoreGreeting(String requestId) async {
    final uri = _uri(
      UserApiMetadata.ignoreGreetingRequestPath(requestId: requestId),
    );
    final decoded = await _httpClient.postJson(
      uri,
      headers: _headersFor(UserRequestPageIds.ignoreGreetingRequest),
      body: const <String, dynamic>{},
    );
    return GreetingRequestDto.fromMap(
      CloudResponseDecoder.asObject(
        decoded,
        context: UserRequestPageIds.ignoreGreetingRequest,
      ),
    );
  }

  @override
  Future<GreetingRequestDto> cancelGreeting(String requestId) async {
    final uri = _uri(
      UserApiMetadata.cancelGreetingRequestPath(requestId: requestId),
    );
    final decoded = await _httpClient.deleteJson(
      uri,
      headers: _headersFor(UserRequestPageIds.cancelGreetingRequest),
    );
    final body = CloudResponseDecoder.asObject(
      decoded,
      context: UserRequestPageIds.cancelGreetingRequest,
    );
    return GreetingRequestDto.fromMap(body);
  }
}
