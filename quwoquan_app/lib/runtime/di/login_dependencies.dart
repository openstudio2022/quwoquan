import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/config/app_content_source.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/runtime/config/rehearsal_storage_namespace.dart';
import 'package:quwoquan_app/runtime/config/runtime_package_resolver.dart';
import 'package:quwoquan_app/service/user_service/account/authentication_challenge/application/public/synthetic_challenge_port.dart';
import 'package:quwoquan_app/service/user_service/account/account_session/application/public/synthetic_session_port.dart';
import 'package:quwoquan_cloud_contracts/generated/values/user/account/authentication_challenge.values.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/errors/content_capability_unavailable.dart';
import 'package:quwoquan_app/runtime/auth/account_restriction_support.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart'
    show rehearsalStorageObserverProvider;
import 'package:quwoquan_app/runtime/di/ops_event_dependencies.dart';
import 'package:quwoquan_app/runtime/platform/one_tap_login_native_bridge.dart';
import 'package:quwoquan_app/runtime/platform/otp_autofill_gateway.dart';
import 'package:quwoquan_app/runtime/observability/trackers/journey_event_tracker.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_reporter.dart';
import 'package:quwoquan_app/service/user_service/account/authentication_challenge/adapters/secure_pending_otp_attempt_store.dart';
import 'package:quwoquan_app/service/user_service/account/authentication_challenge/application/public/pending_otp_attempt_store.dart';

/// 启动scope以override注入；不安装全局hook，不持有Alpha实现或runtime秘密。
final class SyntheticLoginCapability {
  SyntheticLoginCapability({
    required VerifiedRehearsalSpace space,
    required this.currentSpace,
    required this.challengePort,
    required this.sessionPort,
    required this.createIdentityLabel,
    required this.createRequestKey,
  }) : _namespace = RehearsalStorageNamespace(space) {
    requireCurrent();
  }

  final RehearsalStorageNamespace _namespace;
  final VerifiedRehearsalSpace? Function() currentSpace;
  final SyntheticChallengePort challengePort;
  final SyntheticSessionPort sessionPort;
  final SyntheticIdentityLabel Function() createIdentityLabel;
  final String Function() createRequestKey;
  void requireCurrent() => _namespace.requireCurrent(currentSpace());
}

final syntheticLoginCapabilityProvider = Provider<SyntheticLoginCapability?>(
  (ref) => null,
);

/// source 只在组合根选择；登录页面消费 typed 能力失败，不探测环境。
CloudException? Function()? _loginCapabilityFailureOverride;

void configureLoginCapabilityFailure(CloudException? Function()? override) {
  _loginCapabilityFailureOverride = override;
}

final loginCapabilityFailureProvider = Provider<CloudException?>((ref) {
  final synthetic = ref.watch(syntheticLoginCapabilityProvider);
  if (synthetic != null) {
    synthetic.requireCurrent();
    return null;
  }
  if (_loginCapabilityFailureOverride != null) {
    return _loginCapabilityFailureOverride!();
  }
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
  final space = CloudRuntimeConfig.rehearsalSpace;
  if (space?.isIsolated == true) {
    final store = SecurePendingOtpAttemptStore.isolated(
      namespace: RehearsalStorageNamespace(space!),
      currentSpace: () => CloudRuntimeConfig.rehearsalSpace,
      isActive: () => ref.mounted,
      observer: ref.read(rehearsalStorageObserverProvider),
    );
    ref.onDispose(store.dispose);
    return store;
  }
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
