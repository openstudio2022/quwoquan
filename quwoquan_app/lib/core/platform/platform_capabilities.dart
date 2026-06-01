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
    required this.realtimeCommunication,
    required this.incomingCallUi,
    required this.nativeVideoEditing,
    required this.secureStorage,
    required this.backgroundAudio,
    required this.wideScreenLayout,
    required this.promotesAppInstall,
    required this.oneTapLogin,
  });

  /// Local random-access file system (`dart:io File/Directory`). False on web.
  final bool hasLocalFileSystem;

  /// System photo/video gallery access (album browsing, save-to-gallery).
  final bool mediaLibrary;

  /// Live camera capture.
  final bool camera;

  /// Real-time audio/video (WebRTC / LiveKit) availability.
  final bool realtimeCommunication;

  /// Native incoming-call UI (CallKit / VoIP / system call screen).
  final bool incomingCallUi;

  /// Native video trim/mute/export via platform channel.
  final bool nativeVideoEditing;

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

  PlatformCapabilities copyWith({
    bool? hasLocalFileSystem,
    bool? mediaLibrary,
    bool? camera,
    bool? realtimeCommunication,
    bool? incomingCallUi,
    bool? nativeVideoEditing,
    bool? secureStorage,
    bool? backgroundAudio,
    bool? wideScreenLayout,
    bool? promotesAppInstall,
    bool? oneTapLogin,
  }) {
    return PlatformCapabilities(
      hasLocalFileSystem: hasLocalFileSystem ?? this.hasLocalFileSystem,
      mediaLibrary: mediaLibrary ?? this.mediaLibrary,
      camera: camera ?? this.camera,
      realtimeCommunication:
          realtimeCommunication ?? this.realtimeCommunication,
      incomingCallUi: incomingCallUi ?? this.incomingCallUi,
      nativeVideoEditing: nativeVideoEditing ?? this.nativeVideoEditing,
      secureStorage: secureStorage ?? this.secureStorage,
      backgroundAudio: backgroundAudio ?? this.backgroundAudio,
      wideScreenLayout: wideScreenLayout ?? this.wideScreenLayout,
      promotesAppInstall: promotesAppInstall ?? this.promotesAppInstall,
      oneTapLogin: oneTapLogin ?? this.oneTapLogin,
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
    realtimeCommunication: true,
    incomingCallUi: true,
    nativeVideoEditing: true,
    secureStorage: true,
    backgroundAudio: true,
    wideScreenLayout: false,
    promotesAppInstall: false,
    oneTapLogin: true,
  );

  static const PlatformCapabilities web = PlatformCapabilities(
    hasLocalFileSystem: false,
    mediaLibrary: true,
    camera: true,
    realtimeCommunication: true,
    incomingCallUi: false,
    nativeVideoEditing: false,
    secureStorage: false,
    backgroundAudio: false,
    wideScreenLayout: true,
    promotesAppInstall: true,
    oneTapLogin: false,
  );

  // HarmonyOS / OpenHarmony initial baseline. RTC / incoming-call / native
  // video editing are deferred to their own milestone (see cross-platform spec).
  static const PlatformCapabilities ohos = PlatformCapabilities(
    hasLocalFileSystem: true,
    mediaLibrary: true,
    camera: true,
    realtimeCommunication: false,
    incomingCallUi: false,
    nativeVideoEditing: false,
    secureStorage: true,
    backgroundAudio: true,
    wideScreenLayout: false,
    promotesAppInstall: false,
    oneTapLogin: false,
  );

  static const PlatformCapabilities desktop = PlatformCapabilities(
    hasLocalFileSystem: true,
    mediaLibrary: false,
    camera: false,
    realtimeCommunication: true,
    incomingCallUi: false,
    nativeVideoEditing: false,
    secureStorage: true,
    backgroundAudio: true,
    wideScreenLayout: true,
    promotesAppInstall: false,
    oneTapLogin: false,
  );
}

/// Resolves the capability baseline for a platform.
PlatformCapabilities platformCapabilitiesFor(AppPlatform platform) {
  switch (platform) {
    case AppPlatform.android:
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
