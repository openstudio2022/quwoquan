import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/runtime/observability/generated/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/runtime/platform/video_native_playback_signals.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

/// 播放传输状态。页面只渲染该语义状态，不能自行从原生 controller 推导第二套状态。
enum VideoPlaybackTransport {
  initializing,
  ready,
  playing,
  paused,
  scrubbing,
  buffering,
  ended,
  failure,
}

/// 播放来源意图。用户暂停必须始终压过自动播放与生命周期恢复。
enum VideoPlaybackIntent {
  autoEligible,
  manualPlay,
  manualPause,
  interrupted,
  awaitingUserGesture,
}

/// 控制层的显示策略。
enum VideoPlaybackControlsVisibility { hidden, transient, pinned }

/// 暂停原因仅用于状态收敛、可观测和恢复判断，不直接展示给用户。
enum VideoPlaybackPauseReason {
  user,
  focusLost,
  offscreen,
  appLifecycle,
  audioInterruption,
  episodeChange,
  failure,
}

enum VideoSeekLifecyclePhase {
  requested,
  commandCompleted,
  commandTimedOut,
  commandCapacityExceeded,
  failed,
  settleTimedOut,
  settleUnsupported,
  superseded,
}

enum VideoSourceSwitchSeekOutcome {
  nativeSettled,
  positionReadbackSettled,
  nativeSettleTimedOut,
  settleUnsupported,
  commandTimedOut,
  commandCapacityExceeded,
  commandFailed,
  superseded,
}

@immutable
class VideoSourceSwitchSeekResult {
  const VideoSourceSwitchSeekResult({
    required this.outcome,
    required this.target,
    required this.elapsedMs,
    required this.evidenceCapability,
    this.observedPosition,
  });

  final VideoSourceSwitchSeekOutcome outcome;
  final Duration target;
  final Duration? observedPosition;
  final int elapsedMs;
  final VideoSeekSettleEvidenceCapability evidenceCapability;

  bool get isSettled =>
      outcome == VideoSourceSwitchSeekOutcome.nativeSettled ||
      outcome == VideoSourceSwitchSeekOutcome.positionReadbackSettled;

  bool get countsAsFailure =>
      outcome == VideoSourceSwitchSeekOutcome.nativeSettleTimedOut ||
      outcome == VideoSourceSwitchSeekOutcome.settleUnsupported ||
      outcome == VideoSourceSwitchSeekOutcome.commandTimedOut ||
      outcome == VideoSourceSwitchSeekOutcome.commandCapacityExceeded ||
      outcome == VideoSourceSwitchSeekOutcome.commandFailed;

  String get evidenceSource => switch (outcome) {
    VideoSourceSwitchSeekOutcome.nativeSettled =>
      AppTelemetryValueSeekEvidenceSource.sourceSwitchNativeSettled,
    VideoSourceSwitchSeekOutcome.positionReadbackSettled =>
      AppTelemetryValueSeekEvidenceSource
          .sourceSwitchPositionReadbackNativeUnsupported,
    VideoSourceSwitchSeekOutcome.nativeSettleTimedOut =>
      AppTelemetryValueSeekEvidenceSource.sourceSwitchNativeSettleTimeout,
    VideoSourceSwitchSeekOutcome.settleUnsupported =>
      AppTelemetryValueSeekEvidenceSource.sourceSwitchSettleUnsupported,
    VideoSourceSwitchSeekOutcome.commandTimedOut ||
    VideoSourceSwitchSeekOutcome.commandCapacityExceeded ||
    VideoSourceSwitchSeekOutcome.commandFailed =>
      AppTelemetryValueSeekEvidenceSource.sourceSwitchCommandFailed,
    VideoSourceSwitchSeekOutcome.superseded =>
      AppTelemetryValueSeekEvidenceSource.sourceSwitchSuperseded,
  };
}

typedef VideoNativeSignalObserver =
    FutureOr<void> Function(VideoNativePlaybackSignal signal);

/// seek 命令生命周期。
///
/// [hasNativeSettleEvidence] 仅在原生 surface 的帧证据确认后为 true；
/// command Future 完成不能伪装成原生画面 settle。
@immutable
class VideoSeekLifecycleEvent {
  const VideoSeekLifecycleEvent({
    required this.phase,
    required this.target,
    required this.generation,
    required this.elapsedMs,
    required this.hasNativeSettleEvidence,
  });

