import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/platform/native_bridge.dart';

void main() {
  group('UnsupportedNativeAuthBridge', () {
    const bridge = UnsupportedNativeAuthBridge();

    test('所有 provider 默认返回 unavailable capability', () async {
      for (final provider in NativeAuthProvider.values) {
        final capability = await bridge.getCapability(provider);
        expect(capability.provider, provider);
        expect(capability.isAvailable, isFalse);
        expect(capability.reason, 'unsupported_platform');
      }
    });

    test('signIn 在未支持平台上抛出结构化错误', () async {
      await expectLater(
        () => bridge.signIn(NativeAuthProvider.wechat),
        throwsA(isA<StateError>()),
      );
    });

    test('signInWithPasskey 在未支持平台上抛出结构化错误', () async {
      await expectLater(
        () => bridge.signInWithPasskey(),
        throwsA(isA<StateError>()),
      );
    });
  });
}
