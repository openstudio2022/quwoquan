import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:quwoquan_app/runtime/platform/assistant_device_action_bridge.dart';
import 'package:quwoquan_app/runtime/platform/call_audio_session_gateway.dart';
import 'package:quwoquan_app/runtime/platform/contacts/device_contacts_gateway.dart';
import 'package:quwoquan_app/runtime/platform/contacts/flutter_contacts_device_contacts_gateway.dart';
import 'package:quwoquan_app/runtime/platform/device_calendar_bridge.dart';
import 'package:quwoquan_app/runtime/platform/file_storage_gateway.dart';
import 'package:quwoquan_app/runtime/platform/firebase_incoming_call_runtime.dart';
import 'package:quwoquan_app/runtime/platform/incoming_call_native_bridge.dart';
import 'package:quwoquan_app/runtime/platform/native_bridge.dart';
import 'package:quwoquan_app/runtime/platform/platform_capabilities.dart';
import 'package:quwoquan_app/runtime/platform/platform_target.dart';
import 'package:quwoquan_app/runtime/platform/push_endpoint_gateway.dart';
import 'package:quwoquan_app/runtime/platform/screen_wake_gateway.dart';
import 'package:quwoquan_app/runtime/platform/web_install_context.dart';

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

/// System contacts are exposed only through the platform anti-corruption
/// boundary. Unsupported platforms receive a structured fail-closed gateway.
final deviceContactsGatewayProvider = Provider<DeviceContactsGateway>((ref) {
  if (!ref.watch(platformCapabilitiesProvider).contacts) {
    return const UnsupportedDeviceContactsGateway();
  }
  return const FlutterContactsDeviceContactsGateway();
});

/// Assistant auth has not yet exposed a generated opaque-permit verifier.
///
/// Production therefore remains fail-closed. Tests override this object-level
/// port with a suite-local verifier; no environment composition may do so.
final deviceCalendarPermitVerifierProvider =
    Provider<DeviceCalendarPermitVerifier>(
      (ref) => const FailClosedDeviceCalendarPermitVerifier(),
    );

/// Local installation/device binding for permit claim comparison.
///
/// The empty production binding is intentional until the generated assistant
/// auth binding port lands. It cannot be filled from caller-controlled input.
final deviceCalendarLocalBindingProvider = Provider<DeviceCalendarLocalBinding>(
  (ref) => const DeviceCalendarLocalBinding.unavailable(),
);

final deviceCalendarBridgeProvider = Provider<DeviceCalendarBridge>((ref) {
  final capabilities = ref.watch(platformCapabilitiesProvider);
  if (!capabilities.deviceCalendar) {
    return const UnsupportedDeviceCalendarBridge();
  }
  return MethodChannelDeviceCalendarBridge(
    permitVerifier: ref.watch(deviceCalendarPermitVerifierProvider),
    localBinding: ref.watch(deviceCalendarLocalBindingProvider),
  );
});

final assistantDeviceActionBridgeProvider =
    Provider<AssistantDeviceActionBridge>((ref) {
      final platform = ref.watch(platformTargetProvider);
      switch (platform) {
        case AppPlatform.android:
        case AppPlatform.ios:
          return const MethodChannelAssistantDeviceActionBridge();
        case AppPlatform.web:
        case AppPlatform.ohos:
        case AppPlatform.desktop:
          return const UnsupportedAssistantDeviceActionBridge();
      }
    });

/// Stable observability label assembled inside the platform boundary.
///
/// UI and business code may attach this label to telemetry, but must not branch
/// on the target platform itself.
final platformTelemetryNameProvider = Provider<String>(
  (ref) => platformWireName(ref.watch(platformTargetProvider)),
);

/// Web 安装推荐只读取非唯一化的平台能力信号，不参与版本判断。
final webInstallContextProvider = Provider<WebInstallContext>(
  (ref) => readWebInstallContext(),
);

/// 屏幕常亮防腐入口：通话等长驻前台场景保持屏幕不熄灭。
///
/// OHOS 暂无 wakelock 插件支持，装配一致降级实现（R-XP5）；其余平台由
/// wakelock_plus 承载，失败在 gateway 内部降级不打断业务。
final screenWakeGatewayProvider = Provider<ScreenWakeGateway>((ref) {
  switch (ref.watch(platformTargetProvider)) {
    case AppPlatform.android:
    case AppPlatform.ios:
    case AppPlatform.web:
    case AppPlatform.desktop:
      return const WakelockScreenWakeGateway();
    case AppPlatform.ohos:
      return const UnsupportedScreenWakeGateway();
  }
});

/// RTC 通话音频会话防腐入口：playAndRecord 激活、中断与 becomingNoisy
/// 事实流。移动端由 audio_session 承载；其余平台一致降级（R-XP5），
/// 通话不因音频会话能力缺失而失败。
final callAudioSessionGatewayProvider = Provider<CallAudioSessionGateway>((
  ref,
) {
  switch (ref.watch(platformTargetProvider)) {
    case AppPlatform.android:
    case AppPlatform.ios:
      return AudioSessionCallAudioSessionGateway();
    case AppPlatform.web:
    case AppPlatform.ohos:
    case AppPlatform.desktop:
      return const UnsupportedCallAudioSessionGateway();
  }
});

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
///
/// `pushDelivery` 能力关闭平台装配 fail-safe 空实现：注册/反注册/清理结构化
/// 跳过，不触达安全存储与原生通道（R-XP1/R-XP5）。
final pushEndpointGatewayProvider = Provider<PushEndpointGateway>((ref) {
  if (!ref.watch(platformCapabilitiesProvider).pushDelivery) {
    return const UnsupportedPushEndpointGateway();
  }
  return PersistentPushEndpointGateway();
});

final firebasePushMessagingClientProvider =
    Provider<FirebasePushMessagingClient>((ref) {
      return const FirebasePluginPushMessagingClient();
    });

final firebasePushMessagingRuntimeProvider =
    Provider<FirebasePushMessagingRuntime>((ref) {
      final platform = ref.watch(platformTargetProvider);
      final runtime = FirebasePushMessagingRuntime(
        client: ref.watch(firebasePushMessagingClientProvider),
        platformReader: () => platform,
      );
      ref.onDispose(() {
        unawaited(runtime.stop());
      });
      return runtime;
    });

/// 来电与通用 tap 路由共享同一 Firebase 初始化 owner，不重复探测配置状态。
final firebaseIncomingCallRuntimeProvider =
    Provider<FirebaseIncomingCallRuntime>((ref) {
      final runtime = FirebaseIncomingCallRuntime(
        pushEndpointGateway: ref.watch(pushEndpointGatewayProvider),
        messagingRuntime: ref.watch(firebasePushMessagingRuntimeProvider),
      );
      ref.onDispose(() {
        unawaited(runtime.stop());
      });
      return runtime;
    });

/// 非 Android 平台能力由同一 runtime owner 返回 unsupported；消费方只见中性 intent。
final pushTapIntentSourceProvider = Provider<PushTapIntentSource?>((ref) {
  return ref.watch(firebasePushMessagingRuntimeProvider);
});
