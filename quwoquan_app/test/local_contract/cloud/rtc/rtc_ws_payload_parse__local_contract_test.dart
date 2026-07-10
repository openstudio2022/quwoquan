import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/rtc/rtc_signal_payloads.g.dart';

void main() {
  test('rtcWsKnownWireTypes 覆盖全部建模事件', () {
    expect(rtcWsKnownWireTypes.length, equals(11));
    expect(rtcWsKnownWireTypes, contains(rtcWsTypeCallRinging));
    expect(rtcWsKnownWireTypes, contains(rtcWsTypeCallEnded));
  });

  test('各已知 wireType 可解析为对应 WsPayload（非 Unknown）', () {
    final cases = <String, Type>{
      rtcWsTypeCallInitiated: RtcCallInitiatedWsPayload,
      rtcWsTypeCallRinging: RtcCallRingingWsPayload,
      rtcWsTypeCallAnswered: RtcCallAnsweredWsPayload,
      rtcWsTypeCallConnected: RtcCallConnectedWsPayload,
      rtcWsTypeCallEnded: RtcCallEndedWsPayload,
      rtcWsTypeParticipantJoined: RtcParticipantJoinedWsPayload,
      rtcWsTypeParticipantLeft: RtcParticipantLeftWsPayload,
      rtcWsTypeCallRecordingStarted: RtcCallRecordingStartedWsPayload,
      rtcWsTypeCallRecordingStopped: RtcCallRecordingStoppedWsPayload,
      rtcWsTypeScreenShareStarted: RtcScreenShareStartedWsPayload,
      rtcWsTypeScreenShareStopped: RtcScreenShareStoppedWsPayload,
    };
    for (final e in cases.entries) {
      final p = parseRtcWsPayload(wireType: e.key, payload: const {});
      expect(p.runtimeType, e.value, reason: e.key);
    }
  });
}
