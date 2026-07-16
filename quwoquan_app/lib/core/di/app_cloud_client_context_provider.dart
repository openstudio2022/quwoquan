import 'dart:ui' show PlatformDispatcher;

import 'package:quwoquan_app/assistant/observability/logging/app_trace_context_store.dart';
import 'package:quwoquan_app/cloud/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/core/platform/platform_target.dart';

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
      locale: PlatformDispatcher.instance.locale.toLanguageTag(),
    );
  }
}
