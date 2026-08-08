import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/platform/native_runtime_config_bridge.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const channel = MethodChannel('quwoquan/runtime/config');
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;

  tearDown(() {
    messenger.setMockMethodCallHandler(channel, null);
  });

  test('Hot Restart 通道短暂未就绪时有界重试同一 native package', () async {
    var attempts = 0;
    messenger.setMockMethodCallHandler(channel, (call) async {
      expect(call.method, 'readRuntimeConfig');
      attempts += 1;
      if (attempts == 1) {
        return const <String, String>{};
      }
      return const <String, String>{
        'APP_RUNTIME_ENV': 'gamma',
        'APP_LAUNCH_POLICY': 'test_live',
      };
    });

    final package = await NativeRuntimeConfigBridge.readRuntimePackage();

    expect(attempts, 2);
    expect(package['APP_RUNTIME_ENV'], 'gamma');
    expect(package['APP_LAUNCH_POLICY'], 'test_live');
  });

  test('native package 持续不可用时仍返回空包供严格配置校验阻断', () async {
    var attempts = 0;
    messenger.setMockMethodCallHandler(channel, (call) async {
      attempts += 1;
      return const <String, String>{};
    });

    final package = await NativeRuntimeConfigBridge.readRuntimePackage();

    expect(attempts, 3);
    expect(package, isEmpty);
  });
}
