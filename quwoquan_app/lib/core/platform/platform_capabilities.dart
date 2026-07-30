import 'package:flutter/foundation.dart';

import 'package:quwoquan_app/core/platform/platform_target.dart';

/// Capability contract: the ONLY thing business / UI code is allowed to ask
/// about the runtime environment.
///
/// Pages and providers must decide "show this entry / how to degrade" based on
/// these capability flags, never on [AppPlatform] or `Platform.isX` / `kIsWeb`.
/// Adding a platform = add one [CapabilityProfile] + platform implementations,
/// with zero business-layer edits.
@immutable
class PlatformCapabilities {
  const PlatformCapabilities({
    required this.hasLocalFileSystem,
    required this.mediaLibrary,
    required this.camera,
    required this.contacts,
    required this.realtimeCommunication,
    required this.incomingCallUi,
    required this.webPushIncomingCall,
    required this.nativeVideoEditing,
    required this.adaptiveVideoPlayback,
    required this.secureStorage,
    required this.backgroundAudio,
    required this.wideScreenLayout,
    required this.promotesAppInstall,
    required this.oneTapLogin,
    required this.wechatNativeLogin,
    required this.alipayNativeLogin,
    required this.qqNativeLogin,
    required this.wechatTargetedShare,
    required this.systemShareSheet,
    required this.appleNativeLogin,
    required this.systemCredentialLogin,
    required this.passkeyLogin,
    required this.quickLoginPersistence,
  });

  /// Local random-access file system (`dart:io File/Directory`). False on web.
  final bool hasLocalFileSystem;

  /// System photo/video gallery access (album browsing, save-to-gallery).
  final bool mediaLibrary;

  /// Live camera capture.
  final bool camera;

  /// System address book (device contacts) read access.
  ///
  /// True on mobile (iOS/Android). False on web / desktop and the initial ohos
  /// baseline (no flutter_contacts support yet); business code hides the
  /// "phone contacts" entry and degrades gracefully when this is false.
  final bool contacts;

  /// Real-time audio/video (WebRTC / LiveKit) availability.
  final bool realtimeCommunication;

  /// Native incoming-call UI (CallKit / VoIP / system call screen).
  ///
  /// True on mobile (iOS CallKit / Android 全屏意图)；web / desktop / 初始 ohos
  /// 无原生来电屏，需走 [webPushIncomingCall] 或站内弹窗降级。
  final bool incomingCallUi;

  /// Web Push + Service Worker 后台来电通知能力。
  ///
  /// 当前所有平台均为 false：Web RTC 只支持前台 realtime 站内来电，不伪装已具备
  /// Service Worker 后台接听链。原生端使用 [incomingCallUi]。
  final bool webPushIncomingCall;

  /// Native video trim/mute/export via platform channel.
  final bool nativeVideoEditing;

  /// Native player can consume the repository HLS/CMAF profile and perform ABR.
  ///
  /// This is deliberately conservative: only the Android/iOS player baseline is
  /// enabled. Web requires an owned HLS runtime and desktop/OHOS require device
  /// matrix evidence before their profiles can opt in.
  final bool adaptiveVideoPlayback;

  /// Hardware-backed secure key/value storage.
  final bool secureStorage;

  /// Background / lock-screen audio playback.
  final bool backgroundAudio;

  /// Wide-screen multi-column shell (desktop / web wide layout).
  final bool wideScreenLayout;

  /// Whether the runtime should promote installing the native app.
  ///
  /// Web sets this to true so the shell can show the top install banner.
  /// Native runtimes keep it false; business code should still read the
  /// capability rather than asking whether it is running on web.
  final bool promotesAppInstall;

  /// Carrier / vendor one-tap login SDK.
  final bool oneTapLogin;

  /// WeChat native OpenSDK login.
  final bool wechatNativeLogin;

  /// Alipay native authorization login.
  final bool alipayNativeLogin;

  /// QQ native OpenSDK login.
  final bool qqNativeLogin;

  /// WeChat native OpenSDK targeted share.
  ///
  /// This is intentionally separate from [wechatNativeLogin]: login can be
  /// available before the share SDK / app id / universal-link contract is
  /// landed. Business UI should keep the WeChat entry semantics, then degrade
  /// through [systemShareSheet] when this is false.
  final bool wechatTargetedShare;

