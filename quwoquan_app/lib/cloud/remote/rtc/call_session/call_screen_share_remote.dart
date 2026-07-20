import 'package:quwoquan_app/cloud/remote/rtc/call_session/call_session_remote_context.dart';
import 'package:quwoquan_app/cloud/runtime/generated/rtc/rtc_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class RemoteCallScreenShareWriter implements CallScreenShareWriter {
  const RemoteCallScreenShareWriter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final RtcCallInvocationContextFactory invocationContext;

  @override
  Future<CallSessionDto> startScreenShare(RtcCallIdCommand command) =>
      client.rtcCallSessionStartScreenShare(
        command,
        context: invocationContext(
          RtcRequestPageIds.startScreenShare,
          command: true,
        ),
      );

  @override
  Future<CallSessionDto> stopScreenShare(RtcCallIdCommand command) =>
      client.rtcCallSessionStopScreenShare(
        command,
        context: invocationContext(
          RtcRequestPageIds.stopScreenShare,
          command: true,
        ),
      );
}
