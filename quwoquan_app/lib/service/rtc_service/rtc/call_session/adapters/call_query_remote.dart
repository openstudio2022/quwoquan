import 'package:quwoquan_app/service/rtc_service/rtc/call_session/adapters/call_session_remote_context.dart';
import 'package:quwoquan_app/runtime/transport/generated/rtc/rtc_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class RemoteCallQuery implements CallQuery {
  const RemoteCallQuery({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final RtcCallInvocationContextFactory invocationContext;

  @override
  Future<CallSession> getCall(RtcGetCallQuery query) =>
      client.rtcCallSessionGetCall(
        query,
        context: invocationContext(RtcRequestPageIds.getCall, command: false),
      );

  @override
  Future<RtcCallHistoryPage> listCalls(RtcListCallsQuery query) =>
      client.rtcCallSessionListCalls(
        query,
        context: invocationContext(RtcRequestPageIds.listCalls, command: false),
      );
}
