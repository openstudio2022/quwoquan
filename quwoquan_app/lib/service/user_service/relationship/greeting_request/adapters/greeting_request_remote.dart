import 'package:quwoquan_app/runtime/transport/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/service/user_service/relationship/greeting_request/application/public/greeting_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef GreetingRequestInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

final class RemoteGreetingRequestFacet
    implements GreetingRequestCommandWriter, GreetingRequestQuery {
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
  Future<GreetingRequestRecord> ignoreGreeting(IgnoreGreetingCommand command) {
    return client.userGreetingRequestIgnoreGreetingRequest(
      command,
      context: invocationContext(UserRequestPageIds.ignoreGreetingRequest),
    );
  }

  @override
  Future<GreetingRequestRecord> cancelGreeting(CancelGreetingCommand command) {
    return client.userGreetingRequestCancelGreetingRequest(
      command,
      context: invocationContext(UserRequestPageIds.cancelGreetingRequest),
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
