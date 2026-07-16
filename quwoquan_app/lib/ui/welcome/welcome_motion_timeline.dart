import 'package:flutter/animation.dart';
import 'package:flutter/foundation.dart';

enum WelcomeFlowMode { startup, entry, frozen }

enum WelcomeMotionPhase {
  nativeStatic,
  handoffHold,
  gathering,
  budPause,
  blooming,
  openSettle,
  finished,
}

enum WelcomeExitReason {
  readyPrimary,
  readyReplay,
  degraded,
  deadline,
  reducedMotion,
  entryComplete,
}

extension WelcomeExitReasonWireName on WelcomeExitReason {
  String get wireName => switch (this) {
    WelcomeExitReason.readyPrimary => 'ready_primary',
    WelcomeExitReason.readyReplay => 'ready_replay',
    WelcomeExitReason.degraded => 'degraded',
    WelcomeExitReason.deadline => 'deadline',
    WelcomeExitReason.reducedMotion => 'reduced_motion',
    WelcomeExitReason.entryComplete => 'entry_complete',
  };
}

@immutable
class StartupWelcomeTiming {
  const StartupWelcomeTiming({
    required this.handoffHold,
    required this.gatherPetalDuration,
    required this.gatherPetalStagger,
    required this.budPause,
    required this.bloomPetalDuration,
    required this.bloomPetalStagger,
    required this.openSettle,
    required this.shellTransitionReserve,
    required this.softEntryTarget,
    required this.hardEntryDeadline,
    required this.maxReplayCount,
    this.minimumCompressionRatio = 0.65,
  });

  const StartupWelcomeTiming.test({
    this.handoffHold = const Duration(milliseconds: 10),
    this.gatherPetalDuration = const Duration(milliseconds: 13),
    this.gatherPetalStagger = const Duration(milliseconds: 1),
    this.budPause = const Duration(milliseconds: 5),
    this.bloomPetalDuration = const Duration(milliseconds: 13),
    this.bloomPetalStagger = const Duration(milliseconds: 1),
    this.openSettle = const Duration(milliseconds: 10),
    this.shellTransitionReserve = const Duration(milliseconds: 10),
    this.softEntryTarget = const Duration(milliseconds: 100),
    this.hardEntryDeadline = const Duration(milliseconds: 300),
    this.maxReplayCount = 2,
    this.minimumCompressionRatio = 0.65,
  });

  static const int petalCount = 8;

  static const StartupWelcomeTiming production = StartupWelcomeTiming(
    handoffHold: Duration(milliseconds: 90),
    gatherPetalDuration: Duration(milliseconds: 240),
    gatherPetalStagger: Duration(milliseconds: 25),
    budPause: Duration(milliseconds: 70),
    bloomPetalDuration: Duration(milliseconds: 500),
    bloomPetalStagger: Duration(milliseconds: 45),
    openSettle: Duration(milliseconds: 90),
    shellTransitionReserve: Duration(milliseconds: 120),
    softEntryTarget: Duration(seconds: 3),
    hardEntryDeadline: Duration(seconds: 6),
    maxReplayCount: 2,
  );

  final Duration handoffHold;
  final Duration gatherPetalDuration;
  final Duration gatherPetalStagger;
  final Duration budPause;
  final Duration bloomPetalDuration;
  final Duration bloomPetalStagger;
  final Duration openSettle;
  final Duration shellTransitionReserve;
  final Duration softEntryTarget;
  final Duration hardEntryDeadline;
  final int maxReplayCount;
  final double minimumCompressionRatio;

  Duration get gatheringDuration =>
      gatherPetalDuration + gatherPetalStagger * (petalCount - 1);

  Duration get bloomingDuration =>
      bloomPetalDuration + bloomPetalStagger * (petalCount - 1);

  Duration get primaryCycleDuration =>
      handoffHold +
      gatheringDuration +
      budPause +
      bloomingDuration +
      openSettle;

  Duration get replayCycleDuration =>
      gatheringDuration + budPause + bloomingDuration + openSettle;

  Duration scaled(Duration duration, double scale) {
    if (duration == Duration.zero) {
      return duration;
    }
    final milliseconds = (duration.inMicroseconds * scale / 1000).round();
    return Duration(milliseconds: milliseconds.clamp(1, 1 << 30));
  }
}

@immutable
class WelcomeSequenceEvent {
  const WelcomeSequenceEvent({
    required this.phase,
    required this.cycleIndex,
    required this.replayCount,
    required this.elapsedSinceProcessStart,
    required this.remainingBudget,
    required this.readyAtCycleStart,
    required this.readyAtCycleEnd,
    required this.hintVisible,
    required this.motionReduced,
    required this.animationCompressed,
    required this.deadlineOrigin,
    this.exitReason,
    this.buildFrameP95Ms,
    this.rasterFrameP95Ms,
    this.slowFrameStreakDetected = false,
  });

