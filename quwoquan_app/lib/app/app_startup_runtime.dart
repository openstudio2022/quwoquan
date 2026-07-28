import 'dart:async';
import 'dart:convert';
import 'dart:developer' as developer;

import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/analytics/analytics.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_exception_telemetry_service.dart';
import 'package:quwoquan_app/app/startup/startup_telemetry.dart';
import 'package:quwoquan_app/app/startup/startup_telemetry_support.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_reporter.dart';
import 'package:quwoquan_app/core/emoji/emoji_analytics.dart';
import 'package:quwoquan_app/core/emoji/emoji_repository.dart';
import 'package:quwoquan_app/core/platform/startup_native_bridge.dart';
import 'package:quwoquan_app/core/platform/startup_process_clock.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';
import 'package:shared_preferences/shared_preferences.dart';

typedef ProviderReader = Object? Function(dynamic provider);

final class _NativeTimingHydrationCancelled implements Exception {
  const _NativeTimingHydrationCancelled();
}

/// 记录冷启动关键节点，并在首帧后异步预热非关键链路。
final class AppStartupRuntime {
  AppStartupRuntime._();

  static final AppStartupRuntime instance = AppStartupRuntime._();
  final Stopwatch _stopwatch = Stopwatch();

  bool _bootstrapStarted = false;
  bool _postFirstFrameWarmupScheduled = false;
  bool _homeReadyReported = false;
  bool _terminalRecorded = false;
  bool _welcomeOverlayRemoved = false;
  bool _homeFeedContentPainted = false;
  bool _nativeSegmentsHydrated = false;
  bool _productStartupReported = false;
  String _startupAttemptId = '';
  String _startupFailureCode = '';
  AppTelemetryRecorder? _productTelemetry;
  Future<void>? _nativeSegmentsHydration;

  int? _runAppMs;
  int? _firstFrameMs;
  int? _welcomeShownMs;
  int? _welcomeWindowInitMs;
  int? _welcomeCompletedMs;
  int? _shellFirstPaintMs;
  int? _homeFeedWarmMs;
  int? _homeReadyMs;
  int? _androidActivityOnCreateMs;
  int? _androidFlutterEngineConfiguredMs;
  int? _nativeElapsedSinceProcessStartMs;
  int? _dartElapsedAtNativeHydrationMs;
  int? _deadlineElapsedAtBootstrapMs;
  int _dartElapsedAtDeadlineArmMs = 0;
  String _deadlineOrigin = 'fallbackDart';

  static StartupTimingsNativeBridge _nativeTimingsBridge =
      MethodChannelStartupTimingsNativeBridge();

  @visibleForTesting
  static void overrideNativeTimingsBridgeForTesting(
    StartupTimingsNativeBridge bridge,
  ) {
    _nativeTimingsBridge = bridge;
  }

  @visibleForTesting
  static void resetNativeTimingsBridgeForTesting() {
    _nativeTimingsBridge = MethodChannelStartupTimingsNativeBridge();
  }

  @visibleForTesting
  void resetForTesting() {
    _stopwatch
      ..stop()
      ..reset();
    _bootstrapStarted = false;
    _postFirstFrameWarmupScheduled = false;
    _homeReadyReported = false;
    _nativeSegmentsHydrated = false;
    _nativeSegmentsHydration = null;
    _productStartupReported = false;
    _startupAttemptId = '';
    _startupFailureCode = '';
    _productTelemetry = null;
    _runAppMs = null;
    _firstFrameMs = null;
    _welcomeShownMs = null;
    _welcomeWindowInitMs = null;
    _welcomeCompletedMs = null;
    _shellFirstPaintMs = null;
    _homeFeedWarmMs = null;
    _homeReadyMs = null;
    _terminalRecorded = false;
    _welcomeOverlayRemoved = false;
    _homeFeedContentPainted = false;
    _androidActivityOnCreateMs = null;
    _androidFlutterEngineConfiguredMs = null;
    _nativeElapsedSinceProcessStartMs = null;
    _dartElapsedAtNativeHydrationMs = null;
    _deadlineElapsedAtBootstrapMs = null;
    _dartElapsedAtDeadlineArmMs = 0;
    _deadlineOrigin = 'fallbackDart';
  }

