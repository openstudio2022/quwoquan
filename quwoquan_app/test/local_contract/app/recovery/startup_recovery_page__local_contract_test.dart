// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cold-start-performance/spec.md#gwt-002
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/app/recovery/recovery_surface.dart';
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
            };
          }
          if (call.method == 'openTrustedExternalUrl') return true;
          return null;
        });
    final controller = StartupRecoveryController(
      nativeBridge: AppRecoveryNativeBridge(channel: channel),
      recoveryBaseUrl: 'https://api.quwoquan.com',
      versionClient: RecoveryVersionClient(
        client: MockClient(
          (_) async => http.Response(
            '{"latestVersion":"1.8.2","latestBuild":"18201",'
            '"updateUrl":"https://quwoquan.com/download/android",'
            '"recoveryUrl":"https://quwoquan.com/recovery"}',
            200,
          ),
        ),
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
    controller.dispose();
  });
}
