import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/rtc/rtc_api_metadata.g.dart';

/// 与 `contracts/metadata/rtc/call_session/service.yaml` 经 codegen 生成的路径常量对齐（防漂移）。
void main() {
  group('RtcApiMetadata — 与 rtc-service 契约', () {
    test('核心 operation 路径与方法', () {
      expect(RtcApiMetadata.initiateCallPath, equals('/v1/rtc/calls'));
      expect(
        RtcApiMetadata.operationToMethod['InitiateCall'],
        equals('POST'),
      );
      expect(RtcApiMetadata.listCallsPath, equals('/v1/rtc/calls'));
      expect(
        RtcApiMetadata.operationToMethod['ListCalls'],
        equals('GET'),
      );
      expect(
        RtcApiMetadata.joinCallPath(callId: 'x'),
        equals('/v1/rtc/calls/x/join'),
      );
      expect(
        RtcApiMetadata.toggleMutePath(callId: 'y'),
        equals('/v1/rtc/calls/y/mute'),
      );
    });

    test('operationToPathTemplate 覆盖主要动词', () {
      final keys = RtcApiMetadata.operationToPathTemplate.keys.toSet();
      expect(keys, containsAll(<String>[
        'InitiateCall',
        'ListCalls',
        'GetCall',
        'JoinCall',
        'InviteToCall',
        'ToggleMute',
        'ToggleCamera',
      ]));
    });
  });
}
