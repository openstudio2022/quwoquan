part of 'content_behavior_tracker.dart';

extension ContentBehaviorTrackerEffectivePlayback on ContentBehaviorTracker {
  /// 仅接收播放器状态机累计的实际播放候选；拖动位置比例不参与推荐。
  void trackEffectivePlayback(
    String contentId, {
    required String playbackSessionId,
    required int effectivePlayMs,
    required double consumedRatio,
    required int totalUnits,
    String? contentType,
    String? feedRequestId,
    ReferralSource? referralSource,
  }) {
    final normalizedPlaybackSessionId = playbackSessionId.trim();
    if (normalizedPlaybackSessionId.isEmpty ||
        effectivePlayMs < 5000 ||
        totalUnits <= 0) {
      return;
    }
    _add(
      BehaviorEvent(
        contentId: contentId,
        action: BehaviorEventType.effectivePlay,
        state: 'foreground_visible_playing',
        clientEventId: 'effective-play:$contentId:$normalizedPlaybackSessionId',
        playbackSessionId: normalizedPlaybackSessionId,
        contentType: contentType,
        effectivePlayMs: effectivePlayMs,
        consumedRatio: consumedRatio.clamp(0.0, 1.0),
        totalUnits: totalUnits,
        feedRequestId: feedRequestId,
        referralSource: referralSource,
      ),
    );
  }
}
