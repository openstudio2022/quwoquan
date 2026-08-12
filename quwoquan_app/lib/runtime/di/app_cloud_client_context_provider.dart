import 'dart:ui' show PlatformDispatcher;

import 'package:quwoquan_app/runtime/observability/app_trace_context_store.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/platform/platform_target.dart';

final class AppCloudClientContextProvider
    implements CloudClientContextProvider {
  const AppCloudClientContextProvider();

  @override
  CloudClientContextSnapshot snapshot() {
    return CloudClientContextSnapshot(
      sessionId: AppTraceContextStore.instance.sessionId,
      deviceActorId: AppTraceContextStore.instance.deviceActorId,
      platform: platformWireName(currentAppPlatform),
      appVersion: const String.fromEnvironment(
        'APP_VERSION',
        defaultValue: 'dev',
      ),
      appBuild: const String.fromEnvironment(
        'APP_BUILD_NUMBER',
        defaultValue: '0',
      ),
      locale: PlatformDispatcher.instance.locale.toLanguageTag(),
      regionCode: AppTraceContextStore.instance.grayRegionCode,
      carrier: AppTraceContextStore.instance.grayCarrier,
    );
  }
}
