import 'package:flutter/foundation.dart';

import 'package:quwoquan_app/core/platform/platform_os_io.dart'
    if (dart.library.js_interop) 'package:quwoquan_app/core/platform/platform_os_web.dart';

/// The set of runtime platforms the app targets (current + planned).
///
/// `AppPlatform` is the single source of truth for "which platform am I on",
/// but it is intended ONLY for the anti-corruption layer (`lib/core/platform/**`)
/// to assemble platform implementations and for observability tagging.
///
/// Business / UI code MUST NOT branch on `AppPlatform`. It should consume
/// `PlatformCapabilities` instead (capability-first), so that adding a new
/// platform requires zero business-layer changes.
enum AppPlatform {
  android,
  ios,
  ohos,
  web,
  desktop,
}

/// Resolves the current platform once, web-safely.
///
/// `kIsWeb` takes precedence (so web never touches `dart:io`); otherwise the
/// native OS name is mapped, including HarmonyOS / OpenHarmony (`ohos`).
AppPlatform get currentAppPlatform {
  if (kIsWeb) {
    return AppPlatform.web;
  }
  switch (readNativeOperatingSystem()) {
    case 'android':
      return AppPlatform.android;
    case 'ios':
      return AppPlatform.ios;
    case 'ohos':
      return AppPlatform.ohos;
    case 'macos':
    case 'windows':
    case 'linux':
      return AppPlatform.desktop;
    default:
      // Unknown native OS: fall back to the Flutter target platform so that
      // analytics still resolve to a sensible value rather than crashing.
      switch (defaultTargetPlatform) {
        case TargetPlatform.iOS:
          return AppPlatform.ios;
        case TargetPlatform.android:
          return AppPlatform.android;
        case TargetPlatform.macOS:
        case TargetPlatform.windows:
        case TargetPlatform.linux:
        case TargetPlatform.fuchsia:
          return AppPlatform.desktop;
      }
  }
}

/// Stable wire name used in headers / telemetry. Aligns with the cloud-side
/// `X-Client-Device-Platform` enum (metadata-first when adding values).
String platformWireName(AppPlatform platform) {
  switch (platform) {
    case AppPlatform.android:
      return 'android';
    case AppPlatform.ios:
      return 'ios';
    case AppPlatform.ohos:
      return 'ohos';
    case AppPlatform.web:
      return 'web';
    case AppPlatform.desktop:
      return 'desktop';
  }
}