  final VideoSeekLifecyclePhase phase;
  final Duration target;
  final int generation;
  final int elapsedMs;
  final bool hasNativeSettleEvidence;
}

/// 一个原生播放 controller 生命周期内的匿名 QoE 汇总。
///
/// 该对象刻意不带内容、推荐或用户归因；这些字段属于行为链路，不得进入 Ops
/// 产品遥测。无法取得原生证据的平台保持 null，不伪造 TTFF 或渲染计数。
@immutable
class VideoPlaybackQoeSummary {
  const VideoPlaybackQoeSummary({
    required this.readyMs,
    required this.rebufferCount,
    required this.rebufferMs,
    required this.effectivePlaybackMs,
    required this.seekCount,
    required this.seekFailureCount,
    required this.seekCommandMaxMs,
    required this.seekSettleMaxMs,
    required this.seekEvidenceSource,
    required this.playbackMode,
    required this.result,
    this.ttffMs,
    this.droppedFrames,
    this.processedVideoFrames,
    this.audioUnderrunCount,
    this.rendererMode,
    this.decoderQueueMode,
    this.decoderFallbackEnabled,
    this.declaredDurationMs,
    this.observedDurationMs,
    this.durationMismatch,
    this.failReasonCode,
  });

  final int readyMs;
  final int rebufferCount;
  final int rebufferMs;
  final int effectivePlaybackMs;
  final int seekCount;
  final int seekFailureCount;
  final int seekCommandMaxMs;
  final int seekSettleMaxMs;
  final String seekEvidenceSource;
  final String playbackMode;
  final String result;
  final int? ttffMs;
  final int? droppedFrames;
  final int? processedVideoFrames;
  final int? audioUnderrunCount;
  final String? rendererMode;
  final String? decoderQueueMode;
  final bool? decoderFallbackEnabled;
  final int? declaredDurationMs;
  final int? observedDurationMs;
  final bool? durationMismatch;
  final String? failReasonCode;
}

/// 推荐行为链只消费该候选证据；seek、buffering、后台和离屏时间不会累计。
@immutable
class VideoEffectivePlaybackEvidence {
  const VideoEffectivePlaybackEvidence({
    required this.playbackSessionId,
    required this.effectivePlayMs,
    required this.consumedRatio,
    required this.totalUnits,
  });

  final String playbackSessionId;
  final int effectivePlayMs;
  final double consumedRatio;
  final int totalUnits;

  bool get qualifies => effectivePlayMs >= 5000 && totalUnits > 0;
}

/// 一个播放会话的唯一渲染输入。
@immutable
class VideoPlaybackSnapshot {
  const VideoPlaybackSnapshot({
    required this.transport,
    required this.intent,
    required this.controlsVisibility,
    required this.position,
    required this.duration,
    required this.isInitialized,
    required this.isPlaying,
    required this.isBuffering,
    required this.hasController,
    required this.generation,
    this.pauseReason,
    this.scrubTarget,
    this.verifiedDuration,
    this.runtimeFailure,
    this.lastSeekLifecycleEvent,
    this.lastSourceSwitchSeekResult,
  });

  final VideoPlaybackTransport transport;
  final VideoPlaybackIntent intent;
  final VideoPlaybackControlsVisibility controlsVisibility;
  final Duration position;
  final Duration duration;
  final bool isInitialized;
  final bool isPlaying;
  final bool isBuffering;
  final bool hasController;
  final int generation;
  final VideoPlaybackPauseReason? pauseReason;
  final Duration? scrubTarget;
  final Duration? verifiedDuration;
  final RuntimeFailure? runtimeFailure;
  final VideoSeekLifecycleEvent? lastSeekLifecycleEvent;
  final VideoSourceSwitchSeekResult? lastSourceSwitchSeekResult;

  bool get isScrubbing => transport == VideoPlaybackTransport.scrubbing;

  bool get isEnded => transport == VideoPlaybackTransport.ended;

  bool get canSeek => duration > Duration.zero && isInitialized;

  double get progress {
    if (!canSeek) {
      return 0;
    }
    return position.inMilliseconds / duration.inMilliseconds;
  }

  Duration get effectivePosition => scrubTarget ?? position;
}
