import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// rtc 通话事件（经 realtime 单通道 rt:rtc:user:{userId} 下发）。
/// 事件 envelope：{type, callId, actorId, payload}，type 与
/// events.yaml client_ws_type 同源（call.ringing / call.ended / ...）。
class RtcSignalEvent {
  final String type;
  final String callId;
  final String? actorId;

  /// 已由共享 [RealtimeEventEnvelope] tagged union 按 `events.yaml` 解析。
  final RtcWsPayload payload;

  const RtcSignalEvent({
    required this.type,
    required this.callId,
    this.actorId,
    required this.payload,
  });

  factory RtcSignalEvent.fromEnvelope(RtcRealtimeEventEnvelope envelope) {
    final payload = envelope.payload;
    return RtcSignalEvent(
      type: envelope.wireType,
      callId: _rtcPayloadCallId(payload),
      actorId: _rtcPayloadActorId(payload),
      payload: payload,
    );
  }
}

/// rtc 事件是否属于通话信令 wire 命名空间（realtime 通道复用判定）。
bool isRtcSignalWireType(String type) {
  return type.startsWith('call.') ||
      type.startsWith('participant.') ||
      type.startsWith('screen_share.');
}

/// realtime 单通道到达的 rtc 事件总线：由 RealtimeMessageHandler 投递，
/// IncomingCallCoordinator 与通话页订阅。替代已删除的独立信令 WebSocket。
class RtcSignalEventBus {
  final _events = StreamController<RtcSignalEvent>.broadcast();

  Stream<RtcSignalEvent> get events => _events.stream;

  Stream<RtcSignalEvent> get incomingCalls =>
      events.where((e) => e.payload is RtcCallRingingWsPayload);

  Stream<RtcSignalEvent> get callEnded =>
      events.where((e) => e.payload is RtcCallEndedWsPayload);

  Stream<RtcSignalEvent> get callAnswered =>
      events.where((e) => e.payload is RtcCallAnsweredWsPayload);

  void emit(RealtimeEventEnvelope envelope) {
    if (envelope is! RtcRealtimeEventEnvelope) {
      throw FormatException(
        'RTC event bus requires RtcRealtimeEventEnvelope, got ${envelope.wireType}',
      );
    }
    _events.add(RtcSignalEvent.fromEnvelope(envelope));
  }

  void dispose() {
    _events.close();
  }
}

final rtcSignalEventBusProvider = Provider<RtcSignalEventBus>((ref) {
  final bus = RtcSignalEventBus();
  ref.onDispose(bus.dispose);
  return bus;
});

String _rtcPayloadCallId(RtcWsPayload payload) => switch (payload) {
  RtcCallInitiatedWsPayload(:final data) => data.callId ?? '',
  RtcCallRingingWsPayload(:final data) => data.callId ?? '',
  RtcCallAnsweredWsPayload(:final data) => data.callId ?? '',
  RtcCallConnectedWsPayload(:final data) => data.callId ?? '',
  RtcCallEndedWsPayload(:final data) => data.callId ?? '',
  RtcParticipantJoinedWsPayload(:final data) => data.callId ?? '',
  RtcParticipantLeftWsPayload(:final data) => data.callId ?? '',
  RtcScreenShareStartedWsPayload(:final data) => data.callId ?? '',
  RtcScreenShareStoppedWsPayload(:final data) => data.callId ?? '',
};

String? _rtcPayloadActorId(RtcWsPayload payload) => switch (payload) {
  RtcCallInitiatedWsPayload(:final data) => data.initiatorId,
  RtcCallAnsweredWsPayload(:final data) => data.userId,
  RtcCallConnectedWsPayload(:final data) => data.userId,
  RtcParticipantJoinedWsPayload(:final data) => data.userId,
  RtcParticipantLeftWsPayload(:final data) => data.userId,
  RtcScreenShareStartedWsPayload(:final data) => data.userId,
  RtcScreenShareStoppedWsPayload(:final data) => data.userId,
  RtcCallRingingWsPayload() || RtcCallEndedWsPayload() => null,
};
