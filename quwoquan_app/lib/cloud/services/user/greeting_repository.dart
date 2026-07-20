import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/greeting_reply_result_dto.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

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

  GreetingRequestDto copyWith({
    String? status,
    String? promotedConversationId,
    DateTime? decisionAt,
    DateTime? updatedAt,
  }) {
    return GreetingRequestDto(
      id: id,
      requesterSubAccountId: requesterSubAccountId,
      targetSubAccountId: targetSubAccountId,
      requestMessage: requestMessage,
      status: status ?? this.status,
      source: source,
      promotedConversationId:
          promotedConversationId ?? this.promotedConversationId,
      expireAt: expireAt,
      decisionAt: decisionAt ?? this.decisionAt,
      createdAt: createdAt,
      updatedAt: updatedAt ?? this.updatedAt,
    );
  }

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

  factory GreetingRequestDto.fromContract(GreetingRequestRecord record) {
    return GreetingRequestDto(
      id: record.id,
      requesterSubAccountId: record.requesterSubAccountId,
      targetSubAccountId: record.targetSubAccountId,
      requestMessage: record.requestMessage,
      status: record.status,
      source: record.source,
      promotedConversationId: record.promotedConversationId,
      expireAt: record.expireAt,
      decisionAt: record.decisionAt,
      createdAt: record.createdAt,
      updatedAt: record.updatedAt,
    );
  }
}

/// 打招呼 Repository（三层模式）
///
/// 对应云侧路由（contracts/metadata/user/greeting_request/service.yaml）：
///   POST   /user/greeting-request
///   GET    /user/greeting-request/inbox
///   GET    /user/greeting-request/outbox
///   POST   /user/greeting-request/{requestId}/reply
///   POST   /user/greeting-request/{requestId}/ignore
///   DELETE /user/greeting-request/{requestId}
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

/// Remote 实现
class RemoteGreetingRepository implements GreetingRepository {
  const RemoteGreetingRepository({
    required this.commandWriter,
    required this.query,
  });

  final GreetingRequestCommandWriter commandWriter;
  final GreetingRequestQuery query;

  @override
  Future<GreetingRequestDto> sendGreeting({
    required String targetSubAccountId,
    String? requestMessage,
    String source = 'profile',
  }) async {
    final record = await commandWriter.sendGreeting(
      SendGreetingCommand(
        targetSubAccountId: targetSubAccountId,
        requestMessage: requestMessage,
        source: source,
      ),
    );
    return GreetingRequestDto.fromContract(record);
  }

  @override
  Future<List<GreetingRequestDto>> listInbox({
    String status = 'pending',
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final slice = await query.listGreetingInbox(
      ListGreetingRequestsQuery(status: status, cursor: cursor, limit: limit),
    );
    return slice.items
        .map(GreetingRequestDto.fromContract)
        .toList(growable: false);
  }

  @override
  Future<List<GreetingRequestDto>> listOutbox({
    String status = 'pending',
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final slice = await query.listGreetingOutbox(
      ListGreetingRequestsQuery(status: status, cursor: cursor, limit: limit),
    );
    return slice.items
        .map(GreetingRequestDto.fromContract)
        .toList(growable: false);
  }

  @override
  Future<GreetingReplyResultDto> replyGreeting(String requestId) async {
    final record = await commandWriter.replyGreeting(
      ReplyGreetingCommand(requestId: requestId),
    );
    return GreetingReplyResultDto(
      conversationId: record.promotedConversationId ?? '',
    );
  }

  @override
  Future<GreetingRequestDto> ignoreGreeting(String requestId) async {
    final record = await commandWriter.ignoreGreeting(
      IgnoreGreetingCommand(requestId: requestId),
    );
    return GreetingRequestDto.fromContract(record);
  }

  @override
  Future<GreetingRequestDto> cancelGreeting(String requestId) async {
    final record = await commandWriter.cancelGreeting(
      CancelGreetingCommand(requestId: requestId),
    );
    return GreetingRequestDto.fromContract(record);
  }
}
