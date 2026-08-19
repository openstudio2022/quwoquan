import 'dart:async';
import 'dart:convert';
import 'dart:developer' as developer;

import 'package:flutter/foundation.dart'
    show kProfileMode, kReleaseMode;
import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/runtime/observability/analytics.dart';
import 'package:quwoquan_app/runtime/observability/app_exception_telemetry_service.dart';
import 'package:quwoquan_app/runtime/observability/startup/startup_telemetry.dart';
import 'package:quwoquan_app/runtime/observability/startup/startup_telemetry_support.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/runtime/observability/generated/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_reporter.dart';
import 'package:quwoquan_app/design_system/emoji/emoji_analytics.dart';
import 'package:quwoquan_app/design_system/emoji/emoji_repository.dart';
import 'package:quwoquan_app/runtime/platform/startup_native_bridge.dart';
import 'package:quwoquan_app/runtime/platform/startup_process_clock.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';
import 'package:shared_preferences/shared_preferences.dart';

typedef ProviderReader = Object? Function(dynamic provider);

final class _NativeTimingHydrationCancelled implements Exception {
  const _NativeTimingHydrationCancelled();
}

/// 启动链路单个观测点的脱敏快照（typed 视图）。
///
/// 序列化为原生 watchdog / dev log 的 JSON payload 时保持既往稀疏键语义：
/// 未发生的里程碑不写键，见 [toJson]。
final class StartupPhaseSnapshot {
  const StartupPhaseSnapshot({
    required this.phase,
    required this.attemptId,
    required this.runtimeEnv,
    required this.launchMode,
    required this.configurationState,
    required this.missingDefineKeys,
    required this.runAppMs,
    required this.firstFrameMs,
    required this.welcomeShownMs,
    required this.welcomeWindowInitMs,
    required this.welcomeCompletedMs,
    required this.shellFirstPaintMs,
    required this.androidActivityOnCreateMs,
    required this.androidFlutterEngineConfiguredMs,
    required this.deadlineOrigin,
    required this.attemptKind,
    required this.elapsedSinceProcessStartMs,
    required this.processElapsedMs,
    required this.homeFeedWarmMs,
    required this.homeReadyMs,
    required this.elapsedMs,
  });

  final String phase;
  final String attemptId;
  final String? runtimeEnv;
  final String? launchMode;
  final String? configurationState;
  final String missingDefineKeys;
  final int? runAppMs;
  final int? firstFrameMs;
  final int? welcomeShownMs;
  final int? welcomeWindowInitMs;
  final int? welcomeCompletedMs;
  final int? shellFirstPaintMs;
  final int? androidActivityOnCreateMs;
  final int? androidFlutterEngineConfiguredMs;
  final String deadlineOrigin;
  final String attemptKind;
  final int elapsedSinceProcessStartMs;
  final int processElapsedMs;
  final int? homeFeedWarmMs;
  final int? homeReadyMs;
  final int elapsedMs;

