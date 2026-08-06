import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/rtc_signal_events.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

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
      expect((p as RtcCallRingingWsPayload).data.callType, CallType.video);
    });

    test('未知 type 失败关闭', () {
      expect(
        () => parseRtcWsPayload(
          wireType: 'x.unknown',
          payload: const <String, dynamic>{'a': 1},
        ),
        throwsFormatException,
      );
    });
  });

  group('RtcSignalEvent.fromEnvelope', () {
    test('共享 tagged union 提供同一 RTC payload 与 call identity', () {
      final envelope = RealtimeEventEnvelope.fromWire(<String, Object?>{
        'type': 'call.ringing',
        'eventId': 'event-1',
        'occurredAt': '2026-08-04T10:00:00Z',
        'payload': <String, Object?>{
          'eventId': 'event-1',
          'callId': 'c1',
          'targetPersonaId': 'persona-2',
          'callType': 'video',
          'callerName': 'Alice',
          'callerAvatarUrl': '',
          'sourceLabel': 'conversation',
          'trustRelation': 'contact',
          'expiresAt': '2026-08-04T10:00:30Z',
          'deliveryKey': 'delivery-1',
        },
      });
      final e = RtcSignalEvent.fromEnvelope(
        envelope as RtcRealtimeEventEnvelope,
      );
      expect(e.callId, 'c1');
      expect(e.payload, isA<RtcCallRingingWsPayload>());
      expect(
        (e.payload as RtcCallRingingWsPayload).data.callType,
        CallType.video,
      );
    });

    test('未知 type 与非对象 payload 均失败关闭', () {
      expect(
        () => RealtimeEventEnvelope.fromWire(<String, Object?>{
          'type': 'x.unknown',
          'occurredAt': '2026-08-04T10:00:00Z',
          'payload': <String, Object?>{},
        }),
        throwsFormatException,
      );
      expect(
        () => RealtimeEventEnvelope.fromWire(<String, Object?>{
          'type': 'call.answered',
          'occurredAt': '2026-08-04T10:00:00Z',
          'payload': 'not-a-map',
        }),
        throwsFormatException,
      );
    });
  });

  group('RtcSignalEventBus', () {
    test('emit 后按 payload 类型过滤的流收到事件', () async {
      final bus = RtcSignalEventBus();
      addTearDown(bus.dispose);

      final ringing = bus.incomingCalls.first;
      bus.emit(RealtimeEventEnvelope.fromWire(<String, Object?>{
        'type': 'call.ringing',
        'occurredAt': '2026-08-04T10:00:00Z',
        'payload': <String, Object?>{
          'eventId': 'event-bus',
          'callId': 'c-bus',
          'targetPersonaId': 'persona-2',
          'callType': 'audio',
          'callerName': 'Alice',
          'callerAvatarUrl': '',
          'sourceLabel': 'conversation',
          'trustRelation': 'contact',
          'expiresAt': '2026-08-04T10:00:30Z',
          'deliveryKey': 'delivery-bus',
        },
      }));
      expect((await ringing).callId, equals('c-bus'));
    });
  });
}
