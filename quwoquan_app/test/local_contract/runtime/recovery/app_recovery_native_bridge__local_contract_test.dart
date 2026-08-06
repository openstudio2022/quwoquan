// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cold-start-performance/spec.md#gwt-002
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/platform/app_recovery_native_bridge.dart';

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

  test('recovery context is bound to one effective launch manifest', () async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          if (call.method != 'getRecoveryContext') return null;
          return _validContext;
        });

    final context = await AppRecoveryNativeBridge(channel: channel).context();

    expect(context, isNotNull);
    expect(context!.runtimeBinding.environment.name, 'alpha');
    expect(
      context.runtimeBinding.recoveryOrigin,
      Uri.parse('https://api.alpha.quwoquan.com:17000'),
    );
    expect(
      context.runtimeBinding.effectiveLaunchManifestDigest,
      _effectiveManifestDigest,
    );
  });

  test(
    'recovery context rejects missing candidate identity and URL query',
    () async {
      for (final invalid in <Map<String, Object>>[
        <String, Object>{..._validContext, 'runtimeConfigDigest': ''},
        <String, Object>{
          ..._validContext,
          'recoveryBaseUrl': 'https://api.alpha.quwoquan.com:17000?target=beta',
        },
      ]) {
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
            .setMockMethodCallHandler(channel, (call) async {
              if (call.method != 'getRecoveryContext') return null;
              return invalid;
            });

        expect(
          await AppRecoveryNativeBridge(channel: channel).context(),
          isNull,
        );
      }
    },
  );

  test('native bridges project the same candidate-bound recovery identity', () {
    final android = File(
      'android/app/src/main/java/com/quwoquan/quwoquan_app/MainActivity.java',
    ).readAsStringSync();
    final ios = File('ios/Runner/AppDelegate.swift').readAsStringSync();
    for (final field in <String>[
      'environment',
      'recoveryBaseUrl',
      'runtimeConfigDigest',
      'effectiveLaunchManifestDigest',
    ]) {
      expect(android, contains('"$field"'));
      expect(ios, contains('"$field"'));
    }
    final gateway = File(
      'lib/runtime/shell/recovery/recovery_operation_gateway.dart',
    ).readAsStringSync();
    final controller = File(
      'lib/runtime/shell/recovery/startup_recovery_controller.dart',
    ).readAsStringSync();
    expect(gateway, isNot(contains('fromCompileTime')));
    for (final forbidden in <String>[
      'runtime/di/',
      'runtime/transport/',
      'quwoquan_cloud_contracts',
      'GeneratedCloudOperationClient',
    ]) {
      expect(gateway, isNot(contains(forbidden)));
    }
    expect(
      File(
        'lib/service/product_ops_service/product_ops/app_release/adapters/'
        'remote_app_release_recovery_reader.dart',
      ).readAsStringSync(),
      contains('opsAppReleaseGetAppRecoveryVersion'),
    );
    expect(
      File(
        'lib/service/product_ops_service/product_ops/recovery_failure/adapters/'
        'remote_recovery_failure_writer.dart',
      ).readAsStringSync(),
      contains('opsRecoveryFailureReportRecoveryFailure'),
    );
    expect(controller, isNot(contains('this.recoveryBaseUrl')));
  });
}

const _runtimeConfigDigest =
    'sha256:1111111111111111111111111111111111111111111111111111111111111111';
const _effectiveManifestDigest =
    'sha256:2222222222222222222222222222222222222222222222222222222222222222';
const _validContext = <String, Object>{
  'platform': 'android',
  'appVersion': '1.8.2',
  'buildNumber': 18201,
  'osVersion': '15',
  'deviceModel': 'Pixel',
  'environment': 'alpha',
  'recoveryBaseUrl': 'https://api.alpha.quwoquan.com:17000',
  'runtimeConfigDigest': _runtimeConfigDigest,
  'effectiveLaunchManifestDigest': _effectiveManifestDigest,
  'publicWebUrl': 'https://alpha.quwoquan.com:17000',
  'appDownloadBaseUrl': 'https://cdn.alpha.quwoquan.com:17100/download',
};
