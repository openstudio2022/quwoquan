import 'package:quwoquan_app/runtime/transport/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/service/user_service/relationship/greeting_request/application/public/greeting_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef GreetingRequestInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      String? idempotencyKey,
    });

final class RemoteGreetingRequestFacet
    implements
        GreetingRequestCommandWriter,
        GreetingRequestQuery,
        GreetingRequestIntentCommandWriter {
  const RemoteGreetingRequestFacet({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final GreetingRequestInvocationContextFactory invocationContext;

  @override
  Future<GreetingRequestRecord> sendGreeting(SendGreetingCommand command) {
    return client.userGreetingRequestSendGreetingRequest(
      command,
      context: invocationContext(UserRequestPageIds.sendGreetingRequest),
    );
  }

  @override
  Future<GreetingRequestSlice> listGreetingInbox(
    ListGreetingRequestsQuery query,
  ) {
    return client.userGreetingRequestListGreetingInbox(
      query,
      context: invocationContext(UserRequestPageIds.listGreetingInbox),
    );
  }

  @override
  Future<GreetingRequestSlice> listGreetingOutbox(
    ListGreetingRequestsQuery query,
  ) {
    return client.userGreetingRequestListGreetingOutbox(
      query,
      context: invocationContext(UserRequestPageIds.listGreetingOutbox),
    );
  }

  @override
  Future<GreetingRequestRecord> replyGreeting(ReplyGreetingCommand command) {
    return client.userGreetingRequestReplyGreetingRequest(
      command,
      context: invocationContext(UserRequestPageIds.replyGreetingRequest),
    );
  }

  @override
  Future<GreetingRequestRecord> replyGreetingWithIntent(
    ReplyGreetingCommand command, {
    required String idempotencyKey,
  }) {
    return client.userGreetingRequestReplyGreetingRequest(
      command,
      context: invocationContext(
        UserRequestPageIds.replyGreetingRequest,
        idempotencyKey: idempotencyKey,
      ),
    );
  }

  @override
  Future<GreetingRequestRecord> ignoreGreeting(IgnoreGreetingCommand command) {
    return client.userGreetingRequestIgnoreGreetingRequest(
      command,
      context: invocationContext(UserRequestPageIds.ignoreGreetingRequest),
    );
  }

  @override
  Future<GreetingRequestRecord> ignoreGreetingWithIntent(
    IgnoreGreetingCommand command, {
    required String idempotencyKey,
  }) {
    return client.userGreetingRequestIgnoreGreetingRequest(
      command,
      context: invocationContext(
        UserRequestPageIds.ignoreGreetingRequest,
        idempotencyKey: idempotencyKey,
      ),
    );
  }

  @override
  Future<GreetingRequestRecord> cancelGreeting(CancelGreetingCommand command) {
    return client.userGreetingRequestCancelGreetingRequest(
      command,
      context: invocationContext(UserRequestPageIds.cancelGreetingRequest),
    );
  }

  @override
  Future<GreetingRequestRecord> cancelGreetingWithIntent(
    CancelGreetingCommand command, {
    required String idempotencyKey,
  }) {
    return client.userGreetingRequestCancelGreetingRequest(
      command,
      context: invocationContext(
        UserRequestPageIds.cancelGreetingRequest,
        idempotencyKey: idempotencyKey,
      ),
    );
  }
}

final class RemoteGreetingRepository implements GreetingRepository {
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
  Future<GreetingReplyResultViewData> replyGreeting(
    String requestId, {
    String? idempotencyKey,
  }) async {
    final command = ReplyGreetingCommand(requestId: requestId);
    final record = await _runIntent(
      idempotencyKey: idempotencyKey,
      fallback: () => commandWriter.replyGreeting(command),
      bound: (writer, key) =>
          writer.replyGreetingWithIntent(command, idempotencyKey: key),
    );
    return GreetingReplyResultViewData(
      conversationId: record.promotedConversationId ?? '',
    );
  }

  @override
  Future<GreetingRequestViewData> ignoreGreeting(
    String requestId, {
    String? idempotencyKey,
  }) async {
    final command = IgnoreGreetingCommand(requestId: requestId);
    final record = await _runIntent(
      idempotencyKey: idempotencyKey,
      fallback: () => commandWriter.ignoreGreeting(command),
      bound: (writer, key) =>
          writer.ignoreGreetingWithIntent(command, idempotencyKey: key),
    );
    return GreetingRequestViewData.fromWire(record);
  }

  @override
  Future<GreetingRequestViewData> cancelGreeting(
    String requestId, {
    String? idempotencyKey,
  }) async {
    final command = CancelGreetingCommand(requestId: requestId);
    final record = await _runIntent(
      idempotencyKey: idempotencyKey,
      fallback: () => commandWriter.cancelGreeting(command),
      bound: (writer, key) =>
          writer.cancelGreetingWithIntent(command, idempotencyKey: key),
    );
    return GreetingRequestViewData.fromWire(record);
  }

  Future<GreetingRequestRecord> _runIntent({
    required String? idempotencyKey,
    required Future<GreetingRequestRecord> Function() fallback,
    required Future<GreetingRequestRecord> Function(
      GreetingRequestIntentCommandWriter writer,
      String idempotencyKey,
    )
    bound,
  }) {
    final normalized = idempotencyKey?.trim() ?? '';
    if (normalized.isEmpty) {
      return fallback();
    }
    final writer = commandWriter;
    if (writer is! GreetingRequestIntentCommandWriter) {
      throw StateError(
        'GreetingRequest command writer does not support caller-bound intent',
      );
    }
    return bound(writer as GreetingRequestIntentCommandWriter, normalized);
  }
}
