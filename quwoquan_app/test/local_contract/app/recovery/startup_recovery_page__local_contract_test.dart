// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cold-start-performance/spec.md#gwt-002
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/app/recovery/recovery_surface.dart';
import 'package:quwoquan_app/app/recovery/recovery_state_machine.dart';
import 'package:quwoquan_app/app/recovery/recovery_version_client.dart';
import 'package:quwoquan_app/app/recovery/startup_recovery_controller.dart';
import 'package:quwoquan_app/core/platform/app_recovery_native_bridge.dart';

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
              'recoveryBaseUrl': 'https://api.quwoquan.com',
              'publicWebUrl': 'https://quwoquan.com',
            };
          }
          if (call.method == 'openTrustedExternalUrl') return true;
          return null;
        });
    var versionCalls = 0;
    final controller = StartupRecoveryController(
      nativeBridge: AppRecoveryNativeBridge(channel: channel),
      recoveryBaseUrl: 'https://api.quwoquan.com',
      versionClient: RecoveryVersionClient(
        client: MockClient((_) async {
          versionCalls += 1;
          return http.Response(
            '{"latestVersion":"1.8.2","latestBuild":"${versionCalls == 1 ? '18201' : '18100'}",'
            '"updateUrl":"https://quwoquan.com/download/android",'
            '"recoveryUrl":"https://quwoquan.com/recovery"}',
            200,
          );
        }),
      ),
    );

    await tester.pumpWidget(
      MaterialApp(home: StartupRecoveryPage(controller: controller)),
    );
    expect(find.text('应用暂时无法启动'), findsOneWidget);
    expect(find.text('使用网页版'), findsOneWidget);
    expect(find.byType(Icon), findsNothing);

    await tester.pump();
    await tester.pump(const Duration(milliseconds: 120));
    expect(find.text('当前版本需要更新'), findsOneWidget);
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
            child: StartupRecoveryPage(controller: controller),
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
}
