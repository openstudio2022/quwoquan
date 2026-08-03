import 'rtc_operation_contracts.g.dart';

export 'rtc_operation_contracts.g.dart';

/// RTC CallSession application ports over the canonical generated wire owner.
abstract interface class CallLifecycleCommandWriter {
  Future<RtcInitiateCallResult> initiateCall(RtcInitiateCallCommand command);

  Future<RtcAnswerCallResult> answerCall(RtcCallIdCommand command);

  Future<CallSession> rejectCall(RtcCallIdCommand command);

  Future<CallSession> cancelCall(RtcCallIdCommand command);

  Future<CallSession> hangupCall(RtcCallIdCommand command);
}

abstract interface class CallParticipantCommandWriter {
  Future<RtcJoinCredentials> joinCall(RtcCallIdCommand command);

  Future<CallSession> leaveCall(RtcCallIdCommand command);

  Future<CallSession> inviteToCall(RtcInviteToCallCommand command);

  Future<CallSession> reportMediaConnected(RtcCallIdCommand command);
}

abstract interface class CallMediaControlWriter {
  Future<CallSession> toggleMute(RtcToggleMuteCommand command);

  Future<CallSession> toggleCamera(RtcToggleCameraCommand command);
}

abstract interface class CallScreenShareWriter {
  Future<CallSession> startScreenShare(RtcCallIdCommand command);

  Future<CallSession> stopScreenShare(RtcCallIdCommand command);
}

abstract interface class CallQuery {
  Future<CallSession> getCall(RtcGetCallQuery query);

  Future<RtcCallHistoryPage> listCalls(RtcListCallsQuery query);
}
