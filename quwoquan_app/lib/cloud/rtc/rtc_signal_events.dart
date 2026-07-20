import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/rtc/rtc_signal_payloads.g.dart';

/// rtc 通话事件（经 realtime 单通道 rt:rtc:user:{userId} 下发）。
/// 事件 envelope：{type, callId, actorId, payload}，type 与
/// events.yaml client_ws_type 同源（call.ringing / call.ended / ...）。
class RtcSignalEvent {
  final String type;
  final String callId;
  final String? actorId;

  /// 已按 `events.yaml` / [parseRtcWsPayload] 解析；未知 `type` 为 [RtcWsUnknownPayload]。
  final RtcWsPayload payload;

  const RtcSignalEvent({
    required this.type,
    required this.callId,
    this.actorId,
    required this.payload,
  });

  factory RtcSignalEvent.fromJson(Map<String, dynamic> json) {
    final p = json['payload'];
    final payloadMap = p is Map<String, dynamic>
        ? p
        : p is Map
        ? Map<String, dynamic>.from(p)
        : <String, dynamic>{};
    final type = json['type'] as String? ?? '';
    return RtcSignalEvent(
      type: type,
      callId: json['callId'] as String? ?? '',
      actorId: json['actorId'] as String?,
      payload: parseRtcWsPayload(wireType: type, payload: payloadMap),
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

  void emit(Map<String, dynamic> json) {
    _events.add(RtcSignalEvent.fromJson(json));
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
