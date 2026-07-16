import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/rtc/incoming_call_coordinator.dart';
import 'package:quwoquan_app/core/platform/platform_capabilities.dart';
import 'package:quwoquan_app/core/platform/platform_target.dart';

void main() {
  // ──────────────────────────────────────────────────────────────────
  // S6 来电平台矩阵：来电唤醒通道由能力位单一派生（无裸平台判断）。
  // ──────────────────────────────────────────────────────────────────
  group('resolveIncomingCallChannel — 三端能力矩阵', () {
    test('mobile（CallKit/全屏意图）→ nativeCallKit', () {
      expect(
        resolveIncomingCallChannel(CapabilityProfile.mobile),
        IncomingCallChannel.nativeCallKit,
      );
    });

    test('web（Web Push + 站内）→ webPushInApp', () {
      expect(
        resolveIncomingCallChannel(CapabilityProfile.web),
        IncomingCallChannel.webPushInApp,
      );
    });

    test('ohos 初始基线（无 RTC）→ unsupported', () {
      expect(
        resolveIncomingCallChannel(CapabilityProfile.ohos),
        IncomingCallChannel.unsupported,
      );
    });

    test('desktop（有 RTC，无原生来电屏/无 Web Push）→ inAppOnly', () {
      expect(
        resolveIncomingCallChannel(CapabilityProfile.desktop),
        IncomingCallChannel.inAppOnly,
      );
    });

    test('RTC 不可用时强制 unsupported（优先级最高）', () {
      final caps = CapabilityProfile.mobile.copyWith(
        realtimeCommunication: false,
      );
      expect(resolveIncomingCallChannel(caps), IncomingCallChannel.unsupported);
    });

    test('原生来电屏优先于 Web Push', () {
      final caps = CapabilityProfile.mobile.copyWith(
        incomingCallUi: true,
        webPushIncomingCall: true,
      );
      expect(
        resolveIncomingCallChannel(caps),
        IncomingCallChannel.nativeCallKit,
      );
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 能力位与平台基线一致性：incomingCallUi / webPushIncomingCall 互斥语义。
  // ──────────────────────────────────────────────────────────────────
  group('PlatformCapabilities — 来电能力位基线', () {
    test('mobile：原生来电屏开、Web Push 关', () {
      final caps = platformCapabilitiesFor(AppPlatform.ios);
      expect(caps.incomingCallUi, isTrue);
      expect(caps.webPushIncomingCall, isFalse);
      expect(caps.realtimeCommunication, isTrue);
      expect(caps.appleNativeLogin, isTrue);
      expect(caps.wechatNativeLogin, isTrue);
      expect(caps.systemCredentialLogin, isTrue);
      expect(caps.passkeyLogin, isTrue);
    });

    test('web：原生来电屏关、Web Push 开', () {
      final caps = platformCapabilitiesFor(AppPlatform.web);
      expect(caps.incomingCallUi, isFalse);
      expect(caps.webPushIncomingCall, isTrue);
      expect(caps.realtimeCommunication, isTrue);
      expect(caps.systemCredentialLogin, isFalse);
      expect(caps.passkeyLogin, isFalse);
    });

    test('ohos 初始：RTC/来电均关', () {
      final caps = platformCapabilitiesFor(AppPlatform.ohos);
      expect(caps.realtimeCommunication, isFalse);
      expect(caps.incomingCallUi, isFalse);
      expect(caps.webPushIncomingCall, isFalse);
      expect(caps.wechatNativeLogin, isFalse);
      expect(caps.appleNativeLogin, isFalse);
      expect(caps.systemCredentialLogin, isFalse);
      expect(caps.passkeyLogin, isFalse);
    });

    test('android：微信与系统凭据入口可见，Apple 关闭', () {
      final caps = platformCapabilitiesFor(AppPlatform.android);
      expect(caps.wechatNativeLogin, isTrue);
      expect(caps.appleNativeLogin, isFalse);
      expect(caps.systemCredentialLogin, isTrue);
      expect(caps.passkeyLogin, isTrue);
    });
  });
}
