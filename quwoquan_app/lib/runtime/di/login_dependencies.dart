import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/config/app_content_source.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/errors/content_capability_unavailable.dart';
import 'package:quwoquan_app/runtime/auth/account_restriction_support.dart';
import 'package:quwoquan_app/runtime/di/ops_event_dependencies.dart';
import 'package:quwoquan_app/runtime/platform/one_tap_login_native_bridge.dart';
import 'package:quwoquan_app/runtime/platform/otp_autofill_gateway.dart';
import 'package:quwoquan_app/runtime/observability/trackers/journey_event_tracker.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_reporter.dart';
import 'package:quwoquan_app/service/user_service/account/authentication_challenge/adapters/secure_pending_otp_attempt_store.dart';
import 'package:quwoquan_app/service/user_service/account/authentication_challenge/application/public/pending_otp_attempt_store.dart';

/// source 只在组合根选择；登录页面消费 typed 能力失败，不探测环境。
final loginCapabilityFailureProvider = Provider<CloudException?>((ref) {
  return CloudRuntimeConfig.isHydrated &&
          CloudRuntimeConfig.contentSource == AppContentSource.bundledSnapshot
      ? contentCapabilityUnavailable('account_authentication')
      : null;
});

final oneTapLoginClientProvider = Provider<OneTapLoginClient>((ref) {
  return MethodChannelOneTapLoginClient();
});

final otpAutofillGatewayProvider = Provider<OtpAutofillGateway>((ref) {
  return createOtpAutofillGateway();
});

final accountRestrictionSupportLauncherProvider =
    Provider<AccountRestrictionSupportLauncher>((ref) {
      return PublicWebAccountRestrictionSupportLauncher.runtime();
    });

final pendingOtpAttemptStoreProvider = Provider<PendingOtpAttemptStore>((ref) {
  return const SecurePendingOtpAttemptStore();
});

/// 登录页专用的轻量漏斗组合入口。
///
/// 不依赖全应用 Provider 聚合图；事件 schema、脱敏与上报实现仍复用统一
/// [JourneyEventTracker] / [AppTelemetryRecorder]。
final loginJourneyEventTrackerProvider = Provider<JourneyEventTracker>((ref) {
  return JourneyEventTracker(
    telemetryReporter: ref.watch(appTelemetryReporterProvider),
  );
});
