import 'package:quwoquan_app/cloud/remote/rtc/call_session/call_session_remote_context.dart';
import 'package:quwoquan_app/cloud/runtime/generated/rtc/rtc_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class RemoteCallMediaControlWriter implements CallMediaControlWriter {
  const RemoteCallMediaControlWriter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final RtcCallInvocationContextFactory invocationContext;

  @override
  Future<CallSessionDto> toggleMute(RtcToggleMuteCommand command) =>
      client.rtcCallSessionToggleMute(
        command,
        context: invocationContext(RtcRequestPageIds.toggleMute, command: true),
      );

  @override
  Future<CallSessionDto> toggleCamera(RtcToggleCameraCommand command) =>
      client.rtcCallSessionToggleCamera(
        command,
        context: invocationContext(
          RtcRequestPageIds.toggleCamera,
          command: true,
        ),
      );
}