  /// System share sheet / platform share sheet availability.
  final bool systemShareSheet;

  /// Apple native sign-in / AuthenticationServices entry.
  final bool appleNativeLogin;

  /// System credential entry (Android Credential Manager / iOS Password AutoFill).
  final bool systemCredentialLogin;

  /// WebAuthn / passkey entry available for this platform.
  final bool passkeyLogin;

  /// 是否可在本机安全存储中长期持有"快速登录凭证"（软退出后有效期内免验证码登录）。
  ///
  /// 个人设备（手机/iPad/桌面）为 true：refresh 凭证存安全存储，退出后有效期内可一键恢复。
  /// Web 为 false：凭证生命周期由浏览器 cookies/会话控制，端侧不长期持有，
  /// 业务层据此决定 returning 主按钮是否提供一键登录（只看会话是否仍在）。
  final bool quickLoginPersistence;

  PlatformCapabilities copyWith({
    bool? hasLocalFileSystem,
    bool? mediaLibrary,
    bool? camera,
    bool? contacts,
    bool? realtimeCommunication,
    bool? incomingCallUi,
    bool? webPushIncomingCall,
    bool? nativeVideoEditing,
    bool? adaptiveVideoPlayback,
    bool? secureStorage,
    bool? backgroundAudio,
    bool? wideScreenLayout,
    bool? promotesAppInstall,
    bool? oneTapLogin,
    bool? wechatNativeLogin,
    bool? alipayNativeLogin,
    bool? qqNativeLogin,
    bool? wechatTargetedShare,
    bool? systemShareSheet,
    bool? appleNativeLogin,
    bool? systemCredentialLogin,
    bool? passkeyLogin,
    bool? quickLoginPersistence,
  }) {
    return PlatformCapabilities(
      hasLocalFileSystem: hasLocalFileSystem ?? this.hasLocalFileSystem,
      mediaLibrary: mediaLibrary ?? this.mediaLibrary,
      camera: camera ?? this.camera,
      contacts: contacts ?? this.contacts,
      realtimeCommunication:
          realtimeCommunication ?? this.realtimeCommunication,
      incomingCallUi: incomingCallUi ?? this.incomingCallUi,
      webPushIncomingCall: webPushIncomingCall ?? this.webPushIncomingCall,
      nativeVideoEditing: nativeVideoEditing ?? this.nativeVideoEditing,
      adaptiveVideoPlayback:
          adaptiveVideoPlayback ?? this.adaptiveVideoPlayback,
      secureStorage: secureStorage ?? this.secureStorage,
      backgroundAudio: backgroundAudio ?? this.backgroundAudio,
      wideScreenLayout: wideScreenLayout ?? this.wideScreenLayout,
      promotesAppInstall: promotesAppInstall ?? this.promotesAppInstall,
      oneTapLogin: oneTapLogin ?? this.oneTapLogin,
      wechatNativeLogin: wechatNativeLogin ?? this.wechatNativeLogin,
      alipayNativeLogin: alipayNativeLogin ?? this.alipayNativeLogin,
      qqNativeLogin: qqNativeLogin ?? this.qqNativeLogin,
      wechatTargetedShare: wechatTargetedShare ?? this.wechatTargetedShare,
      systemShareSheet: systemShareSheet ?? this.systemShareSheet,
      appleNativeLogin: appleNativeLogin ?? this.appleNativeLogin,
      systemCredentialLogin:
          systemCredentialLogin ?? this.systemCredentialLogin,
      passkeyLogin: passkeyLogin ?? this.passkeyLogin,
      quickLoginPersistence:
          quickLoginPersistence ?? this.quickLoginPersistence,
    );
  }
}

/// Initial per-platform capability baselines.
///
/// These are conservative defaults: high-risk capabilities (RTC, incoming
/// call, native video editing) start disabled on newly-added platforms and are
/// flipped on per milestone once their implementations land. Tests inject these
/// profiles via `platformCapabilitiesProvider` overrides instead of mocking the
/// whole environment.
class CapabilityProfile {
  const CapabilityProfile._();

