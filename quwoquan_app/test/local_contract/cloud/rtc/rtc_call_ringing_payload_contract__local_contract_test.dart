import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/rtc/rtc_signal_payloads.g.dart';

void main() {
  group('RtcCallRingingPayload (metadata-driven)', () {
    test('manifest keys 与 events.yaml payload 字段一致（codegen 单一源）', () {
      expect(
        rtcCallRingingPayloadWireKeys,
        containsAll(<String>[
          'callId',
          'callType',
          'initiatorId',
          'initiatorRingtoneId',
          'targetUserId',
          'conversationId',
        ]),
      );
      // 信任两态（SIT3）扩展：来源标签 / 信任关系 / 链接过期，均为可选客户端字符串。
      expect(
        rtcCallRingingOptionalClientStringWireKeys,
        equals(<String>[
          'callerName',
          'sourceLabel',
          'trustRelation',
          'expiresAt',
        ]),
      );
    });

    test('fromWire：最小 map + 默认值 callType=voice + 扩展 callerName', () {
      final minimal = <String, dynamic>{
        for (final k in rtcCallRingingPayloadWireKeys) k: null,
        'callerName': 'Alice',
      };
      final p = RtcCallRingingPayload.fromWire(minimal);
      expect(p.callType, equals('voice'));
      expect(p.callerName, equals('Alice'));
      for (final k in rtcCallRingingPayloadWireKeys) {
        expect(minimal.containsKey(k), isTrue, reason: k);
      }
    });
  });
}