  void markBootstrapStarted() {
    if (_bootstrapStarted) {
      return;
    }
    _bootstrapStarted = true;
    _startupAttemptId = StartupTelemetrySupport.randomUrlSafeToken(24);
    _stopwatch.start();
    _recordPlatformStartupEvent(
      eventName: 'startup_attempt_started',
      properties: _snapshotProperties(phase: 'startup_attempt_started'),
    );
    final platformElapsed = readPlatformStartupElapsedMs();
    _dartElapsedAtDeadlineArmMs = _elapsedMs;
    if (platformElapsed != null) {
      _nativeElapsedSinceProcessStartMs = platformElapsed;
      _dartElapsedAtNativeHydrationMs = _elapsedMs;
      _deadlineElapsedAtBootstrapMs = platformElapsed;
      _deadlineOrigin = readPlatformStartupDeadlineOrigin() ?? 'fallbackDart';
    }
    _recordCanonicalPhase(
      StartupTelemetryPhase.nativePreFlutter,
      elapsedMs: _nativeElapsedSinceProcessStartMs ?? 0,
      outcome: 'observed',
    );
    _recordCanonicalPhase(
      StartupTelemetryPhase.dartBootstrap,
      outcome: 'started',
    );
  }

  void markRunAppCalled() {
    _runAppMs ??= _elapsedMs;
  }

  void markConfigurationValidated() {
    _recordCanonicalPhase(
      StartupTelemetryPhase.configurationValidation,
      outcome: 'validated',
    );
  }

  /// Bootstrap 尚未装配 Provider/Analytics 时也必须留下脱敏终态。
  void recordBootstrapFailure(RuntimeFailureBase failure) {
    final properties = <String, Object?>{
      ..._snapshotProperties(phase: 'bootstrap_failure'),
      'failureCode': failure.code,
      'failureKind': failure.kind.name,
      'failureOrigin': failure.origin.name,
      'recoveryAction': failure.recovery.action,
    };
    try {
      _recordCanonicalPhase(
        StartupTelemetryPhase.configurationValidation,
        outcome: failure.code.contains('startup_configuration')
            ? 'failed'
            : 'skipped',
        failureCode: failure.code,
        failureSource: 'bootstrap',
      );
      _recordCanonicalPhase(
        StartupTelemetryPhase.recovery,
        outcome: 'bootstrap_failure',
        recoverySurface: 'flutter_recovery',
        failureCode: failure.code,
        failureSource: 'bootstrap',
      );
      _recordTerminal(
        outcome: 'recovery',
        recoverySurface: 'flutter_recovery',
        failureCode: failure.code,
        failureSource: 'bootstrap',
      );
      StartupTelemetryRuntime.instance.flush();
      developer.log(
        'startup_bootstrap_failure code=${failure.code}',
        name: 'QWQStartup',
      );
      recordPlatformStartupEvent(
        jsonEncode(<String, Object?>{
          'eventName': 'startup_bootstrap_failure',
          ...properties,
        }),
      );
    } catch (_) {
      // Bootstrap 失败记录绝不能阻断恢复根。
    }
  }

  void markFirstFramePainted() {
    if (_firstFrameMs != null) {
      return;
    }
    _firstFrameMs = _elapsedMs;
    _recordCanonicalPhase(
      StartupTelemetryPhase.flutterFirstFrame,
      outcome: 'painted',
    );
    try {
      recordPlatformStartupEvent(
        jsonEncode(<String, Object?>{
          'eventName': 'flutter_first_frame',
          ..._snapshotProperties(phase: 'flutter_first_frame'),
        }),
      );
    } catch (_) {
      // 原生 watchdog 确认仅为 best effort，不能反向影响首帧。
    }
    // Durable journal / native journal import 只能在 Flutter 已实际绘制后启动。
    StartupTelemetryRuntime.instance.activateAfterFirstFrame();
  }

  void markWelcomeShown() {
    _welcomeShownMs ??= _elapsedMs;
  }

