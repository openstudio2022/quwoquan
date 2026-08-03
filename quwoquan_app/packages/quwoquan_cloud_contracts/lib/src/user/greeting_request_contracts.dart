import 'user_operation_contracts.g.dart';

abstract interface class GreetingRequestCommandWriter {
  Future<GreetingRequestRecord> sendGreeting(SendGreetingCommand command);
  Future<GreetingRequestRecord> replyGreeting(ReplyGreetingCommand command);
  Future<GreetingRequestRecord> ignoreGreeting(IgnoreGreetingCommand command);
  Future<GreetingRequestRecord> cancelGreeting(CancelGreetingCommand command);
}

abstract interface class GreetingRequestQuery {
  Future<GreetingRequestSlice> listGreetingInbox(
    ListGreetingRequestsQuery query,
  );
  Future<GreetingRequestSlice> listGreetingOutbox(
    ListGreetingRequestsQuery query,
  );
}
