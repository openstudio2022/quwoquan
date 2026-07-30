// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cold-start-performance/spec.md#gwt-002
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/platform/app_recovery_native_bridge.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('test/quwoquan/app_recovery/fatal-marker');

  tearDown(() async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, null);
  });

  test(
    'fatal marker request binds canonical attempt and failure code',
    () async {
      MethodCall? received;
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, (call) async {
            received = call;
            return true;
          });

      final recorded = await AppRecoveryNativeBridge(channel: channel)
          .recordFatalStartup(
            attemptId: 'startup_attempt_01',
            failureCode: 'OPS.SYSTEM.startup_configuration_invalid',
          );

      expect(recorded, isTrue);
      expect(received?.method, 'recordFatalStartup');
      expect(received?.arguments, <String, String>{
        'attemptId': 'startup_attempt_01',
        'failureCode': 'OPS.SYSTEM.startup_configuration_invalid',
      });
    },
  );

  test(
    'fatal marker request fails closed on missing context or native refusal',
    () async {
      var invocationCount = 0;
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, (call) async {
            invocationCount += 1;
            return false;
          });
      final bridge = AppRecoveryNativeBridge(channel: channel);

      expect(
        await bridge.recordFatalStartup(
          attemptId: ' ',
          failureCode: 'OPS.SYSTEM.startup_initialization_failed',
        ),
        isFalse,
      );
      expect(invocationCount, 0);
      expect(
        await bridge.recordFatalStartup(
          attemptId: 'startup_attempt_02',
          failureCode: 'OPS.SYSTEM.startup_initialization_failed',
        ),
        isFalse,
      );
      expect(invocationCount, 1);
    },
  );
}
