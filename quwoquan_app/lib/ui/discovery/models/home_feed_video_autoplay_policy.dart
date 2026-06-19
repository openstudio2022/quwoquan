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
