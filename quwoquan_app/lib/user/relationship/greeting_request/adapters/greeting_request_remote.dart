import 'package:quwoquan_app/cloud/runtime/generated/user/user_request_page_ids.g.dart';
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
