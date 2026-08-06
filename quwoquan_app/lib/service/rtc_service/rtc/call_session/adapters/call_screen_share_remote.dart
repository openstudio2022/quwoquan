import 'package:quwoquan_app/service/rtc_service/rtc/call_session/adapters/call_session_remote_context.dart';
import 'package:quwoquan_app/runtime/transport/generated/rtc/rtc_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class RemoteCallScreenShareWriter implements CallScreenShareWriter {
  const RemoteCallScreenShareWriter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final RtcCallInvocationContextFactory invocationContext;

  @override
  Future<CallSession> startScreenShare(RtcCallIdCommand command) =>
      client.rtcCallSessionStartScreenShare(
        command,
        context: invocationContext(
          RtcRequestPageIds.startScreenShare,
          command: true,
        ),
      );

  @override
  Future<CallSession> stopScreenShare(RtcCallIdCommand command) =>
      client.rtcCallSessionStopScreenShare(
        command,
        context: invocationContext(
          RtcRequestPageIds.stopScreenShare,
          command: true,
        ),
      );
}
