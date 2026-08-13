// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-005
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-005.t3
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('rtcWsKnownWireTypes 覆盖全部建模事件', () {
    expect(rtcWsKnownWireTypes.length, equals(9));
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
      rtcWsTypeScreenShareStarted: RtcScreenShareStartedWsPayload,
      rtcWsTypeScreenShareStopped: RtcScreenShareStoppedWsPayload,
    };
    for (final e in cases.entries) {
      final p = parseRtcWsPayload(wireType: e.key, payload: const {});
      expect(p.runtimeType, e.value, reason: e.key);
    }
  });
}
