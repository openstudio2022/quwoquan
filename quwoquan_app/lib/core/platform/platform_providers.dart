import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:quwoquan_app/core/platform/file_storage_gateway.dart';
import 'package:quwoquan_app/core/platform/native_bridge.dart';
import 'package:quwoquan_app/core/platform/platform_capabilities.dart';
import 'package:quwoquan_app/core/platform/platform_target.dart';

/// Current platform (assembly/observability only — do NOT branch on this in
/// business code; consume [platformCapabilitiesProvider] instead).
final platformTargetProvider = Provider<AppPlatform>(
  (ref) => currentAppPlatform,
);

/// Capability contract for the current platform. This is the business layer's
/// single entry point for "is X available / how do I degrade". Tests override
/// this with `CapabilityProfile.mobile|web|ohos` to drive the same behavior
/// contract across platforms.
final platformCapabilitiesProvider = Provider<PlatformCapabilities>(
  (ref) => platformCapabilitiesFor(ref.watch(platformTargetProvider)),
);

/// Local file/path access behind the anti-corruption boundary.
final fileStorageGatewayProvider = Provider<FileStorageGateway>(
  (ref) => createFileStorageGateway(),
);

/// Native assistant local-context bridge, capability-gated. Platforms without a
/// native provider get the unsupported (empty-context) implementation.
final assistantLocalContextBridgeProvider =
    Provider<AssistantLocalContextBridge>((ref) {
  // Reuse the secureStorage/native availability as a proxy for "has a native
  // host"; web/ohos-initial fall back to the unsupported bridge.
  final platform = ref.watch(platformTargetProvider);
  switch (platform) {
    case AppPlatform.android:
    case AppPlatform.ios:
      return MethodChannelAssistantLocalContextBridge();
    case AppPlatform.web:
    case AppPlatform.ohos:
    case AppPlatform.desktop:
      return const UnsupportedAssistantLocalContextBridge();
  }
});
