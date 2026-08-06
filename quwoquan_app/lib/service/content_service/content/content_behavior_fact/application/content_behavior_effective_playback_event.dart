import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show BehaviorEventType;

/// 将播放器状态机证据归一为唯一 effective-play 事件。
///
/// 无效候选返回 `null`，避免把拖动位置或不足阈值的播放误记为推荐信号。
BehaviorEvent? buildEffectivePlaybackBehaviorEvent(
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
    return null;
  }
  return BehaviorEvent(
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
  );
}
