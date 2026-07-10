import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/platform/native_bridge.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

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

  group('UnsupportedNativeShareBridge', () {
    const bridge = UnsupportedNativeShareBridge();

    test('所有 target 默认返回 unavailable capability', () async {
      for (final target in NativeShareTarget.values) {
        final capability = await bridge.getCapability(target);
        expect(capability.target, target);
        expect(capability.isAvailable, isFalse);
        expect(capability.reason, 'unsupported_platform');
      }
    });

    test('shareText 在未支持平台上返回 unavailable', () async {
      final result = await bridge.shareText(
        target: NativeShareTarget.wechatFriend,
        text: 'text',
        subject: 'subject',
      );
      expect(result.target, NativeShareTarget.wechatFriend);
      expect(result.isDelivered, isFalse);
      expect(result.reason, 'unsupported_platform');
    });
  });

  group('MethodChannelNativeShareBridge', () {
    const channel = MethodChannel('quwoquan/share/native_bridge');

    tearDown(() {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, null);
    });

    test('getCapability 解析原生可用状态', () async {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, (call) async {
            expect(call.method, 'getCapability');
            expect(call.arguments, <String, dynamic>{
              'target': NativeShareTarget.wechatMoments.name,
            });
            return <String, Object?>{
              'available': true,
              'reason': 'android_intent',
            };
          });
      final bridge = MethodChannelNativeShareBridge(channel: channel);

      final capability = await bridge.getCapability(
        NativeShareTarget.wechatMoments,
      );

      expect(capability.target, NativeShareTarget.wechatMoments);
      expect(capability.isAvailable, isTrue);
      expect(capability.reason, 'android_intent');
    });

    test('shareText 解析原生投递状态', () async {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, (call) async {
            expect(call.method, 'shareText');
            expect(call.arguments, <String, dynamic>{
              'target': NativeShareTarget.wechatFriend.name,
              'text': 'hello',
              'subject': 'title',
            });
            return <String, Object?>{
              'delivered': true,
              'reason': 'android_intent',
            };
          });
      final bridge = MethodChannelNativeShareBridge(channel: channel);

      final result = await bridge.shareText(
        target: NativeShareTarget.wechatFriend,
        text: 'hello',
        subject: 'title',
      );

      expect(result.target, NativeShareTarget.wechatFriend);
      expect(result.isDelivered, isTrue);
      expect(result.reason, 'android_intent');
    });
  });
}
