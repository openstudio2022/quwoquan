import 'package:quwoquan_app/cloud/remote/rtc/call_session/call_session_remote_context.dart';
import 'package:quwoquan_app/cloud/runtime/generated/rtc/rtc_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class RemoteCallParticipantCommandWriter
    implements CallParticipantCommandWriter {
  const RemoteCallParticipantCommandWriter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final RtcCallInvocationContextFactory invocationContext;

  @override
  Future<RtcJoinCredentialsDto> joinCall(RtcCallIdCommand command) =>
      client.rtcCallSessionJoinCall(
        command,
        context: invocationContext(RtcRequestPageIds.joinCall, command: true),
      );

  @override
  Future<CallSessionDto> leaveCall(RtcCallIdCommand command) =>
      client.rtcCallSessionLeaveCall(
        command,
        context: invocationContext(RtcRequestPageIds.leaveCall, command: true),
      );

  @override
  Future<CallSessionDto> inviteToCall(RtcInviteToCallCommand command) =>
      client.rtcCallSessionInviteToCall(
        command,
        context: invocationContext(
          RtcRequestPageIds.inviteToCall,
          command: true,
        ),
      );

  @override
  Future<CallSessionDto> reportMediaConnected(RtcCallIdCommand command) =>
      client.rtcCallSessionReportMediaConnected(
        command,
        context: rtcInvocationWithIdempotencyKey(
          invocationContext(
            RtcRequestPageIds.reportMediaConnected,
            command: true,
          ),
          'rtc-media-connected:${command.callId}',
        ),
      );
}