  /// 原生 timing bridge 不属于进入 Shell 的前置条件。
  ///
  /// 同时到来的调用共享一条有上限任务；超时、PlatformException 或任意未知错误都会
  /// 清除 in-flight 标记，下一次安全时机可以重试，绝不把永久 pending 固化为已水合。
  Future<void> hydrateNativeProcessSegments({
    Duration budget = const Duration(seconds: 2),
    Future<void>? cancellationSignal,
  }) {
    if (_nativeSegmentsHydrated) {
      return Future<void>.value();
    }
    final active = _nativeSegmentsHydration;
    if (active != null) {
      return active;
    }
    late final Future<void> task;
    task =
        _readNativeProcessSegments(
          budget,
          cancellationSignal: cancellationSignal,
        ).whenComplete(() {
          if (identical(_nativeSegmentsHydration, task)) {
            _nativeSegmentsHydration = null;
          }
        });
    _nativeSegmentsHydration = task;
    return task;
  }

  Future<void> _readNativeProcessSegments(
    Duration budget, {
    Future<void>? cancellationSignal,
  }) async {
    try {
      final segments = await _readNativeSegmentsWithBudget(
        budget,
        cancellationSignal: cancellationSignal,
      );
      if (segments != null) {
        final deadlineBeforeHydration =
            deadlineElapsedSinceProcessStart.inMilliseconds;
        final dartElapsedAtHydration = _elapsedMs;
        _androidActivityOnCreateMs = segments.androidActivityOnCreateMs;
        _androidFlutterEngineConfiguredMs =
            segments.androidFlutterEngineConfiguredMs;
        _nativeElapsedSinceProcessStartMs = segments.elapsedSinceProcessStartMs;
        _dartElapsedAtNativeHydrationMs = dartElapsedAtHydration;
        final nativeAttemptId = segments.startupAttemptId?.trim() ?? '';
        if (StartupTelemetrySupport.isValidAttemptId(nativeAttemptId)) {
          _startupAttemptId = nativeAttemptId;
        }
        final nativeDeadline = segments.elapsedSinceProcessStartMs;
        if (nativeDeadline != null &&
            nativeDeadline > deadlineBeforeHydration) {
          // Native process time can only consume more of the existing budget.
          // A delayed/stale bridge response must never move the absolute
          // deadline backwards and grant a second startup window.
          _deadlineElapsedAtBootstrapMs = nativeDeadline;
          _dartElapsedAtDeadlineArmMs = dartElapsedAtHydration;
          final nativeOrigin = segments.deadlineOrigin ?? '';
          _deadlineOrigin = nativeOrigin.isEmpty
              ? 'nativeProcess'
              : nativeOrigin;
        }
      }
      _nativeSegmentsHydrated = true;
    } catch (_) {
      _nativeSegmentsHydrated = false;
      rethrow;
    }
  }

  Future<NativeStartupProcessSegments?> _readNativeSegmentsWithBudget(
    Duration budget, {
    Future<void>? cancellationSignal,
  }) {
    final result = Completer<NativeStartupProcessSegments?>();
    late final Timer timer;
    void completeValue(NativeStartupProcessSegments? segments) {
      if (result.isCompleted) {
        return;
      }
      timer.cancel();
      result.complete(segments);
    }

    void completeFailure(Object error, [StackTrace? stack]) {
      if (result.isCompleted) {
        return;
      }
      timer.cancel();
      if (stack == null) {
        result.completeError(error);
      } else {
        result.completeError(error, stack);
      }
    }

    timer = Timer(budget, () {
      if (!result.isCompleted) {
        result.completeError(
          TimeoutException('native startup timing bridge timed out', budget),
        );
      }
    });
    _nativeTimingsBridge.readProcessSegments().then(
      (segments) {
        completeValue(segments);
      },
      onError: (Object error, StackTrace stack) {
        completeFailure(error, stack);
      },
    );
    cancellationSignal?.then((_) {
      completeFailure(const _NativeTimingHydrationCancelled());
    });
    return result.future;
  }

