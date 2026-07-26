import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/platform/platform_capabilities.dart';
import 'package:quwoquan_app/core/platform/platform_providers.dart';
import 'package:quwoquan_app/core/platform/platform_target.dart';

/// Example "behavior contract" decided purely from capabilities (not platform).
///
/// This mirrors how UI/providers should gate entries: ask the capability, not
/// "am I on web/ohos". The same contract is then exercised under every
/// CapabilityProfile, and only the *difference boundary* is asserted per
/// profile (see rule 14, R-XP9 / cross-platform-portability spec §测试 profile).
bool shouldShowVideoEditingEntry(PlatformCapabilities caps) =>
    caps.nativeVideoEditing;

bool shouldShowIncomingCallSettings(PlatformCapabilities caps) =>
    caps.incomingCallUi;

bool shouldUseWideShell(PlatformCapabilities caps) => caps.wideScreenLayout;

bool shouldShowWechatLogin(PlatformCapabilities caps) => caps.wechatNativeLogin;

bool canUseTargetedWechatShare(PlatformCapabilities caps) =>
    caps.wechatTargetedShare;

bool canUseSystemShareSheet(PlatformCapabilities caps) => caps.systemShareSheet;

bool shouldShowSystemCredentialLogin(PlatformCapabilities caps) =>
    caps.systemCredentialLogin;

bool shouldShowPhoneContactsEntry(PlatformCapabilities caps) => caps.contacts;

PlatformCapabilities _resolve(PlatformCapabilities profile) {
  final container = ProviderContainer(
    overrides: [platformCapabilitiesProvider.overrideWithValue(profile)],
  );
  addTearDown(container.dispose);
  return container.read(platformCapabilitiesProvider);
}

void main() {
  group('capability-first behavior contract (profile-driven)', () {
    // Same contract, three platform profiles — no duplicated test bodies.
    final profiles = <String, PlatformCapabilities>{
      'mobile': CapabilityProfile.mobile,
      'web': CapabilityProfile.web,
      'ohos': CapabilityProfile.ohos,
    };

    for (final entry in profiles.entries) {
      test('${entry.key}: entries follow capability flags', () {
        final caps = _resolve(entry.value);
        expect(
          shouldShowVideoEditingEntry(caps),
          caps.nativeVideoEditing,
          reason: 'video editing entry must mirror nativeVideoEditing',
        );
        expect(shouldShowIncomingCallSettings(caps), caps.incomingCallUi);
        expect(shouldUseWideShell(caps), caps.wideScreenLayout);
        expect(shouldShowWechatLogin(caps), caps.wechatNativeLogin);
        expect(canUseTargetedWechatShare(caps), caps.wechatTargetedShare);
        expect(canUseSystemShareSheet(caps), caps.systemShareSheet);
        expect(
          shouldShowSystemCredentialLogin(caps),
          caps.systemCredentialLogin,
        );
        expect(
          shouldShowPhoneContactsEntry(caps),
          caps.contacts,
          reason: 'phone contacts entry must mirror contacts capability',
        );
      });
    }

    // Difference boundaries: assert only the cross-platform divergence.
    test('只有已有原生实现的 iOS 显示视频编辑，Android/Web/OHOS 降级', () {
      expect(
        shouldShowVideoEditingEntry(
          platformCapabilitiesFor(AppPlatform.ios),
        ),
        isTrue,
      );
      expect(
        shouldShowVideoEditingEntry(
          platformCapabilitiesFor(AppPlatform.android),
        ),
        isFalse,
      );
      expect(shouldShowVideoEditingEntry(CapabilityProfile.web), isFalse);
      expect(shouldShowVideoEditingEntry(CapabilityProfile.ohos), isFalse);
    });

    test('only web uses the wide shell among mobile/web/ohos', () {
      expect(shouldUseWideShell(CapabilityProfile.web), isTrue);
      expect(shouldUseWideShell(CapabilityProfile.mobile), isFalse);
      expect(shouldUseWideShell(CapabilityProfile.ohos), isFalse);
    });

    test('mobile profile exposes credential login while web/ohos degrade', () {
      expect(shouldShowSystemCredentialLogin(CapabilityProfile.mobile), isTrue);
      expect(shouldShowSystemCredentialLogin(CapabilityProfile.web), isFalse);
      expect(shouldShowSystemCredentialLogin(CapabilityProfile.ohos), isFalse);
    });

    test('only mobile exposes phone contacts among mobile/web/ohos', () {
      expect(shouldShowPhoneContactsEntry(CapabilityProfile.mobile), isTrue);
      expect(shouldShowPhoneContactsEntry(CapabilityProfile.web), isFalse);
      expect(shouldShowPhoneContactsEntry(CapabilityProfile.ohos), isFalse);
    });

    test('微信定向分享与系统分享能力分离', () {
      expect(canUseTargetedWechatShare(CapabilityProfile.mobile), isFalse);
      expect(canUseSystemShareSheet(CapabilityProfile.mobile), isTrue);
      expect(canUseTargetedWechatShare(CapabilityProfile.web), isFalse);
      expect(canUseSystemShareSheet(CapabilityProfile.web), isTrue);
      expect(canUseTargetedWechatShare(CapabilityProfile.ohos), isFalse);
      expect(canUseSystemShareSheet(CapabilityProfile.ohos), isFalse);
    });

    test('Android 平台启用微信定向分享桥，iOS 仍降级系统分享', () {
      final androidCaps = platformCapabilitiesFor(AppPlatform.android);
      final iosCaps = platformCapabilitiesFor(AppPlatform.ios);
      expect(androidCaps.wechatTargetedShare, isTrue);
      expect(androidCaps.systemShareSheet, isTrue);
      expect(iosCaps.wechatTargetedShare, isFalse);
      expect(iosCaps.systemShareSheet, isTrue);
    });
  });
}
