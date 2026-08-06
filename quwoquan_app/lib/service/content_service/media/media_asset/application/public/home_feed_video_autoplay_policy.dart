/// 首页视频自动播放的跨对象公开策略输入。
class HomeFeedVideoAutoPlayInput {
  const HomeFeedVideoAutoPlayInput({
    required this.hasPlayableSource,
    required this.visibleFraction,
    required this.stableVisibleDuration,
    required this.scrollVelocityPxPerSecond,
    required this.isUserDragging,
    required this.isScrolling,
    required this.timeSinceScrollEnd,
    required this.timeSinceHighVelocity,
  });

  final bool hasPlayableSource;
  final double visibleFraction;
  final Duration stableVisibleDuration;
  final double scrollVelocityPxPerSecond;
  final bool isUserDragging;
  final bool isScrolling;
  final Duration timeSinceScrollEnd;
  final Duration timeSinceHighVelocity;
}

class HomeFeedVideoFastScrollSuppressionInput {
  const HomeFeedVideoFastScrollSuppressionInput({
    required this.hasPlayableSource,
    required this.visibleFraction,
    required this.prewarmStableVisibleDuration,
    required this.scrollVelocityPxPerSecond,
    required this.timeSinceHighVelocity,
  });

  final bool hasPlayableSource;
  final double visibleFraction;
  final Duration prewarmStableVisibleDuration;
  final double scrollVelocityPxPerSecond;
  final Duration timeSinceHighVelocity;
}

const double homeFeedVideoAutoPlayMinVisibleFraction = 0.72;
const double homeFeedVideoPrewarmMinVisibleFraction = 0.52;
const double homeFeedVideoRetainInitializedMinVisibleFraction = 0.34;
const double homeFeedVideoAutoPlayMaxVelocityPxPerSecond = 720;
const double homeFeedVideoFastScrollVelocityPxPerSecond = 1100;
const Duration homeFeedVideoAutoPlayMinStableVisibleDuration = Duration(
  milliseconds: 160,
);
const Duration homeFeedVideoAutoPlayScrollEndDebounce = Duration(
  milliseconds: 100,
);
const Duration homeFeedVideoFastScrollCooldown = Duration(milliseconds: 420);

bool shouldAutoPlayHomeFeedVideo(HomeFeedVideoAutoPlayInput input) {
  if (!input.hasPlayableSource) {
    return false;
  }
  if (input.visibleFraction < homeFeedVideoAutoPlayMinVisibleFraction) {
    return false;
  }
  if (input.stableVisibleDuration <
      homeFeedVideoAutoPlayMinStableVisibleDuration) {
    return false;
  }
  if (input.isUserDragging || input.isScrolling) {
    return false;
  }
  if (input.timeSinceScrollEnd < homeFeedVideoAutoPlayScrollEndDebounce) {
    return false;
  }
  if (input.timeSinceHighVelocity < homeFeedVideoFastScrollCooldown) {
    return false;
  }
  return input.scrollVelocityPxPerSecond.abs() <=
      homeFeedVideoAutoPlayMaxVelocityPxPerSecond;
}

bool shouldSuppressHomeFeedVideoFastScroll(
  HomeFeedVideoFastScrollSuppressionInput input,
) {
  if (!input.hasPlayableSource) {
    return false;
  }
  if (input.visibleFraction < homeFeedVideoPrewarmMinVisibleFraction) {
    return false;
  }
  if (input.prewarmStableVisibleDuration <
      homeFeedVideoAutoPlayMinStableVisibleDuration) {
    return false;
  }
  return input.timeSinceHighVelocity < homeFeedVideoFastScrollCooldown ||
      input.scrollVelocityPxPerSecond.abs() >
          homeFeedVideoFastScrollVelocityPxPerSecond;
}

Map<String, Object?> homeFeedVideoFastScrollSuppressedTelemetryAttributes({
  required String videoId,
  required double visibleFraction,
  required double velocityPxPerSecond,
  required Duration cooldownRemaining,
}) {
  return <String, Object?>{
    'videoId': videoId,
    'visibleFraction': visibleFraction,
    'velocityPxPerSecond': velocityPxPerSecond,
    'cooldownRemainingMs': cooldownRemaining.isNegative
        ? 0
        : cooldownRemaining.inMilliseconds,
  };
}
