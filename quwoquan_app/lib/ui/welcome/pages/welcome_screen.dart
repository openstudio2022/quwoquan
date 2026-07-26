import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';
import 'package:quwoquan_app/app/app_startup_runtime.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_exception_telemetry_service.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/ui/welcome/welcome_appearance.dart';
import 'package:quwoquan_app/ui/welcome/welcome_motion_timeline.dart';
import 'package:quwoquan_app/ui/welcome/widgets/welcome_brand_cluster.dart';
import 'package:quwoquan_app/ui/welcome/widgets/welcome_flower_mark.dart';

/// 唯一的 Flutter 欢迎页。
///
/// 首帧固定为全开终态；冷启动只在完整周期的全开边界检查 Shell readiness。
/// 生产默认一轮约 1.48 秒，6 秒仅为从进程启动起计算的硬退出上限。
///
/// 信息结构固定为：深蓝渐变背景 + 八瓣花 + slogan + 底部品牌名 +
/// （仅首轮未 ready 时）单行启动提示；无标题、按钮、进度与装饰层。
class WelcomeScreen extends StatefulWidget {
  const WelcomeScreen({
    super.key,
    required this.onFinish,
    this.flowMode = WelcomeFlowMode.entry,
    this.shellEntryReady = true,
    this.timing = StartupWelcomeTiming.production,
    this.elapsedSinceProcessStart,
    this.deadlineOrigin,
    this.onWelcomeVisible,
    this.onSequenceEvent,
  });

  final VoidCallback onFinish;
  final WelcomeFlowMode flowMode;
  final bool shellEntryReady;
  final StartupWelcomeTiming timing;
  final Duration Function()? elapsedSinceProcessStart;
  final String Function()? deadlineOrigin;
  final VoidCallback? onWelcomeVisible;
  final ValueChanged<WelcomeSequenceEvent>? onSequenceEvent;

  @override
  State<WelcomeScreen> createState() => _WelcomeScreenState();
}

