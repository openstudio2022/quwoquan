// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-021
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/platform/media/native_orientation_reader.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel(nativeOrientationChannel);
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  tearDown(() => messenger.setMockMethodCallHandler(channel, null));
  test('生产reader只消费fresh typed原生结果', () async {
    var rotation = 0;
    messenger.setMockMethodCallHandler(channel, (call) async {
      expect(call.method, nativeOrientationMethod);
      return {
        'status': 'available',
        'platform': 'android',
        'binding': 'window',
        'axis': 'portrait',
        'rotation': rotation,
      };
    });
    const reader = NativeOrientationReader();
    expect((await reader.read())!.rotation, 0);
    rotation = 180;
    expect((await reader.read())!.rotation, 180);
  });
  test('缺失平台与非法wire都不可用，无默认portrait', () async {
    const reader = NativeOrientationReader();
    expect(await reader.read(), isNull);
    for (final payload in [
      {
        'status': 'available',
        'platform': 'ios',
        'binding': 'window',
        'axis': 'portrait',
        'rotation': 0,
      },
      {
        'status': 'available',
        'platform': 'android',
        'binding': '',
        'axis': 'portrait',
        'rotation': 0,
      },
      {
        'status': 'available',
        'platform': 'ios',
        'binding': 'window',
        'orientation': 'faceUp',
      },
      {'status': 'unavailable', 'platform': 'ios', 'orientation': 'portraitUp'},
    ]) {
      messenger.setMockMethodCallHandler(channel, (_) async => payload);
      expect(await reader.read(), isNull);
    }
  });
}