  static const String motionSpecVersion = 'petal_bloom_v2';

  final WelcomeMotionPhase phase;
  final int cycleIndex;
  final int replayCount;
  final Duration elapsedSinceProcessStart;
  final Duration remainingBudget;
  final bool readyAtCycleStart;
  final bool readyAtCycleEnd;
  final bool hintVisible;
  final bool motionReduced;
  final bool animationCompressed;
  final String deadlineOrigin;
  final WelcomeExitReason? exitReason;
  final int? buildFrameP95Ms;
  final int? rasterFrameP95Ms;
  final bool slowFrameStreakDetected;

  Map<String, Object?> toProperties() => <String, Object?>{
    'phase': phase.name,
    'motionSpecVersion': motionSpecVersion,
    'cycleIndex': cycleIndex,
    'replayCount': replayCount,
    'deadlineOrigin': deadlineOrigin,
    'elapsedSinceProcessStartMs': elapsedSinceProcessStart.inMilliseconds,
    'remainingBudgetMs': remainingBudget.inMilliseconds,
    'readyAtCycleStart': readyAtCycleStart,
    'readyAtCycleEnd': readyAtCycleEnd,
    'hintVisible': hintVisible,
    'motionReduced': motionReduced,
    'animationCompressed': animationCompressed,
    if (exitReason != null) 'exitReason': exitReason!.wireName,
    if (exitReason != null)
      'welcomeExitMs': elapsedSinceProcessStart.inMilliseconds,
    if (buildFrameP95Ms != null) 'buildFrameP95Ms': buildFrameP95Ms,
    if (rasterFrameP95Ms != null) 'rasterFrameP95Ms': rasterFrameP95Ms,
    'slowFrameStreakDetected': slowFrameStreakDetected,
  };
}

/// 将单一控制器的线性进度映射为八片花瓣各自的线性绽放度。
///
/// 聚拢按 7 -> 0 逆序，绽放按 0 -> 7 顺时针。easing 与 stagger 只存在
/// 于时间轴，painter 只消费最终的 `bloomAmount`。
abstract final class WelcomeMotionTimeline {
  static const int petalCount = StartupWelcomeTiming.petalCount;
  static const List<int> gatheringOrder = <int>[7, 6, 5, 4, 3, 2, 1, 0];
  static const List<int> bloomingOrder = <int>[0, 1, 2, 3, 4, 5, 6, 7];

  static List<double> petalBloomAmounts({
    required WelcomeMotionPhase phase,
    required double phaseProgress,
    StartupWelcomeTiming timing = StartupWelcomeTiming.production,
  }) {
    final progress = phaseProgress.clamp(0.0, 1.0);
    return switch (phase) {
      WelcomeMotionPhase.gathering => _staggeredAmounts(
        progress: progress,
        order: gatheringOrder,
        petalDuration: timing.gatherPetalDuration,
        stagger: timing.gatherPetalStagger,
        curve: Curves.easeInOutCubic,
        gathering: true,
      ),
      WelcomeMotionPhase.budPause => List<double>.filled(petalCount, 0),
      WelcomeMotionPhase.blooming => _staggeredAmounts(
        progress: progress,
        order: bloomingOrder,
        petalDuration: timing.bloomPetalDuration,
        stagger: timing.bloomPetalStagger,
        curve: Curves.easeOutCubic,
        gathering: false,
      ),
      WelcomeMotionPhase.nativeStatic ||
      WelcomeMotionPhase.handoffHold ||
      WelcomeMotionPhase.openSettle ||
      WelcomeMotionPhase.finished => List<double>.filled(petalCount, 1),
    };
  }

  static List<double> _staggeredAmounts({
    required double progress,
    required List<int> order,
    required Duration petalDuration,
    required Duration stagger,
    required Curve curve,
    required bool gathering,
  }) {
    assert(order.length == petalCount);
    final totalDuration = petalDuration + stagger * (petalCount - 1);
    final elapsedUs = totalDuration.inMicroseconds * progress;
    final petalDurationUs = petalDuration.inMicroseconds;
    final amounts = List<double>.filled(petalCount, gathering ? 1 : 0);

    for (var position = 0; position < order.length; position++) {
      final localProgress =
          ((elapsedUs - stagger.inMicroseconds * position) / petalDurationUs)
              .clamp(0.0, 1.0);
      final eased = curve.transform(localProgress);
      amounts[order[position]] = gathering ? 1 - eased : eased;
    }
    return amounts;
  }
}
