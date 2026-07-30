import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/auth/account_restriction_support.dart';
import 'package:quwoquan_app/core/di/ops_event_dependencies.dart';
import 'package:quwoquan_app/core/platform/one_tap_login_native_bridge.dart';
import 'package:quwoquan_app/core/trackers/journey_event_tracker.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_reporter.dart';

final oneTapLoginClientProvider = Provider<OneTapLoginClient>((ref) {
  return MethodChannelOneTapLoginClient();
});

final accountRestrictionSupportLauncherProvider =
    Provider<AccountRestrictionSupportLauncher>((ref) {
      return PublicWebAccountRestrictionSupportLauncher.runtime();
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
