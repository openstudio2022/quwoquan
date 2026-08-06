import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/remote_api_path_test_harness.dart';

/// 与 `quwoquan_service/services/rtc-service/contracts/rtc/call_session/operations.yaml` 经 codegen 生成的路径常量对齐（防漂移）。
void main() {
  group('RTC canonical operation contract — 与 rtc-service 契约', () {
    test('核心 operation 路径与方法', () {
      expect(
        canonicalRemoteApiPath(AppCloudOperationIds.rtcCallSessionInitiateCall),
        equals('/rtc/calls'),
      );
      expect(
        canonicalRemoteApiOperation(
          AppCloudOperationIds.rtcCallSessionInitiateCall,
        ).method,
        equals('POST'),
      );
      expect(
        canonicalRemoteApiPath(AppCloudOperationIds.rtcCallSessionListCalls),
        equals('/rtc/calls'),
      );
      expect(
        canonicalRemoteApiOperation(
          AppCloudOperationIds.rtcCallSessionListCalls,
        ).method,
        equals('GET'),
      );
      expect(
        canonicalRemoteApiPath(
          AppCloudOperationIds.rtcCallSessionJoinCall,
          pathParameters: const <String, String>{'callId': 'x'},
        ),
        equals('/rtc/calls/x/join'),
      );
      expect(
        canonicalRemoteApiPath(
          AppCloudOperationIds.rtcCallSessionToggleMute,
          pathParameters: const <String, String>{'callId': 'y'},
        ),
        equals('/rtc/calls/y/mute'),
      );
    });

    test('canonical registry 覆盖主要动词', () {
      for (final operationId in <String>[
        AppCloudOperationIds.rtcCallSessionInitiateCall,
        AppCloudOperationIds.rtcCallSessionListCalls,
        AppCloudOperationIds.rtcCallSessionGetCall,
        AppCloudOperationIds.rtcCallSessionJoinCall,
        AppCloudOperationIds.rtcCallSessionInviteToCall,
        AppCloudOperationIds.rtcCallSessionToggleMute,
        AppCloudOperationIds.rtcCallSessionToggleCamera,
      ]) {
        expect(
          canonicalRemoteApiOperation(operationId).objectId,
          'rtc.call_session',
        );
      }
    });
  });
}
