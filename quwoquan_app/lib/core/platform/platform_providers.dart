import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:quwoquan_app/core/platform/file_storage_gateway.dart';
import 'package:quwoquan_app/core/platform/firebase_incoming_call_runtime.dart';
import 'package:quwoquan_app/core/platform/incoming_call_native_bridge.dart';
import 'package:quwoquan_app/core/platform/native_bridge.dart';
import 'package:quwoquan_app/core/platform/platform_capabilities.dart';
import 'package:quwoquan_app/core/platform/platform_target.dart';
import 'package:quwoquan_app/core/platform/push_endpoint_gateway.dart';

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

/// Stable observability label assembled inside the platform boundary.
///
/// UI and business code may attach this label to telemetry, but must not branch
/// on the target platform itself.
final platformTelemetryNameProvider = Provider<String>(
  (ref) => platformWireName(ref.watch(platformTargetProvider)),
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

/// Native auth bridge for provider-backed social/system credential entrypoints.
///
/// Production composition never branches to fixtures by environment. Mobile
/// platforms use the real method-channel adapter; unsupported platforms return
/// a structured unavailable capability. Alpha fixtures are injected only by
/// the physically separate alpha runner.
final nativeAuthBridgeProvider = Provider<NativeAuthBridge>((ref) {
  final platform = ref.watch(platformTargetProvider);
  switch (platform) {
    case AppPlatform.android:
    case AppPlatform.ios:
      return MethodChannelNativeAuthBridge();
    case AppPlatform.web:
    case AppPlatform.ohos:
    case AppPlatform.desktop:
      return const UnsupportedNativeAuthBridge();
  }
});

/// Native share bridge for targeted external-share entrypoints.
///
/// Android currently owns a best-effort WeChat package/intent implementation;
/// unsupported platforms return structured unavailable so callers can degrade
/// through the system share sheet.
final nativeShareBridgeProvider = Provider<NativeShareBridge>((ref) {
  final platform = ref.watch(platformTargetProvider);
  switch (platform) {
    case AppPlatform.android:
      return MethodChannelNativeShareBridge();
    case AppPlatform.ios:
    case AppPlatform.web:
    case AppPlatform.ohos:
    case AppPlatform.desktop:
      return const UnsupportedNativeShareBridge();
  }
});

/// 来电原生桥只在 iOS / Android 装配；Web/OHOS/desktop 统一返回 typed 空能力。
final incomingCallNativeBridgeProvider = Provider<IncomingCallNativeBridge>((
  ref,
) {
  final platform = ref.watch(platformTargetProvider);
  switch (platform) {
    case AppPlatform.android:
    case AppPlatform.ios:
      return const MethodChannelIncomingCallNativeBridge();
    case AppPlatform.web:
    case AppPlatform.ohos:
    case AppPlatform.desktop:
      return const UnsupportedIncomingCallNativeBridge();
  }
});

/// APNs VoIP 原生 queue 与 Dart FCM queue 的统一持久化入口。
final pushEndpointGatewayProvider = Provider<PushEndpointGateway>(
  (ref) => PersistentPushEndpointGateway(),
);

/// Firebase 只在防腐层内部判断 Android；业务仅消费 runtime state/capability。
final firebaseIncomingCallRuntimeProvider =
    Provider<FirebaseIncomingCallRuntime>((ref) {
      final runtime = FirebaseIncomingCallRuntime(
        pushEndpointGateway: ref.watch(pushEndpointGatewayProvider),
      );
      ref.onDispose(() {
        unawaited(runtime.stop());
      });
      return runtime;
    });
