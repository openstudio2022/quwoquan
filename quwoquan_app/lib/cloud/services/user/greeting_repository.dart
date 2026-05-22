import 'dart:convert';

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
  final List<GreetingRequestDto> _inbox = [];
  final List<GreetingRequestDto> _outbox = [];

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
  Future<GreetingReplyResultDto> replyGreeting(String requestId) async =>
      GreetingReplyResultDto.fromMap(<String, dynamic>{
        'conversationId': 'mock_conv_$requestId',
      });

  @override
  Future<GreetingRequestDto> ignoreGreeting(String requestId) async {
    final idx = _inbox.indexWhere((g) => g.id == requestId);
    if (idx >= 0) {
      _inbox.removeAt(idx);
    }
    return _inbox.isEmpty
        ? GreetingRequestDto(
            id: requestId,
            requesterSubAccountId: '',
            targetSubAccountId: '',
            status: 'ignored',
            source: 'profile',
            createdAt: DateTime.now(),
            updatedAt: DateTime.now(),
          )
        : _inbox[0];
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

  Map<String, String> get _headers =>
      CloudRequestHeaders.forPage(UserRequestPageIds.sendGreetingRequest);

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
    final resp = await _httpClient.post(
      uri,
      headers: {..._headers, 'Content-Type': 'application/json'},
      body: jsonEncode(body),
    );
    if (resp.statusCode == 200 || resp.statusCode == 201) {
      return GreetingRequestDto.fromMap(
        CloudResponseDecoder.asObject(
          jsonDecode(resp.body),
          context: UserRequestPageIds.sendGreetingRequest,
        ),
      );
    }
    throw Exception('SendGreetingRequest failed: ${resp.statusCode}');
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
    final resp = await _httpClient.get(
      uri,
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.listGreetingInbox,
      ),
    );
    if (resp.statusCode == 200) {
      final body = CloudResponseDecoder.asObject(
        jsonDecode(resp.body),
        context: UserRequestPageIds.listGreetingInbox,
      );
      return CloudResponseDecoder.mapList(
        body,
        'items',
      ).map(GreetingRequestDto.fromMap).toList(growable: false);
    }
    return [];
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
    final resp = await _httpClient.get(
      uri,
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.listGreetingOutbox,
      ),
    );
    if (resp.statusCode == 200) {
      final body = CloudResponseDecoder.asObject(
        jsonDecode(resp.body),
        context: UserRequestPageIds.listGreetingOutbox,
      );
      return CloudResponseDecoder.mapList(
        body,
        'items',
      ).map(GreetingRequestDto.fromMap).toList(growable: false);
    }
    return [];
  }

  @override
  Future<GreetingReplyResultDto> replyGreeting(String requestId) async {
    final uri = _uri(
      UserApiMetadata.replyGreetingRequestPath(requestId: requestId),
    );
    final resp = await _httpClient.post(
      uri,
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.replyGreetingRequest,
      ),
    );
    if (resp.statusCode == 200) {
      return GreetingReplyResultDto.fromMap(
        CloudResponseDecoder.asObject(
          jsonDecode(resp.body),
          context: UserRequestPageIds.replyGreetingRequest,
        ),
      );
    }
    throw Exception('ReplyGreetingRequest failed: ${resp.statusCode}');
  }

  @override
  Future<GreetingRequestDto> ignoreGreeting(String requestId) async {
    final uri = _uri(
      UserApiMetadata.ignoreGreetingRequestPath(requestId: requestId),
    );
    final resp = await _httpClient.post(
      uri,
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.ignoreGreetingRequest,
      ),
    );
    if (resp.statusCode == 200) {
      return GreetingRequestDto.fromMap(
        CloudResponseDecoder.asObject(
          jsonDecode(resp.body),
          context: UserRequestPageIds.ignoreGreetingRequest,
        ),
      );
    }
    throw Exception('IgnoreGreetingRequest failed: ${resp.statusCode}');
  }

  @override
  Future<GreetingRequestDto> cancelGreeting(String requestId) async {
    final uri = _uri(
      UserApiMetadata.cancelGreetingRequestPath(requestId: requestId),
    );
    final resp = await _httpClient.delete(
      uri,
      headers: CloudRequestHeaders.forPage(
        UserRequestPageIds.cancelGreetingRequest,
      ),
    );
    if (resp.statusCode == 200) {
      return GreetingRequestDto.fromMap(
        CloudResponseDecoder.asObject(
          jsonDecode(resp.body),
          context: UserRequestPageIds.cancelGreetingRequest,
        ),
      );
    }
    throw Exception('CancelGreetingRequest failed: ${resp.statusCode}');
  }
}
