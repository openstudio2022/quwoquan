import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/scheduler.dart';
import 'package:quwoquan_app/app/app_startup_runtime.dart';
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
        widget.onWelcomeVisible?.call();
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
          _armDeadline();
        }
      case AppLifecycleState.paused:
      case AppLifecycleState.hidden:
      case AppLifecycleState.detached:
        _backgrounded = true;
        _deadlineTimer?.cancel();
        _controller.stop(canceled: false);
        _resumeCompleter ??= Completer<void>();
      case AppLifecycleState.inactive:
        break;
    }
  }

  bool get _isStartup => widget.flowMode == WelcomeFlowMode.startup;

  Duration _elapsed() =>
      widget.elapsedSinceProcessStart?.call() ??
      AppStartupRuntime.instance.elapsedSinceProcessStart;

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
    unawaited(
      AppStartupRuntime.instance.hydrateNativeProcessSegments().whenComplete(
        () {
          if (mounted && !_terminal) {
            _armDeadline();
          }
        },
      ),
    );
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

  Future<void> _runReducedMotion() async {
    _readyAtCycleStart = widget.shellEntryReady;
    await _runPhase(WelcomeMotionPhase.handoffHold, widget.timing.handoffHold);
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

    while (mounted && !_terminal && _controller.value < 1) {
      await _waitUntilResumed();
      if (!mounted || _terminal) {
        return;
      }
      try {
        await _controller.forward(from: _controller.value).orCancel;
      } on TickerCanceled {
        if (!mounted || _terminal) {
          return;
        }
      }
    }
  }

  Future<void> _waitUntilResumed() async {
    if (!_backgrounded) {
      return;
    }
    final resume = _resumeCompleter ??= Completer<void>();
    await resume.future;
  }

  void _armDeadline() {
    _deadlineTimer?.cancel();
    if (!_isStartup || _terminal || _backgrounded) {
      return;
    }
    final remaining = _remainingMotionBudget;
    if (remaining == Duration.zero) {
      scheduleMicrotask(() => _finish(WelcomeExitReason.deadline));
      return;
    }
    _deadlineTimer = Timer(remaining, () {
      _finish(WelcomeExitReason.deadline);
    });
  }

  void _finish(WelcomeExitReason reason) {
    if (_terminal) {
      return;
    }
    _terminal = true;
    _deadlineTimer?.cancel();
    _controller
      ..stop(canceled: false)
      ..value = 1;
    _phase = WelcomeMotionPhase.finished;
    _emit(exitReason: reason);
    if (mounted) {
      setState(() {});
    }
    scheduleMicrotask(widget.onFinish);
  }

  void _emit({WelcomeExitReason? exitReason}) {
    widget.onSequenceEvent?.call(
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
    _deadlineTimer?.cancel();
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

  @override
  Widget build(BuildContext context) {
    final appearance = WelcomeAppearance.of(context);
    return AppScaffold(
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
            _buildBackground(appearance),
            WelcomeBrandCluster(
              flower: _buildGraphicArea(appearance),
              typography: WelcomeBrandCluster.buildTypography(appearance),
            ),
            if (_hintVisible)
              _buildStartupInlineHint(appearance)
            else
              _buildAssistantWhisper(appearance),
          ],
        ),
      ),
    );
  }

  Widget _buildBackground(WelcomeAppearance appearance) {
    return Positioned.fill(
      child: DecoratedBox(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: <Color>[
              appearance.gradientStart,
              appearance.background,
              appearance.gradientEnd,
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildGraphicArea(WelcomeAppearance appearance) {
    return SizedBox.square(
      dimension: AppSpacing.welcomeGraphicDiameter,
      child: AnimatedBuilder(
        animation: _controller,
        builder: (context, child) => WelcomeFlowerMark(
          appearance: appearance,
          petalBloomAmounts: WelcomeMotionTimeline.petalBloomAmounts(
            phase: _phase,
            phaseProgress: _controller.value,
            timing: widget.timing,
          ),
        ),
      ),
    );
  }

  Widget _buildAssistantWhisper(WelcomeAppearance appearance) {
    return Positioned(
      left: 0,
      right: 0,
      bottom: 0,
      child: SafeArea(
        top: false,
        child: Padding(
          padding: EdgeInsets.only(
            left: AppSpacing.lg,
            right: AppSpacing.lg,
            bottom: AppSpacing.xl,
          ),
          child: Text.rich(
            TextSpan(
              style: TextStyle(
                fontSize: AppTypography.xs,
                fontWeight: AppTypography.regular,
                color: appearance.foregroundMuted.withValues(alpha: 0.78),
                height: AppTypography.lineHeightCompact,
                decoration: TextDecoration.none,
              ),
              children: <InlineSpan>[
                WidgetSpan(
                  alignment: PlaceholderAlignment.middle,
                  child: Padding(
                    padding: EdgeInsets.only(right: AppSpacing.xs),
                    child: Icon(
                      CupertinoIcons.sparkles,
                      size: AppSpacing.fourteen,
                      color: AppColors.assistantMarkColorOnDark,
                    ),
                  ),
                ),
                TextSpan(
                  text: '${UITextConstants.assistantWhisperSignature}  ',
                  style: TextStyle(
                    fontWeight: AppTypography.semiBold,
                    color: AppColors.welcomeForeground.withValues(alpha: 0.85),
                  ),
                ),
                TextSpan(text: UITextConstants.assistantWhisperLine),
              ],
            ),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            textAlign: TextAlign.center,
          ),
        ),
      ),
    );
  }

  Widget _buildStartupInlineHint(WelcomeAppearance appearance) {
    return Positioned(
      left: AppSpacing.containerLg,
      right: AppSpacing.containerLg,
      bottom: 0,
      child: SafeArea(
        top: false,
        child: Padding(
          padding: EdgeInsets.only(bottom: AppSpacing.xl),
          child: SizedBox(
            height: AppSpacing.radiusTwentyFour,
            child: Text(
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
      ),
    );
  }
}