class _WelcomeScreenState extends State<WelcomeScreen>
    with SingleTickerProviderStateMixin, WidgetsBindingObserver {
  late final AnimationController _controller;
  WelcomeMotionPhase _phase = WelcomeMotionPhase.nativeStatic;
  Timer? _deadlineTimer;
  final Set<Timer> _wallClockTimers = <Timer>{};
  final Completer<void> _disposedCompleter = Completer<void>();
  Completer<void>? _resumeCompleter;
  bool _started = false;
  bool _running = false;
  bool _terminal = false;
  bool _backgrounded = false;
  bool _motionReduced = false;
  bool _animationCompressed = false;
  bool _hintVisible = false;
  bool _readyAtCycleStart = false;
  int _cycleIndex = 0;
  int _replayCount = 0;
  final List<int> _buildFrameMs = <int>[];
  final List<int> _rasterFrameMs = <int>[];
  int _consecutiveSlowFrames = 0;
  bool _slowFrameStreakDetected = false;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(vsync: this);
    WidgetsBinding.instance
      ..addObserver(this)
      ..addTimingsCallback(_recordFrameTimings)
      ..addPostFrameCallback((_) {
        AppStartupRuntime.instance.markWelcomeShown();
        if (!mounted) {
          return;
        }
        // 可见回调失败不得阻断动效/退出；否则会永久停在欢迎终态。
        try {
          widget.onWelcomeVisible?.call();
        } catch (error, stackTrace) {
          _reportNonBlockingFailure(
            'notify shell welcome visibility',
            error,
            stackTrace,
          );
        }
        unawaited(_begin());
      });
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _motionReduced = MediaQuery.disableAnimationsOf(context);
  }

  @override
  void didUpdateWidget(covariant WelcomeScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!oldWidget.shellEntryReady &&
        widget.shellEntryReady &&
        _motionReduced &&
        _running &&
        !_terminal) {
      _finish(WelcomeExitReason.reducedMotion);
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    switch (state) {
      case AppLifecycleState.resumed:
        _backgrounded = false;
        final resume = _resumeCompleter;
        _resumeCompleter = null;
        if (resume != null && !resume.isCompleted) {
          resume.complete();
        }
        if (_isStartup && _remainingMotionBudget == Duration.zero) {
          _finish(WelcomeExitReason.deadline);
        } else {
          // 硬截止在后台仍继续计时；恢复时仅按剩余预算刷新。
          _armDeadline();
        }
      case AppLifecycleState.paused:
      case AppLifecycleState.hidden:
      case AppLifecycleState.detached:
        _backgrounded = true;
        // 不取消硬截止：后台暂停动画可以，但不能取消进入主壳的安全阀。
        _controller.stop(canceled: false);
        _resumeCompleter ??= Completer<void>();
      case AppLifecycleState.inactive:
        break;
    }
  }

  bool get _isStartup => widget.flowMode == WelcomeFlowMode.startup;

  Duration _elapsed() =>
      widget.elapsedSinceProcessStart?.call() ??
      AppStartupRuntime.instance.deadlineElapsedSinceProcessStart;

  String _deadlineOrigin() =>
      widget.deadlineOrigin?.call() ??
      AppStartupRuntime.instance.deadlineOrigin;

  Duration get _remainingBudget {
    final remaining = widget.timing.hardEntryDeadline - _elapsed();
    return remaining.isNegative ? Duration.zero : remaining;
  }

  Duration get _remainingMotionBudget {
    final remaining = _remainingBudget - widget.timing.shellTransitionReserve;
    return remaining.isNegative ? Duration.zero : remaining;
  }

  Future<void> _begin() async {
    if (_started || widget.flowMode == WelcomeFlowMode.frozen) {
      return;
    }
    _started = true;
    unawaited(_refreshNativeSegmentsWithoutBlockingWelcome());
    _readyAtCycleStart = widget.shellEntryReady;
    _emit();
    if (!mounted || _terminal) {
      return;
    }
    _running = true;
    _armDeadline();
    if (_motionReduced) {
      await _runReducedMotion();
      return;
    }
    await _runMotion();
  }

  Future<void> _refreshNativeSegmentsWithoutBlockingWelcome() async {
    try {
      await AppStartupRuntime.instance.hydrateNativeProcessSegments(
        cancellationSignal: _disposedCompleter.future,
      );
    } catch (error, stackTrace) {
      // MethodChannel 超时或未知平台错误只降级到 Dart 时钟，但必须留下诊断。
      _reportNonBlockingFailure(
        'hydrate native process segments; fallback to Dart clock',
        error,
        stackTrace,
      );
    }
  }

  Future<void> _runReducedMotion() async {
    _readyAtCycleStart = widget.shellEntryReady;
    // 减弱动效时不依赖 AnimationController/Ticker，避免 ticker 静默导致永等。
    _phase = WelcomeMotionPhase.handoffHold;
    _controller.value = 1;
    if (mounted) {
      setState(() {});
    }
    _emit();
    await _waitWallClock(widget.timing.handoffHold);
    if (_terminal) {
      return;
    }
    if (widget.flowMode == WelcomeFlowMode.entry) {
      _finish(WelcomeExitReason.entryComplete);
    } else if (widget.shellEntryReady) {
      _finish(WelcomeExitReason.reducedMotion);
    } else {
      _finish(WelcomeExitReason.degraded);
    }
  }

  Future<void> _runMotion() async {
    final primaryScale = _cycleScale(widget.timing.primaryCycleDuration);
    if (primaryScale == null) {
      final hold = _remainingMotionBudget < widget.timing.handoffHold
          ? _remainingMotionBudget
          : widget.timing.handoffHold;
      if (hold > Duration.zero) {
        await _runPhase(WelcomeMotionPhase.handoffHold, hold);
      }
      _finish(WelcomeExitReason.deadline);
      return;
    }
    _animationCompressed = primaryScale < 1;
    await _playCycle(primary: true, scale: primaryScale);

    while (mounted && !_terminal) {
      if (widget.flowMode == WelcomeFlowMode.entry) {
        _finish(WelcomeExitReason.entryComplete);
        return;
      }
      if (widget.shellEntryReady) {
        _finish(
          _replayCount == 0
              ? WelcomeExitReason.readyPrimary
              : WelcomeExitReason.readyReplay,
        );
        return;
      }
      if (_replayCount >= widget.timing.maxReplayCount) {
        _finish(WelcomeExitReason.degraded);
        return;
      }

      final replayScale = _cycleScale(widget.timing.replayCycleDuration);
      if (replayScale == null) {
        _finish(WelcomeExitReason.deadline);
        return;
      }
      _replayCount += 1;
      _cycleIndex = _replayCount;
      _hintVisible = true;
      _animationCompressed = _animationCompressed || replayScale < 1;
      if (mounted) {
        setState(() {});
      }
      await _playCycle(primary: false, scale: replayScale);
    }
  }

  double? _cycleScale(Duration cycleDuration) {
    if (!_isStartup) {
      return 1;
    }
    final available = _remainingMotionBudget;
    if (available <= Duration.zero) {
      return null;
    }
    final ratio = available.inMicroseconds / cycleDuration.inMicroseconds;
    if (ratio < widget.timing.minimumCompressionRatio) {
      return null;
    }
    return ratio.clamp(widget.timing.minimumCompressionRatio, 1.0);
  }

  Future<void> _playCycle({
    required bool primary,
    required double scale,
  }) async {
    _readyAtCycleStart = widget.shellEntryReady;
    if (primary) {
      await _runPhase(
        WelcomeMotionPhase.handoffHold,
        widget.timing.scaled(widget.timing.handoffHold, scale),
      );
    }
    await _runPhase(
      WelcomeMotionPhase.gathering,
      widget.timing.scaled(widget.timing.gatheringDuration, scale),
    );
    await _runPhase(
      WelcomeMotionPhase.budPause,
      widget.timing.scaled(widget.timing.budPause, scale),
    );
    await _runPhase(
      WelcomeMotionPhase.blooming,
      widget.timing.scaled(widget.timing.bloomingDuration, scale),
    );
    await _runPhase(
      WelcomeMotionPhase.openSettle,
      widget.timing.scaled(widget.timing.openSettle, scale),
    );
  }

  Future<void> _runPhase(WelcomeMotionPhase phase, Duration duration) async {
    if (!mounted || _terminal) {
      return;
    }
    _phase = phase;
    _controller
      ..duration = duration
      ..value = 0;
    setState(() {});
    _emit();
    _armDeadline();

    // 相位墙钟上限：防止 TickerCanceled 空转或 ticker 静默饿死事件循环。
    final phaseDeadline = DateTime.now().add(
      duration + const Duration(milliseconds: 400),
    );

    while (mounted && !_terminal && _controller.value < 1) {
      if (DateTime.now().isAfter(phaseDeadline)) {
        _controller.value = 1;
        break;
      }
      await _waitUntilResumed();
      if (!mounted || _terminal) {
        return;
      }
      final before = _controller.value;
      try {
        await _controller.forward(from: _controller.value).orCancel;
      } on TickerCanceled {
        if (!mounted || _terminal) {
          return;
        }
      }
      if (_controller.value <= before + 0.0001 && _controller.value < 1) {
        // 无进展时让出事件循环，避免饿死硬截止 Timer。
        await _waitWallClock(const Duration(milliseconds: 16));
      }
    }
    if (_controller.value < 1 && !_terminal) {
      _controller.value = 1;
    }
  }

  Future<void> _waitWallClock(Duration duration) {
    if (duration <= Duration.zero) {
      return Future<void>.value();
    }
    final completer = Completer<void>();
    late final Timer timer;
    timer = Timer(duration, () {
      _wallClockTimers.remove(timer);
      if (!completer.isCompleted) {
        completer.complete();
      }
    });
    _wallClockTimers.add(timer);
    return completer.future;
  }

  void _cancelWallClockTimers() {
    for (final timer in _wallClockTimers) {
      timer.cancel();
    }
    _wallClockTimers.clear();
  }

  Future<void> _waitUntilResumed() async {
    if (!_backgrounded) {
      return;
    }
    final resume = _resumeCompleter ??= Completer<void>();
    // 后台等待也设墙钟上限：避免 hidden/paused 无 resumed 时永久卡住。
    await Future.any<void>([
      resume.future,
      _waitWallClock(const Duration(seconds: 2)),
    ]);
    if (_backgrounded && mounted && !_terminal) {
      // 超时仍未 resume：按前台降级继续，硬截止负责最终退出。
      _backgrounded = false;
      _resumeCompleter = null;
      if (!resume.isCompleted) {
        resume.complete();
      }
      _armDeadline();
    }
  }

  void _armDeadline() {
    if (_terminal) {
      return;
    }
    // 启动路径：硬截止一旦武装就只随剩余预算刷新，不因 background 取消。
    // entry 路径：补安全上限，避免无 readiness 门控时 ticker 故障永停。
    final budget = _isStartup
        ? _remainingMotionBudget
        : const Duration(seconds: 8);
    _deadlineTimer?.cancel();
    if (budget == Duration.zero) {
      scheduleMicrotask(() => _finish(WelcomeExitReason.deadline));
      return;
    }
    _deadlineTimer = Timer(budget, () {
      _finish(WelcomeExitReason.deadline);
    });
  }

  void _finish(WelcomeExitReason reason) {
    if (_terminal) {
      return;
    }
    _terminal = true;
    _deadlineTimer?.cancel();
    _cancelWallClockTimers();
    final resume = _resumeCompleter;
    _resumeCompleter = null;
    if (resume != null && !resume.isCompleted) {
      resume.complete();
    }
    try {
      _controller
        ..stop(canceled: false)
        ..value = 1;
    } catch (error, stackTrace) {
      _reportNonBlockingFailure(
        'commit welcome animation terminal state',
        error,
        stackTrace,
      );
    }
    _phase = WelcomeMotionPhase.finished;
    try {
      _emit(exitReason: reason);
    } catch (error, stackTrace) {
      // 观测回调失败不得阻断进入主壳。
      _reportNonBlockingFailure(
        'emit welcome sequence exit telemetry',
        error,
        stackTrace,
      );
    }
    if (mounted) {
      setState(() {});
    }
    scheduleMicrotask(() {
      try {
        widget.onFinish();
      } catch (error, stackTrace) {
        _reportNonBlockingFailure(
          'enter app shell from welcome',
          error,
          stackTrace,
        );
      }
    });
  }

  void _emit({WelcomeExitReason? exitReason}) {
    final callback = widget.onSequenceEvent;
    if (callback == null) {
      return;
    }
    try {
      callback(
        WelcomeSequenceEvent(
          phase: _phase,
          cycleIndex: _cycleIndex,
          replayCount: _replayCount,
          elapsedSinceProcessStart: _elapsed(),
          remainingBudget: _remainingBudget,
          readyAtCycleStart: _readyAtCycleStart,
          readyAtCycleEnd: widget.shellEntryReady,
          hintVisible: _hintVisible,
          motionReduced: _motionReduced,
          animationCompressed: _animationCompressed,
          deadlineOrigin: _deadlineOrigin(),
          exitReason: exitReason,
          buildFrameP95Ms: _percentile95(_buildFrameMs),
          rasterFrameP95Ms: _percentile95(_rasterFrameMs),
          slowFrameStreakDetected: _slowFrameStreakDetected,
        ),
      );
    } catch (error, stackTrace) {
      _reportNonBlockingFailure(
        'emit welcome sequence telemetry',
        error,
        stackTrace,
      );
    }
  }

  void _reportNonBlockingFailure(
    String operation,
    Object error,
    StackTrace stackTrace,
  ) {
    unawaited(
      AppExceptionTelemetryService.instance.recordHandledException(
        source: 'welcome.$operation',
        error: error,
        stackTrace: stackTrace,
        pageId: 'welcome',
        pageName: 'welcome',
        surfaceId: 'welcome',
        routeId: 'welcome',
        operationId: 'app.welcome.sequence',
      ),
    );
  }

  void _recordFrameTimings(List<FrameTiming> timings) {
    if (_terminal) {
      return;
    }
    for (final timing in timings) {
      final buildMs = timing.buildDuration.inMilliseconds;
      final rasterMs = timing.rasterDuration.inMilliseconds;
      _buildFrameMs.add(buildMs);
      _rasterFrameMs.add(rasterMs);
      if (buildMs > 32 || rasterMs > 32) {
        _consecutiveSlowFrames += 1;
        if (_consecutiveSlowFrames >= 2) {
          _slowFrameStreakDetected = true;
        }
      } else {
        _consecutiveSlowFrames = 0;
      }
    }
  }

  int? _percentile95(List<int> values) {
    if (values.isEmpty) {
      return null;
    }
    final sorted = List<int>.of(values)..sort();
    final index = ((sorted.length - 1) * 0.95).ceil();
    return sorted[index];
  }

  @override
  void dispose() {
    if (!_disposedCompleter.isCompleted) {
      _disposedCompleter.complete();
    }
    _deadlineTimer?.cancel();
    _cancelWallClockTimers();
    final resume = _resumeCompleter;
    if (resume != null && !resume.isCompleted) {
      resume.complete();
    }
    WidgetsBinding.instance
      ..removeObserver(this)
      ..removeTimingsCallback(_recordFrameTimings);
    _controller.dispose();
    super.dispose();
  }

  /// 启动提示淡入时长：轻微淡入出现，不推动其他元素重新布局。
  static const Duration _hintFadeDuration = Duration(milliseconds: 240);

  /// 品牌屏统一状态栏语义：透明背景 + 适合深蓝底的浅色内容，
  /// 与原生启动阶段一致，深浅色系统模式下不切换。
  static const SystemUiOverlayStyle _brandOverlayStyle = SystemUiOverlayStyle(
    statusBarColor: AppColors.transparent,
    statusBarIconBrightness: Brightness.light,
    statusBarBrightness: Brightness.dark,
    systemNavigationBarColor: AppColors.transparent,
    systemNavigationBarIconBrightness: Brightness.light,
  );

  @override
  Widget build(BuildContext context) {
    final appearance = WelcomeAppearance.of(context);
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: _brandOverlayStyle,
      child: AppScaffold(
        backgroundColor: appearance.background,
        resizeToAvoidBottomInset: false,
        body: DefaultTextStyle.merge(
          style: const TextStyle(
            decoration: TextDecoration.none,
            decorationThickness: 0,
          ),
          child: Stack(
            fit: StackFit.expand,
            children: [
              WelcomeStaticFrame(flower: _buildAnimatedFlower(appearance)),
              _buildStartupInlineHint(appearance),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildAnimatedFlower(WelcomeAppearance appearance) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, child) => WelcomeFlowerMark(
        appearance: appearance,
        petalBloomAmounts: WelcomeMotionTimeline.petalBloomAmounts(
          phase: _phase,
          phaseProgress: _controller.value,
          timing: widget.timing,
        ),
      ),
    );
  }

  /// 单行启动提示：固定 24px 槽位挂在底部品牌名上方，文案只做轻微淡入，
  /// 出现与消失都不会推动品牌簇或品牌名重新布局。
  Widget _buildStartupInlineHint(WelcomeAppearance appearance) {
    final media = MediaQuery.of(context);
    final hintBottom =
        WelcomeBrandFooter.resolveStripHeight(
          viewportHeight: media.size.height,
          bottomInset: media.padding.bottom,
        ) +
        AppSpacing.welcomeStartupHintToBrandGap;
    return Positioned(
      left: AppSpacing.containerLg,
      right: AppSpacing.containerLg,
      bottom: hintBottom,
      child: SizedBox(
        height: AppSpacing.welcomeStartupHintSlotHeight,
        child: AnimatedSwitcher(
          duration: _hintFadeDuration,
          switchInCurve: Curves.easeOutCubic,
          switchOutCurve: Curves.easeOutCubic,
          child: !_hintVisible
              ? const SizedBox.shrink()
              : Text(
                  UITextConstants.startupStillStartingInline,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: AppTypography.xs,
                    fontWeight: AppTypography.medium,
                    color: appearance.foregroundMuted.withValues(alpha: 0.82),
                    height: AppTypography.lineHeightCompact,
                    decoration: TextDecoration.none,
                  ),
                ),
        ),
      ),
    );
  }
}
