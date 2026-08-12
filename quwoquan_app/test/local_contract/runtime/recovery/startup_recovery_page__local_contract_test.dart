// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cold-start-performance/spec.md#gwt-002
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/shell/recovery/startup_recovery_page.dart';
import 'package:quwoquan_app/runtime/shell/recovery/recovery_operation_gateway.dart';
import 'package:quwoquan_app/runtime/shell/recovery/recovery_state_machine.dart';
import 'package:quwoquan_app/runtime/shell/recovery/recovery_version_client.dart';
import 'package:quwoquan_app/runtime/shell/recovery/startup_recovery_controller.dart';
import 'package:quwoquan_app/runtime/platform/app_recovery_native_bridge.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('test/quwoquan/app_recovery');

  tearDown(() async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, null);
  });

  testWidgets('recovery page transitions from checking to confirmed update', (
    tester,
  ) async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          if (call.method == 'getRecoveryContext') {
            return <String, Object>{
              'platform': 'android',
              'appVersion': '1.8.1',
              'buildNumber': 18100,
              'osVersion': '15',
              'deviceModel': 'Pixel',
              'environment': 'alpha',
              'recoveryBaseUrl': 'https://api.quwoquan.com',
              'runtimeConfigDigest': 'sha256:${'1' * 64}',
              'effectiveLaunchManifestDigest': 'sha256:${'2' * 64}',
              'publicWebUrl': 'https://quwoquan.com',
              'appDownloadBaseUrl': 'https://cdn.quwoquan.com/download',
            };
          }
          if (call.method == 'openTrustedExternalUrl') return true;
          return null;
        });
    var versionCalls = 0;
    final controller = StartupRecoveryController(
      nativeBridge: AppRecoveryNativeBridge(channel: channel),
      versionClient: RecoveryVersionClient(
        gateway: _gateway(
          _VersionExecutor(() {
            versionCalls += 1;
            return <String, Object?>{
              'latestVersion': '1.8.2',
              'latestBuild': versionCalls == 1 ? '18201' : '18100',
              'minimumSupportedVersion': '1.8.0',
              'minimumSupportedBuild': '18000',
              'updateState': versionCalls == 1 ? 'available' : 'none',
              'updateUrl':
                  'https://cdn.quwoquan.com/download/android/latest.json',
              'recoveryUrl': 'https://quwoquan.com/',
            };
          }),
        ),
      ),
    );

    await tester.pumpWidget(
      MaterialApp(
        home: StartupRecoveryPage.routerError(controller: controller),
      ),
    );
    expect(find.text('应用暂时无法启动'), findsOneWidget);
    expect(find.text('使用网页版'), findsOneWidget);
    expect(find.byType(Icon), findsNothing);

    await tester.pump();
    await tester.pump(const Duration(milliseconds: 120));
    expect(find.text('发现新版本'), findsOneWidget);
    expect(find.text('可前往官方渠道更新，或继续使用当前版本'), findsOneWidget);
    expect(find.text('前往更新'), findsOneWidget);
    expect(find.textContaining('诊断'), findsNothing);
    expect(find.textContaining('重试'), findsNothing);

    await tester.tap(find.text('前往更新'));
    await tester.pump();
    controller.refreshVersionAfterExternalReturn();
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 120));
    expect(versionCalls, 2);
    expect(find.text('当前已是最新版本'), findsOneWidget);
    expect(find.text('前往更新'), findsNothing);
    controller.dispose();
  });

  testWidgets(
    'recovery actions remain available on a small large-text screen',
    (tester) async {
      await tester.binding.setSurfaceSize(const Size(320, 568));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final controller = StartupRecoveryController(
        initialSnapshot: const RecoverySnapshot(
          phase: RecoveryPhase.runtimeUnavailable,
        ),
      );

      await tester.pumpWidget(
        MaterialApp(
          home: MediaQuery(
            data: const MediaQueryData(
              size: Size(320, 568),
              textScaler: TextScaler.linear(2),
            ),
            child: StartupRecoveryPage.routerError(controller: controller),
          ),
        ),
      );

      expect(find.text('应用暂时无法继续使用'), findsOneWidget);
      expect(find.text('重新进入应用'), findsOneWidget);
      expect(find.text('使用网页版'), findsOneWidget);
      expect(tester.takeException(), isNull);
      controller.dispose();
    },
  );

  testWidgets('version timeout enters S3 without recording a fatal marker', (
    tester,
  ) async {
    var fatalMarkerRequests = 0;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          if (call.method == 'getRecoveryContext') {
            return <String, Object>{
              'platform': 'ios',
              'appVersion': '1.8.1',
              'buildNumber': 18100,
              'osVersion': '26.3',
              'deviceModel': 'iPhone',
              'environment': 'alpha',
              'recoveryBaseUrl': 'https://api.quwoquan.com',
              'runtimeConfigDigest': 'sha256:${'1' * 64}',
              'effectiveLaunchManifestDigest': 'sha256:${'2' * 64}',
              'publicWebUrl': 'https://quwoquan.com',
              'appDownloadBaseUrl': 'https://cdn.quwoquan.com/download',
            };
          }
          if (call.method == 'recordFatalStartup') {
            fatalMarkerRequests += 1;
          }
          return null;
        });
    final controller = StartupRecoveryController(
      nativeBridge: AppRecoveryNativeBridge(channel: channel),
      versionClient: RecoveryVersionClient(
        gateway: _gateway(
          _VersionExecutor(() => throw TimeoutException('offline')),
        ),
      ),
    );

    await tester.pumpWidget(
      MaterialApp(
        home: StartupRecoveryPage.routerError(controller: controller),
      ),
    );
    await tester.pump(const Duration(milliseconds: 1600));

    expect(controller.snapshot.phase, RecoveryPhase.startupVersionUnavailable);
    expect(find.text('应用暂时无法启动'), findsOneWidget);
    expect(fatalMarkerRequests, 0);
    controller.dispose();
  });
}

RecoveryOperationGateway _gateway(_VersionExecutor executor) {
  return RecoveryOperationGateway(operations: executor);
}

final class _VersionExecutor implements RecoveryRuntimeOperations {
  _VersionExecutor(this.response);

  final Object? Function() response;

  @override
  Future<RecoveryVersionResponse> getVersion(
    RecoveryVersionRequest request,
  ) async {
    final payload = response()! as Map<String, Object?>;
    return RecoveryVersionResponse(
      latestVersion: payload['latestVersion']! as String,
      latestBuild: int.parse(payload['latestBuild']! as String),
      minimumSupportedVersion: payload['minimumSupportedVersion']! as String,
      minimumSupportedBuild: int.parse(
        payload['minimumSupportedBuild']! as String,
      ),
      updateState: switch (payload['updateState']) {
        'none' => RecoveryUpdateState.none,
        'available' => RecoveryUpdateState.available,
        'required' => RecoveryUpdateState.required,
        _ => throw const FormatException('invalid update state'),
      },
      updateUrl: payload['updateUrl']! as String,
      recoveryUrl: payload['recoveryUrl']! as String,
    );
  }

  @override
  Future<void> reportFailure(RecoveryFailurePayload payload) =>
      throw UnsupportedError('not used by this recovery surface test');
}
