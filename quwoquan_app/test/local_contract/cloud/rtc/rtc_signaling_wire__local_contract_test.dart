import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/rtc/rtc_signal_payloads.g.dart';
import 'package:quwoquan_app/cloud/rtc/rtc_signal_events.dart';

void main() {
  group('isRtcSignalWireType', () {
    test('rtc 通话 wire 命名空间被识别并分发给事件总线', () {
      expect(isRtcSignalWireType('call.ringing'), isTrue);
      expect(isRtcSignalWireType('call.ended'), isTrue);
      expect(isRtcSignalWireType('participant.joined'), isTrue);
      expect(isRtcSignalWireType('screen_share.started'), isTrue);
    });

    test('chat 与推荐事件不属于 rtc 命名空间', () {
      expect(isRtcSignalWireType('MessageSent'), isFalse);
      expect(isRtcSignalWireType('ConversationRosterUpdated'), isFalse);
      expect(isRtcSignalWireType('feed.patch'), isFalse);
    });
  });

  group('parseRtcWsPayload', () {
    test('已知 client_ws_type 映射到对应 WsPayload', () {
      final p = parseRtcWsPayload(
        wireType: rtcWsTypeCallRinging,
        payload: const <String, dynamic>{'callType': 'video'},
      );
      expect(p, isA<RtcCallRingingWsPayload>());
      expect((p as RtcCallRingingWsPayload).data.callType, equals('video'));
    });

    test('未知 type → RtcWsUnknownPayload', () {
      final p = parseRtcWsPayload(
        wireType: 'x.unknown',
        payload: const <String, dynamic>{'a': 1},
      );
      expect(p, isA<RtcWsUnknownPayload>());
      final u = p as RtcWsUnknownPayload;
      expect(u.wireType, equals('x.unknown'));
      expect(u.raw['a'], equals(1));
    });
  });

  group('RtcSignalEvent.fromJson', () {
    test('payload 非 Map<String,dynamic> 仍可解析为具体 WsPayload', () {
      final raw = <String, dynamic>{
        'type': 'call.ringing',
        'callId': 'c1',
        'payload': <String, Object?>{'callType': 'video'},
      };
      final e = RtcSignalEvent.fromJson(raw);
      expect(e.payload, isA<RtcCallRingingWsPayload>());
      expect(
        (e.payload as RtcCallRingingWsPayload).data.callType,
        equals('video'),
      );
    });

    test('payload 缺失或类型错误 → 空 map 解析；未知 type → Unknown', () {
      final e1 = RtcSignalEvent.fromJson(<String, dynamic>{
        'type': 'x',
        'callId': 'c',
        'payload': 'not-a-map',
      });
      expect(e1.payload, isA<RtcWsUnknownPayload>());

      final e2 = RtcSignalEvent.fromJson(<String, dynamic>{
        'type': 'x',
        'callId': 'c',
      });
      expect(e2.payload, isA<RtcWsUnknownPayload>());
    });
  });

  group('RtcSignalEventBus', () {
    test('emit 后按 payload 类型过滤的流收到事件', () async {
      final bus = RtcSignalEventBus();
      addTearDown(bus.dispose);

      final ringing = bus.incomingCalls.first;
      bus.emit(<String, dynamic>{
        'type': 'call.ringing',
        'callId': 'c-bus',
        'payload': <String, dynamic>{'callType': 'audio'},
      });
      expect((await ringing).callId, equals('c-bus'));
    });
  });
}