  Duration get elapsedSinceProcessStart {
    final nativeElapsed = _nativeElapsedSinceProcessStartMs;
    final dartHydrationElapsed = _dartElapsedAtNativeHydrationMs;
    if (nativeElapsed != null && dartHydrationElapsed != null) {
      final sinceHydration = (_elapsedMs - dartHydrationElapsed).clamp(
        0,
        1 << 30,
      );
      return Duration(milliseconds: nativeElapsed + sinceHydration);
    }
    return Duration(milliseconds: _elapsedMs);
  }

  /// 单次启动的 deadline 只能被 native process clock 向前收紧。
  ///
  /// 异步 bridge 返回较小或陈旧的时间时继续使用已经 arm 的 Dart 边界，绝不延长预算。
  Duration get deadlineElapsedSinceProcessStart {
    final nativeAtBootstrap = _deadlineElapsedAtBootstrapMs;
    final elapsedSinceArm = (_elapsedMs - _dartElapsedAtDeadlineArmMs).clamp(
      0,
      1 << 30,
    );
    if (nativeAtBootstrap != null) {
      return Duration(milliseconds: nativeAtBootstrap + elapsedSinceArm);
    }
    return Duration(milliseconds: elapsedSinceArm);
  }

  String get deadlineOrigin => _deadlineOrigin;

  String get startupAttemptId => _startupAttemptId;

  void markWelcomeWindowInitStarted() {
    _welcomeWindowInitMs ??= _elapsedMs;
  }

  void markWelcomeCompleted() {
    _welcomeCompletedMs ??= _elapsedMs;
  }

  void markShellFirstPainted() {
    _shellFirstPaintMs ??= elapsedSinceProcessStart.inMilliseconds;
    // 先通知原生/Web 取消 6 秒安全终态看门狗，再做 journal flush；
    // MethodChannel 排队晚于 watchdog 会误弹 nativeRecovery。
    _recordPlatformSafeTerminal('router_shell');
    _recordCanonicalPhase(
      StartupTelemetryPhase.shellFirstPaint,
      outcome: 'painted',
    );
    _recordTerminal(outcome: 'success');
    StartupTelemetryRuntime.instance.markSafeTerminal();
  }

  /// Flutter 首帧可能仍是欢迎层；原生/Web watchdog 必须等到实际可操作的恢复面
  /// 绘制后，才能取消进程级 6 秒安全终态看门狗。
  void markSafeRecoverySurfacePainted() {
    _recordPlatformSafeTerminal('safe_recovery');
    StartupTelemetryRuntime.instance.markSafeTerminal();
  }

  void markBootstrapRecoverySurfacePainted() {
    _recordPlatformSafeTerminal('flutter_recovery');
    StartupTelemetryRuntime.instance.markSafeTerminal();
  }

  void markHomeFeedWarm() {
    _homeFeedWarmMs ??= _elapsedMs;
  }

  /// 只能在首页初始内容真实可交互时调用，不能由欢迎页或 Router 回调伪造。
  void markHomeFeedFirstUsable() {
    if (_homeReadyMs != null) {
      return;
    }
    _homeReadyMs = elapsedSinceProcessStart.inMilliseconds;
    _recordCanonicalPhase(
      StartupTelemetryPhase.homeFeedFirstUsable,
      outcome: 'usable',
    );
    StartupTelemetryRuntime.instance.flush();
    _reportProductStartupWhenReady();
  }

  void bindProductTelemetry(AppTelemetryRecorder recorder) {
    _productTelemetry = recorder;
    _reportProductStartupWhenReady();
  }

  /// 首页内容和欢迎遮罩是两个独立时钟：任一方单独完成都不能冒充“用户已可见且
  /// 可操作”。两者都完成后才记录 home_feed_first_usable。
  void markHomeFeedContentPainted() {
    _homeFeedContentPainted = true;
    _markHomeFeedUsableWhenVisible();
  }

  void markWelcomeOverlayRemoved() {
    _welcomeOverlayRemoved = true;
    _markHomeFeedUsableWhenVisible();
  }

