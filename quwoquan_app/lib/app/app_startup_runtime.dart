import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/analytics/analytics.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_exception_telemetry_service.dart';
import 'package:quwoquan_app/core/emoji/emoji_analytics.dart';
import 'package:quwoquan_app/core/emoji/emoji_repository.dart';
import 'package:quwoquan_app/core/platform/startup_native_bridge.dart';
import 'package:shared_preferences/shared_preferences.dart';

typedef ProviderReader = Object? Function(dynamic provider);

/// 记录冷启动关键节点，并在首帧后异步预热非关键链路。
final class AppStartupRuntime {
  AppStartupRuntime._();

  static final AppStartupRuntime instance = AppStartupRuntime._();
  final Stopwatch _stopwatch = Stopwatch();

  bool _bootstrapStarted = false;
  bool _postFirstFrameWarmupScheduled = false;
  bool _homeReadyReported = false;

  int? _runAppMs;
  int? _firstFrameMs;
  int? _welcomeShownMs;
  int? _welcomeWindowInitMs;
  int? _welcomeCompletedMs;
  int? _homeFeedWarmMs;
  int? _homeReadyMs;
  int? _androidActivityOnCreateMs;
  int? _androidFlutterEngineConfiguredMs;

  static const StartupTimingsNativeBridge _nativeTimingsBridge =
      MethodChannelStartupTimingsNativeBridge();

  void markBootstrapStarted() {
    if (_bootstrapStarted) {
      return;
    }
    _bootstrapStarted = true;
    _stopwatch.start();
  }

  void markRunAppCalled() {
    _runAppMs ??= _elapsedMs;
  }

  void markFirstFramePainted() {
    _firstFrameMs ??= _elapsedMs;
  }

  void markWelcomeShown() {
    _welcomeShownMs ??= _elapsedMs;
  }

  Future<void> hydrateNativeProcessSegments() async {
    if (_androidFlutterEngineConfiguredMs != null) {
      return;
    }
    final segments = await _nativeTimingsBridge.readProcessSegments();
    if (segments == null) {
      return;
    }
    _androidActivityOnCreateMs = segments.androidActivityOnCreateMs;
    _androidFlutterEngineConfiguredMs =
        segments.androidFlutterEngineConfiguredMs;
  }

  void markWelcomeWindowInitStarted() {
    _welcomeWindowInitMs ??= _elapsedMs;
  }

  void markWelcomeCompleted() {
    _welcomeCompletedMs ??= _elapsedMs;
  }

  void markHomeFeedWarm() {
    _homeFeedWarmMs ??= _elapsedMs;
  }

  void schedulePostFirstFrameWarmup(ProviderReader read) {
    if (_postFirstFrameWarmupScheduled) {
      return;
    }
    _postFirstFrameWarmupScheduled = true;
    unawaited(_warmupAfterFirstFrame(read));
  }

  void scheduleHomeReadyReport(ProviderReader read) {
    if (_homeReadyReported) {
      return;
    }
    _homeReadyReported = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _homeReadyMs ??= _elapsedMs;
      final analytics = read(analyticsProvider) as AnalyticsService;
      unawaited(
        analytics.trackEvent(
          AnalyticsEvent(
            eventType: 'app_startup',
            eventName: 'home_ready',
            properties: _snapshotProperties(phase: 'home_ready'),
          ),
        ),
      );
    });
  }

  void recordStartupPhase(
    ProviderReader read, {
    required String phase,
    String eventName = 'app_startup_phase',
    Map<String, dynamic> properties = const <String, dynamic>{},
  }) {
    try {
      final analytics = read(analyticsProvider) as AnalyticsService;
      unawaited(
        analytics.trackEvent(
          AnalyticsEvent(
            eventType: 'app_startup',
            eventName: eventName,
            properties: <String, dynamic>{
              ..._snapshotProperties(phase: phase),
              ...properties,
            },
          ),
        ),
      );
    } catch (_) {
      // 启动观测只做 best effort，不能影响进入 App。
    }
  }

  Map<String, dynamic> snapshotProperties({required String phase}) {
    return _snapshotProperties(phase: phase);
  }

  Future<void> _warmupAfterFirstFrame(ProviderReader read) async {
    unawaited(
      AppExceptionTelemetryService.instance.flushPending().catchError((_) {}),
    );
    await _warmupAnalytics(read);
  }

  Future<void> _warmupAnalytics(ProviderReader read) async {
    try {
      final analytics = read(analyticsProvider) as AnalyticsService;
      final config = read(analyticsConfigProvider) as AnalyticsConfig;
      await analytics.initialize(config);
      unawaited(
        analytics.trackEvent(
          AnalyticsEvent(
            eventType: 'app_startup',
            eventName: 'app_start',
            properties: _snapshotProperties(phase: 'first_frame'),
          ),
        ),
      );

      final prefs = await SharedPreferences.getInstance();
      final emojiRepo = EmojiRepository(prefs);
      unawaited(EmojiAnalytics.tryReportDaily(emojiRepo, analytics));
    } catch (_) {
      // 冷启动统计链路必须 best effort，不能影响首屏。
    }
  }

  Map<String, dynamic> _snapshotProperties({required String phase}) {
    return <String, dynamic>{
      'phase': phase,
      if (_runAppMs != null) 'runAppMs': _runAppMs,
      if (_firstFrameMs != null) 'firstFrameMs': _firstFrameMs,
      if (_welcomeShownMs != null) 'welcomeShownMs': _welcomeShownMs,
      if (_welcomeWindowInitMs != null)
        'welcomeWindowInitMs': _welcomeWindowInitMs,
      if (_welcomeCompletedMs != null)
        'welcomeCompletedMs': _welcomeCompletedMs,
      if (_androidActivityOnCreateMs != null)
        'androidActivityOnCreateMs': _androidActivityOnCreateMs,
      if (_androidFlutterEngineConfiguredMs != null)
        'androidFlutterEngineConfiguredMs': _androidFlutterEngineConfiguredMs,
      if (_homeFeedWarmMs != null) 'homeFeedWarmMs': _homeFeedWarmMs,
      if (_homeReadyMs != null) 'homeReadyMs': _homeReadyMs,
      'elapsedMs': _elapsedMs,
    };
  }

  int get _elapsedMs {
    if (!_stopwatch.isRunning) {
      return 0;
    }
    return _stopwatch.elapsedMilliseconds;
  }
}
