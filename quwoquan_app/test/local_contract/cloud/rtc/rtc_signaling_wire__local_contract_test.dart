import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/rtc/rtc_signal_payloads.g.dart';
import 'package:quwoquan_app/cloud/rtc/rtc_signaling_client.dart';
import 'package:quwoquan_app/cloud/rtc/rtc_signaling_wire.dart';
import 'package:quwoquan_app/cloud/rtc/rtc_signaling_wire_frame.dart';

void main() {
  group('decodeRtcSignalingJsonMessage', () {
    test('String 帧解析为 Map', () {
      final m = decodeRtcSignalingJsonMessage(
        RtcSignalingWireFrame.fromChannelData(
          '{"type":"call.ringing","callId":"c1","payload":{}}',
        ),
      );
      expect(m, isNotNull);
      expect(m!['type'], equals('call.ringing'));
    });

    test('UTF-8 bytes 帧解析为 Map', () {
      final bytes = utf8.encode('{"type":"pong"}');
      final m = decodeRtcSignalingJsonMessage(
        RtcSignalingWireFrame.fromChannelData(bytes),
      );
      expect(m, isNotNull);
      expect(m!['type'], equals('pong'));
    });

    test('非 JSON / 非 Map 返回 null', () {
      expect(
        decodeRtcSignalingJsonMessage(
          RtcSignalingWireFrame.fromChannelData(42),
        ),
        isNull,
      );
      expect(
        decodeRtcSignalingJsonMessage(
          RtcSignalingWireFrame.fromChannelData('"just a string"'),
        ),
        isNull,
      );
      expect(
        decodeRtcSignalingJsonMessage(
          RtcSignalingWireFrame.fromChannelData('{broken'),
        ),
        isNull,
      );
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
      expect((e.payload as RtcCallRingingWsPayload).data.callType, equals('video'));
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
}