  /// 唯一 JSON 序列化出口；键名、键序与稀疏键条件必须与既往 payload 一致。
  Map<String, Object?> toJson() => <String, Object?>{
    'phase': phase,
    if (attemptId.isNotEmpty) 'attemptId': attemptId,
    'runtimeEnv': runtimeEnv,
    'launchMode': launchMode,
    'configurationState': configurationState,
    if (missingDefineKeys.isNotEmpty) 'missingDefineKeys': missingDefineKeys,
    if (runAppMs != null) 'runAppMs': runAppMs,
    if (firstFrameMs != null) 'firstFrameMs': firstFrameMs,
    if (welcomeShownMs != null) 'welcomeShownMs': welcomeShownMs,
    if (welcomeWindowInitMs != null) 'welcomeWindowInitMs': welcomeWindowInitMs,
    if (welcomeCompletedMs != null) 'welcomeCompletedMs': welcomeCompletedMs,
    if (shellFirstPaintMs != null) 'shellFirstPaintMs': shellFirstPaintMs,
    if (androidActivityOnCreateMs != null)
      'androidActivityOnCreateMs': androidActivityOnCreateMs,
    if (androidFlutterEngineConfiguredMs != null)
      'androidFlutterEngineConfiguredMs': androidFlutterEngineConfiguredMs,
    'deadlineOrigin': deadlineOrigin,
    'attemptKind': attemptKind,
    'elapsedSinceProcessStartMs': elapsedSinceProcessStartMs,
    'processElapsedMs': processElapsedMs,
    if (homeFeedWarmMs != null) 'homeFeedWarmMs': homeFeedWarmMs,
    if (homeReadyMs != null) 'homeReadyMs': homeReadyMs,
    'elapsedMs': elapsedMs,
  };
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
  int? _nativeElapsedSinceAttemptStartMs;
  int? _dartElapsedAtNativeHydrationMs;
  int? _deadlineElapsedAtBootstrapMs;
  int _dartElapsedAtDeadlineArmMs = 0;
  String _deadlineOrigin = 'fallbackDart';
  String _attemptKind = 'unknown';

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
    _nativeElapsedSinceAttemptStartMs = null;
    _dartElapsedAtNativeHydrationMs = null;
    _deadlineElapsedAtBootstrapMs = null;
    _dartElapsedAtDeadlineArmMs = 0;
    _deadlineOrigin = 'fallbackDart';
    _attemptKind = 'unknown';
  }

  void markBootstrapStarted() {
    if (_bootstrapStarted) {
      return;
    }
    _bootstrapStarted = true;
    _startupAttemptId = StartupTelemetrySupport.randomUrlSafeToken(24);
    _stopwatch.start();
    final platformElapsed = tryReadPlatformStartupElapsedMs();
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
    _recordPlatformStartupEvent(
      eventName: 'startup_attempt_started',
      properties: _snapshot(phase: 'startup_attempt_started').toJson(),
    );
    _recordCanonicalPhase(
      StartupTelemetryPhase.configurationValidation,
      outcome: 'validated',
    );
    _recordPlatformStartupEvent(
      eventName: 'startup_runtime_configured',
      properties: _snapshot(phase: 'configuration_validation').toJson(),
    );
  }

  /// Bootstrap 尚未装配 Provider/Analytics 时也必须留下脱敏终态。
  void recordBootstrapFailure(RuntimeFailureBase failure) {
    final properties = <String, Object?>{
      ..._snapshot(phase: 'bootstrap_failure').toJson(),
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
      _recordTerminal(
        outcome: 'recovery',
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
          ..._snapshot(phase: 'flutter_first_frame').toJson(),
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
  Future<void> beginNativeStartupAttempt({
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
        _nativeElapsedSinceAttemptStartMs = segments.elapsedSinceAttemptStartMs;
        _dartElapsedAtNativeHydrationMs = dartElapsedAtHydration;
        final nativeAttemptKind = segments.attemptKind?.trim() ?? '';
        if (nativeAttemptKind == 'cold' || nativeAttemptKind == 'hotRestart') {
          _attemptKind = nativeAttemptKind;
        }
        final nativeAttemptId = segments.startupAttemptId?.trim() ?? '';
        if (StartupTelemetrySupport.isValidAttemptId(nativeAttemptId)) {
          _startupAttemptId = nativeAttemptId;
        }
        final nativeDeadline = segments.elapsedSinceAttemptStartMs;
        if (nativeDeadline != null &&
            (_attemptKind == 'hotRestart' ||
                nativeDeadline > deadlineBeforeHydration)) {
          // Cold start 只能向前收紧；Hot Restart 则必须丢弃旧进程时钟，
          // 改用本次 Dart attempt 的单调时钟。
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
    _nativeTimingsBridge
        .beginStartupAttempt(_startupAttemptId)
        .then(
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
    final nativeElapsed = _nativeElapsedSinceAttemptStartMs;
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

  /// 进程总存活时间只用于诊断，不参与 Hot Restart 的 Welcome deadline。
  Duration get processElapsed {
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

  String get attemptKind => _attemptKind;

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

  /// [properties] 是即将 jsonEncode 的事件附加 JSON 属性（不再向外传播）。
  void recordStartupPhase(
    ProviderReader read, {
    required String phase,
    String eventName = 'app_startup_phase',
    Map<String, Object?> properties = const <String, Object?>{},
  }) {
    final eventProperties = <String, Object?>{
      ..._snapshot(phase: phase).toJson(),
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
        jsonEncode(<String, Object?>{
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

  StartupPhaseSnapshot phaseSnapshot({required String phase}) {
    return _snapshot(phase: phase);
  }

  void _recordCanonicalPhaseFromReportedPhase({
    required String phase,
    required String outcome,
    required Map<String, Object?> properties,
  }) {
    if (phase == 'safe_recovery_shown') {
      _recordTerminal(
        outcome: 'recovery',
        failureCode: properties['failureCode']?.toString() ?? '',
        failureSource: properties['failureSource']?.toString() ?? 'router',
      );
      StartupTelemetryRuntime.instance.flush();
      return;
    }
    final canonical = switch (phase) {
      'router_preload_ready' => StartupTelemetryPhase.routerReady,
      'router_preload_failed' ||
      'router_loading_failed' => StartupTelemetryPhase.routerFailure,
      'router_loading' => StartupTelemetryPhase.routerPreload,
      'main_shell_first_paint' => StartupTelemetryPhase.shellFirstPaint,
      _ => null,
    };
    if (canonical == null) {
      return;
    }
    _recordCanonicalPhase(
      canonical,
      outcome: outcome,
      failureCode: properties['failureCode']?.toString() ?? '',
      failureSource: canonical == StartupTelemetryPhase.routerFailure
          ? properties['failureSource']?.toString() ?? 'router'
          : properties['failureSource']?.toString() ?? '',
      deadlineOrigin: properties['deadlineOrigin']?.toString() ?? '',
    );
  }

  void _recordCanonicalPhase(
    StartupTelemetryPhase phase, {
    required String outcome,
    int? elapsedMs,
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
    // 启动身份维度只携带运行时真实在场的值；缺席以不发送表达，
    // 不得用零值/unknown 冒充（catalog enum 之外的值会被 ingest 拒绝）。
    final environment = CloudRuntimeConfig.appRuntimeEnv;
    final launchProvenance = CloudRuntimeConfig.launchMode;
    final launchManifestDigest =
        CloudRuntimeConfig.effectiveLaunchManifestDigest;
    const buildMode = kReleaseMode
        ? 'release'
        : (kProfileMode ? 'profile' : 'debug');
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
          environment: environment.isEmpty ? null : environment,
          buildMode: buildMode,
          launchProvenance: launchProvenance,
          launchManifestDigest:
              launchManifestDigest.isEmpty ? null : launchManifestDigest,
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
        ..._snapshot(phase: 'startup_safe_terminal').toJson(),
      },
    );
  }

  void _recordPlatformStartupEvent({
    required String eventName,
    required Map<String, Object?> properties,
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

  StartupPhaseSnapshot _snapshot({required String phase}) {
    final runtimeSummary = CloudRuntimeConfig.runtimeDefineSummary;
    return StartupPhaseSnapshot(
      phase: phase,
      attemptId: _startupAttemptId,
      runtimeEnv: runtimeSummary['runtimeEnv'],
      launchMode: runtimeSummary['launchMode'],
      configurationState: runtimeSummary['configurationState'],
      missingDefineKeys: runtimeSummary['missingKeys'] ?? '',
      runAppMs: _runAppMs,
      firstFrameMs: _firstFrameMs,
      welcomeShownMs: _welcomeShownMs,
      welcomeWindowInitMs: _welcomeWindowInitMs,
      welcomeCompletedMs: _welcomeCompletedMs,
      shellFirstPaintMs: _shellFirstPaintMs,
      androidActivityOnCreateMs: _androidActivityOnCreateMs,
      androidFlutterEngineConfiguredMs: _androidFlutterEngineConfiguredMs,
      deadlineOrigin: _deadlineOrigin,
      attemptKind: _attemptKind,
      elapsedSinceProcessStartMs: elapsedSinceProcessStart.inMilliseconds,
      processElapsedMs: processElapsed.inMilliseconds,
      homeFeedWarmMs: _homeFeedWarmMs,
      homeReadyMs: _homeReadyMs,
      elapsedMs: _elapsedMs,
    );
  }

  int get _elapsedMs {
    if (!_stopwatch.isRunning) {
      return 0;
    }
    return _stopwatch.elapsedMilliseconds;
  }
}