  void _markHomeFeedUsableWhenVisible() {
    if (!_homeFeedContentPainted || !_welcomeOverlayRemoved) {
      return;
    }
    markHomeFeedFirstUsable();
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
      markHomeFeedFirstUsable();
    });
  }

  void recordStartupPhase(
    ProviderReader read, {
    required String phase,
    String eventName = 'app_startup_phase',
    Map<String, dynamic> properties = const <String, dynamic>{},
  }) {
    final eventProperties = <String, dynamic>{
      ..._snapshotProperties(phase: phase),
      ...properties,
    };
    try {
      developer.log(
        <String>[
          eventName,
          for (final entry in eventProperties.entries)
            '${entry.key}=${entry.value}',
        ].join(' '),
        name: 'QWQStartup',
      );
      recordPlatformStartupEvent(
        jsonEncode(<String, dynamic>{
          'eventName': eventName,
          ...eventProperties,
        }),
      );
      _recordCanonicalPhaseFromReportedPhase(
        phase: phase,
        outcome: properties['result']?.toString() ?? eventName,
        properties: properties,
      );
    } catch (_) {
      // 启动观测只做 best effort，不能影响进入 App。
    }
  }

  Map<String, dynamic> snapshotProperties({required String phase}) {
    return _snapshotProperties(phase: phase);
  }

  void _recordCanonicalPhaseFromReportedPhase({
    required String phase,
    required String outcome,
    required Map<String, dynamic> properties,
  }) {
    final canonical = switch (phase) {
      'router_preload_ready' => StartupTelemetryPhase.routerReady,
      'router_preload_failed' ||
      'router_loading_failed' => StartupTelemetryPhase.routerFailure,
      'router_loading' => StartupTelemetryPhase.routerPreload,
      'main_shell_first_paint' => StartupTelemetryPhase.shellFirstPaint,
      'safe_recovery_shown' => StartupTelemetryPhase.recovery,
      _ => null,
    };
    if (canonical == null) {
      return;
    }
    _recordCanonicalPhase(
      canonical,
      outcome: canonical == StartupTelemetryPhase.recovery ? 'shown' : outcome,
      recoverySurface: canonical == StartupTelemetryPhase.recovery
          ? 'safe_recovery'
          : '',
      failureCode: properties['failureCode']?.toString() ?? '',
      failureSource: canonical == StartupTelemetryPhase.routerFailure
          ? properties['failureSource']?.toString() ?? 'router'
          : properties['failureSource']?.toString() ?? '',
      deadlineOrigin: properties['deadlineOrigin']?.toString() ?? '',
    );
    if (canonical == StartupTelemetryPhase.recovery) {
      _recordTerminal(
        outcome: 'recovery',
        recoverySurface: 'safe_recovery',
        failureCode: properties['failureCode']?.toString() ?? '',
        failureSource: properties['failureSource']?.toString() ?? 'router',
      );
      StartupTelemetryRuntime.instance.flush();
    }
  }

  void _recordCanonicalPhase(
    StartupTelemetryPhase phase, {
    required String outcome,
    int? elapsedMs,
    String recoverySurface = '',
    String failureCode = '',
    String failureSource = '',
    String deadlineOrigin = '',
  }) {
    if (failureCode.trim().isNotEmpty) {
      _startupFailureCode = failureCode.trim();
    }
    StartupTelemetryRuntime.instance.record(
      phase: phase,
      elapsedMs: elapsedMs ?? elapsedSinceProcessStart.inMilliseconds,
      outcome: outcome,
      recoverySurface: recoverySurface,
      failureCode: failureCode,
      failureSource: failureSource,
      deadlineOrigin: deadlineOrigin.isEmpty ? _deadlineOrigin : deadlineOrigin,
    );
  }

  void _reportProductStartupWhenReady() {
    final recorder = _productTelemetry;
    final firstFrameMs = _firstFrameMs;
    final shellMs = _shellFirstPaintMs;
    final contentMs = _homeReadyMs;
    if (_productStartupReported ||
        recorder == null ||
        firstFrameMs == null ||
        shellMs == null ||
        contentMs == null) {
      return;
    }
    _productStartupReported = true;
    final hasError = _startupFailureCode.isNotEmpty;
    unawaited(
      recorder.record(
        AppTelemetryPayload.appStartup(
          tClickToFirstFrameMs: firstFrameMs.clamp(0, contentMs).toInt(),
          tFirstFrameToShellMs: (shellMs - firstFrameMs)
              .clamp(0, contentMs)
              .toInt(),
          tShellToContentMs: (contentMs - shellMs).clamp(0, contentMs).toInt(),
          tClickToContentMs: contentMs,
          hasError: hasError,
        ),
      ),
    );
    if (hasError) {
      unawaited(
        recorder.record(
          AppTelemetryPayload.runtimeException(
            errorCode: _startupFailureCode,
            operationId: 'app.startup',
          ),
        ),
      );
    }
  }

  void _recordPlatformSafeTerminal(String surface) {
    _recordPlatformStartupEvent(
      eventName: 'startup_safe_terminal',
      properties: <String, Object?>{
        'surface': surface,
        ..._snapshotProperties(phase: 'startup_safe_terminal'),
      },
    );
  }

  void _recordPlatformStartupEvent({
    required String eventName,
    required Map<String, dynamic> properties,
  }) {
    try {
      recordPlatformStartupEvent(
        jsonEncode(<String, Object?>{'eventName': eventName, ...properties}),
      );
    } catch (_) {
      // 原生启动证据仅用于诊断，不得反向击穿已经可见的 Flutter UI。
    }
  }

  /// 每次启动必须留下一个可用于漏斗收口的终态；Shell 首帧已表示用户拥有可操作表面，
  /// 首页内容可用则另记 [StartupTelemetryPhase.homeFeedFirstUsable]，不能把后者伪装成
  /// 唯一的启动终态。
  void _recordTerminal({
    required String outcome,
    String recoverySurface = '',
    String failureCode = '',
    String failureSource = '',
  }) {
    if (_terminalRecorded) {
      return;
    }
    _terminalRecorded = true;
    _recordCanonicalPhase(
      StartupTelemetryPhase.terminal,
      outcome: outcome,
      recoverySurface: recoverySurface,
      failureCode: failureCode,
      failureSource: failureSource,
    );
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

      final prefs = await SharedPreferences.getInstance();
      final emojiRepo = EmojiRepository(prefs);
      unawaited(
        EmojiAnalytics.tryReportDaily(emojiRepo, analytics).catchError((_) {}),
      );
    } catch (_) {
      // 冷启动统计链路必须 best effort，不能影响首屏。
    }
  }

  Map<String, dynamic> _snapshotProperties({required String phase}) {
    final runtimeSummary = CloudRuntimeConfig.runtimeDefineSummary;
    final missingDefineKeys = runtimeSummary['missingKeys'] ?? '';
    return <String, dynamic>{
      'phase': phase,
      if (_startupAttemptId.isNotEmpty) 'attemptId': _startupAttemptId,
      'runtimeEnv': runtimeSummary['runtimeEnv'],
      'launchMode': runtimeSummary['launchMode'],
      'configurationState': runtimeSummary['configurationState'],
      if (missingDefineKeys.isNotEmpty) 'missingDefineKeys': missingDefineKeys,
      if (_runAppMs != null) 'runAppMs': _runAppMs,
      if (_firstFrameMs != null) 'firstFrameMs': _firstFrameMs,
      if (_welcomeShownMs != null) 'welcomeShownMs': _welcomeShownMs,
      if (_welcomeWindowInitMs != null)
        'welcomeWindowInitMs': _welcomeWindowInitMs,
      if (_welcomeCompletedMs != null)
        'welcomeCompletedMs': _welcomeCompletedMs,
      if (_shellFirstPaintMs != null) 'shellFirstPaintMs': _shellFirstPaintMs,
      if (_androidActivityOnCreateMs != null)
        'androidActivityOnCreateMs': _androidActivityOnCreateMs,
      if (_androidFlutterEngineConfiguredMs != null)
        'androidFlutterEngineConfiguredMs': _androidFlutterEngineConfiguredMs,
      'deadlineOrigin': _deadlineOrigin,
      'elapsedSinceProcessStartMs': elapsedSinceProcessStart.inMilliseconds,
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
