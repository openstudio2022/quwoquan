import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 打招呼请求 DTO
class GreetingRequestViewData {
  const GreetingRequestViewData({
    required this.id,
    required this.requesterPersonaId,
    required this.targetPersonaId,
    this.requestMessage,
    this.intersectionRef,
    this.intersectionSnapshot,
    required this.status,
    required this.source,
    this.promotedConversationId,
    this.expireAt,
    this.decisionAt,
    required this.createdAt,
    required this.updatedAt,
  });

  final String id;
  final String requesterPersonaId;
  final String targetPersonaId;
  final String? requestMessage;
  final GreetingIntersectionRef? intersectionRef;
  final GreetingIntersectionSnapshotViewData? intersectionSnapshot;

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

  GreetingRequestViewData copyWith({
    String? status,
    String? promotedConversationId,
    DateTime? decisionAt,
    DateTime? updatedAt,
  }) {
    return GreetingRequestViewData(
      id: id,
      requesterPersonaId: requesterPersonaId,
      targetPersonaId: targetPersonaId,
      requestMessage: requestMessage,
      intersectionRef: intersectionRef,
      intersectionSnapshot: intersectionSnapshot,
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

  factory GreetingRequestViewData.fromWire(GreetingRequestRecord record) {
    return GreetingRequestViewData(
      id: record.id,
      requesterPersonaId: record.requesterPersonaId,
      targetPersonaId: record.targetPersonaId,
      requestMessage: record.requestMessage,
      intersectionRef: record.intersectionRef,
      intersectionSnapshot: record.intersectionSnapshot == null
          ? null
          : GreetingIntersectionSnapshotViewData(
              primaryText: record.intersectionSnapshot!.primaryText,
            ),
      status: record.status.wireName,
      source: record.source.wireName,
      promotedConversationId: record.promotedConversationId,
      expireAt: record.expireAt,
      decisionAt: record.decisionAt,
      createdAt: record.createdAt,
      updatedAt: record.updatedAt,
    );
  }
}

final class GreetingIntersectionSnapshotViewData {
  const GreetingIntersectionSnapshotViewData({required this.primaryText});

  final String primaryText;
}

final class GreetingReplyResultViewData {
  const GreetingReplyResultViewData({required this.conversationId});

  final String conversationId;
}

/// 打招呼 Repository（三层模式）
///
/// 对应云侧路由（quwoquan_service/services/user-service/contracts/relationship/greeting_request/operations.yaml）：
///   POST   /user/greeting-request
///   GET    /user/greeting-request/inbox
///   GET    /user/greeting-request/outbox
///   POST   /user/greeting-request/{requestId}/reply
///   POST   /user/greeting-request/{requestId}/ignore
///   DELETE /user/greeting-request/{requestId}
abstract class GreetingRepository {
  Future<GreetingRequestViewData> sendGreeting({
    required String targetPersonaId,
    String? requestMessage,
    String source = 'profile',
    GreetingIntersectionRef? intersectionRef,
  });

  Future<List<GreetingRequestViewData>> listInbox({
    String status = 'pending',
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<List<GreetingRequestViewData>> listOutbox({
    String status = 'pending',
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<GreetingReplyResultViewData> replyGreeting(String requestId);

  Future<GreetingRequestViewData> ignoreGreeting(String requestId);

  Future<GreetingRequestViewData> cancelGreeting(String requestId);
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
  Future<GreetingRequestViewData> sendGreeting({
    required String targetPersonaId,
    String? requestMessage,
    String source = 'profile',
    GreetingIntersectionRef? intersectionRef,
  }) async {
    final record = await commandWriter.sendGreeting(
      SendGreetingCommand(
        targetPersonaId: targetPersonaId,
        requestMessage: requestMessage,
        source: source,
        intersectionRef: intersectionRef,
      ),
    );
    return GreetingRequestViewData.fromWire(record);
  }

  @override
  Future<List<GreetingRequestViewData>> listInbox({
    String status = 'pending',
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final slice = await query.listGreetingInbox(
      ListGreetingRequestsQuery(status: status, cursor: cursor, limit: limit),
    );
    return slice.items
        .map(GreetingRequestViewData.fromWire)
        .toList(growable: false);
  }

  @override
  Future<List<GreetingRequestViewData>> listOutbox({
    String status = 'pending',
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final slice = await query.listGreetingOutbox(
      ListGreetingRequestsQuery(status: status, cursor: cursor, limit: limit),
    );
    return slice.items
        .map(GreetingRequestViewData.fromWire)
        .toList(growable: false);
  }

  @override
  Future<GreetingReplyResultViewData> replyGreeting(String requestId) async {
    final record = await commandWriter.replyGreeting(
      ReplyGreetingCommand(requestId: requestId),
    );
    return GreetingReplyResultViewData(
      conversationId: record.promotedConversationId ?? '',
    );
  }

  @override
  Future<GreetingRequestViewData> ignoreGreeting(String requestId) async {
    final record = await commandWriter.ignoreGreeting(
      IgnoreGreetingCommand(requestId: requestId),
    );
    return GreetingRequestViewData.fromWire(record);
  }

  @override
  Future<GreetingRequestViewData> cancelGreeting(String requestId) async {
    final record = await commandWriter.cancelGreeting(
      CancelGreetingCommand(requestId: requestId),
    );
    return GreetingRequestViewData.fromWire(record);
  }
}
