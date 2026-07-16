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

    test('shareWebpageCard 在未支持平台上返回 unavailable', () async {
      final result = await bridge.shareWebpageCard(
        const NativeShareWebpageCard(
          requestId: 'request-1',
          target: NativeShareTarget.wechatFriend,
          title: 'title',
          description: 'description',
          webpageUrl: 'https://www.quwoquan.cn/posts/1',
        ),
      );
      expect(result.target, NativeShareTarget.wechatFriend);
      expect(result.outcome, NativeShareOutcome.unavailable);
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

    test('shareWebpageCard 只把 sendReq 接受解析为 accepted', () async {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, (call) async {
            expect(call.method, 'shareWebpageCard');
            final arguments = (call.arguments as Map).cast<String, dynamic>();
            expect(arguments['target'], NativeShareTarget.wechatFriend.name);
            expect(arguments['requestId'], 'request-1');
            expect(arguments['title'], 'title');
            expect(arguments['description'], 'description');
            expect(arguments['webpageUrl'], 'https://www.quwoquan.cn/posts/1');
            return <String, Object?>{
              'target': NativeShareTarget.wechatFriend.name,
              'requestId': 'request-1',
              'outcome': 'accepted',
              'reason': 'official_sdk',
            };
          });
      final bridge = MethodChannelNativeShareBridge(channel: channel);

      final result = await bridge.shareWebpageCard(
        const NativeShareWebpageCard(
          requestId: 'request-1',
          target: NativeShareTarget.wechatFriend,
          title: 'title',
          description: 'description',
          webpageUrl: 'https://www.quwoquan.cn/posts/1',
        ),
      );

      expect(result.target, NativeShareTarget.wechatFriend);
      expect(result.isAccepted, isTrue);
      expect(result.isCompleted, isFalse);
      expect(result.reason, 'official_sdk');
    });

    test('非 HTTPS 网页卡在 Dart 防腐层 fail closed', () async {
      final bridge = MethodChannelNativeShareBridge(channel: channel);

      final result = await bridge.shareWebpageCard(
        const NativeShareWebpageCard(
          requestId: 'request-2',
          target: NativeShareTarget.wechatMoments,
          title: 'title',
          description: 'description',
          webpageUrl: 'http://insecure.example.com/posts/1',
        ),
      );

      expect(result.outcome, NativeShareOutcome.failed);
      expect(result.reason, 'invalid_webpage_card');
    });
  });
}
