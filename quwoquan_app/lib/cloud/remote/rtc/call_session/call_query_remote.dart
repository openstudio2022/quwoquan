import 'package:quwoquan_app/cloud/remote/rtc/call_session/call_session_remote_context.dart';
import 'package:quwoquan_app/cloud/runtime/generated/rtc/rtc_request_page_ids.g.dart';
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
