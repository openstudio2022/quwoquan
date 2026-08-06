import 'package:quwoquan_app/service/rtc_service/rtc/call_session/adapters/call_session_remote_context.dart';
import 'package:quwoquan_app/runtime/transport/generated/rtc/rtc_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// CallSession 生命周期命令的 production Remote adapter。
///
/// path、operation、错误映射、超时、重试与解码均由 generated client 持有。
final class RemoteCallLifecycleCommandWriter
    implements CallLifecycleCommandWriter {
  const RemoteCallLifecycleCommandWriter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final RtcCallInvocationContextFactory invocationContext;

  @override
  Future<RtcInitiateCallResult> initiateCall(RtcInitiateCallCommand command) =>
      client.rtcCallSessionInitiateCall(
        command,
        context: invocationContext(
          RtcRequestPageIds.initiateCall,
          command: true,
        ),
      );

  @override
  Future<RtcAnswerCallResult> answerCall(RtcCallIdCommand command) =>
      client.rtcCallSessionAnswerCall(
        command,
        context: invocationContext(RtcRequestPageIds.answerCall, command: true),
      );

  @override
  Future<CallSession> rejectCall(RtcCallIdCommand command) =>
      client.rtcCallSessionRejectCall(
        command,
        context: invocationContext(RtcRequestPageIds.rejectCall, command: true),
      );

  @override
  Future<CallSession> cancelCall(RtcCallIdCommand command) =>
      client.rtcCallSessionCancelCall(
        command,
        context: invocationContext(RtcRequestPageIds.cancelCall, command: true),
      );

  @override
  Future<CallSession> hangupCall(RtcCallIdCommand command) =>
      client.rtcCallSessionHangupCall(
        command,
        context: invocationContext(RtcRequestPageIds.hangupCall, command: true),
      );
}
