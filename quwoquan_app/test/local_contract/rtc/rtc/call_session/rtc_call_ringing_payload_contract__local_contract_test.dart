import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  group('RtcCallRingingPayload (metadata-driven)', () {
    test('manifest keys 与 events.yaml payload 字段一致（codegen 单一源）', () {
      expect(
        rtcCallRingingPayloadWireKeys,
        equals(<String>[
          'eventId',
          'callId',
          'targetPersonaId',
          'callType',
          'callerName',
          'callerAvatarUrl',
          'sourceLabel',
          'trustRelation',
          'expiresAt',
          'deliveryKey',
        ]),
      );
    });

    test('fromWire：最小 map + 默认值 callType=audio + 扩展 callerName', () {
      final minimal = <String, dynamic>{
        for (final k in rtcCallRingingPayloadWireKeys) k: null,
        'callerName': 'Alice',
      };
      final p = RtcCallRingingPayload.fromWire(minimal);
      expect(p.callType, CallType.audio);
      expect(p.callerName, equals('Alice'));
      for (final k in rtcCallRingingPayloadWireKeys) {
        expect(minimal.containsKey(k), isTrue, reason: k);
      }
    });
  });
}