  static const PlatformCapabilities mobile = PlatformCapabilities(
    hasLocalFileSystem: true,
    mediaLibrary: true,
    camera: true,
    contacts: true,
    realtimeCommunication: true,
    incomingCallUi: true,
    webPushIncomingCall: false,
    nativeVideoEditing: true,
    adaptiveVideoPlayback: true,
    secureStorage: true,
    backgroundAudio: true,
    wideScreenLayout: false,
    promotesAppInstall: false,
    oneTapLogin: true,
    wechatNativeLogin: true,
    alipayNativeLogin: true,
    qqNativeLogin: true,
    wechatTargetedShare: false,
    systemShareSheet: true,
    appleNativeLogin: true,
    systemCredentialLogin: true,
    passkeyLogin: true,
    quickLoginPersistence: true,
  );

  static const PlatformCapabilities web = PlatformCapabilities(
    hasLocalFileSystem: false,
    mediaLibrary: true,
    camera: true,
    contacts: false,
    realtimeCommunication: true,
    incomingCallUi: false,
    webPushIncomingCall: false,
    nativeVideoEditing: false,
    adaptiveVideoPlayback: false,
    secureStorage: false,
    backgroundAudio: false,
    wideScreenLayout: true,
    promotesAppInstall: true,
    oneTapLogin: false,
    wechatNativeLogin: false,
    alipayNativeLogin: false,
    qqNativeLogin: false,
    wechatTargetedShare: false,
    systemShareSheet: true,
    appleNativeLogin: false,
    systemCredentialLogin: false,
    passkeyLogin: false,
    quickLoginPersistence: false,
  );

  // HarmonyOS / OpenHarmony initial baseline. RTC / incoming-call / native
  // video editing are deferred to their own milestone (see cross-platform spec).
  static const PlatformCapabilities ohos = PlatformCapabilities(
    hasLocalFileSystem: true,
    mediaLibrary: true,
    camera: true,
    contacts: false,
    realtimeCommunication: false,
    incomingCallUi: false,
    webPushIncomingCall: false,
    nativeVideoEditing: false,
    adaptiveVideoPlayback: false,
    secureStorage: true,
    backgroundAudio: true,
    wideScreenLayout: false,
    promotesAppInstall: false,
    oneTapLogin: false,
    wechatNativeLogin: false,
    alipayNativeLogin: false,
    qqNativeLogin: false,
    wechatTargetedShare: false,
    systemShareSheet: false,
    appleNativeLogin: false,
    systemCredentialLogin: false,
    passkeyLogin: false,
    quickLoginPersistence: true,
  );

  static const PlatformCapabilities desktop = PlatformCapabilities(
    hasLocalFileSystem: true,
    mediaLibrary: false,
    camera: false,
    contacts: false,
    realtimeCommunication: true,
    incomingCallUi: false,
    webPushIncomingCall: false,
    nativeVideoEditing: false,
    adaptiveVideoPlayback: false,
    secureStorage: true,
    backgroundAudio: true,
    wideScreenLayout: true,
    promotesAppInstall: false,
    oneTapLogin: false,
    wechatNativeLogin: false,
    alipayNativeLogin: false,
    qqNativeLogin: false,
    wechatTargetedShare: false,
    systemShareSheet: true,
    appleNativeLogin: false,
    systemCredentialLogin: false,
    passkeyLogin: false,
    quickLoginPersistence: true,
  );
}

/// Resolves the capability baseline for a platform.
PlatformCapabilities platformCapabilitiesFor(AppPlatform platform) {
  switch (platform) {
    case AppPlatform.android:
      return CapabilityProfile.mobile.copyWith(
        appleNativeLogin: false,
        wechatTargetedShare: true,
        // 当前 video_editing MethodChannel 仅有 iOS 实现；Android 必须隐藏
        // trim/mute/export 入口，不能让用户点击后才收到 UnsupportedError。
        nativeVideoEditing: false,
      );
    case AppPlatform.ios:
      return CapabilityProfile.mobile;
    case AppPlatform.web:
      return CapabilityProfile.web;
    case AppPlatform.ohos:
      return CapabilityProfile.ohos;
    case AppPlatform.desktop:
      return CapabilityProfile.desktop;
  }
}
