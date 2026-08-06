import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';

/// ContentBehaviorFact 对外暴露的行为采集端口。
///
/// 页面与其他对象只依赖此纯 Dart seam；缓冲、去重、定时 flush 与 Remote
/// 组合均由本对象内部实现并在 `runtime/di` 装配。
abstract interface class ContentBehaviorTrackerPort {
  void trackImpression(
    String contentId, {
    String? contentType,
    List<String>? tags,
    String? feedRequestId,
    int? position,
    ReferralSource? referralSource,
    String? channelId,
    String? policyDigest,
    String? recallPath,
    String? supplySource,
    String? intersectionId,
    String? intersectionDimension,
    String? intersectionSourceRef,
    List<String>? intersectionTagRefs,
    String? intersectionClass,
    String? intersectionEvidenceId,
  });

  void trackVisible(
    String contentId, {
    String? contentType,
    List<String>? tags,
    String? feedRequestId,
    int? position,
    ReferralSource? referralSource,
    String? channelId,
    String? policyDigest,
    String? recallPath,
    String? supplySource,
  });

  void trackQualifiedImpression(
    String contentId, {
    required double visibleFraction,
    required Duration visibleDuration,
    String? contentType,
    List<String>? tags,
    String? feedRequestId,
    int? position,
    ReferralSource? referralSource,
    String? channelId,
    String? policyDigest,
    String? recallPath,
    String? supplySource,
    String? intersectionId,
    String? intersectionDimension,
    String? intersectionSourceRef,
    List<String>? intersectionTagRefs,
    String? intersectionClass,
    String? intersectionEvidenceId,
  });

  void trackDwell(
    String contentId, {
    required double durationSeconds,
    String? contentType,
    List<String>? tags,
    String? feedRequestId,
    int? position,
    ReferralSource? referralSource,
    String? channelId,
    String? policyDigest,
    String? recallPath,
    String? supplySource,
  });

  void trackClick(
    String contentId, {
    String? contentType,
    List<String>? tags,
    String? feedRequestId,
    int? position,
    ReferralSource? referralSource,
    String? channelId,
    String? policyDigest,
    String? recallPath,
    String? supplySource,
    String? intersectionId,
    String? intersectionDimension,
    String? intersectionSourceRef,
    List<String>? intersectionTagRefs,
    String? intersectionClass,
    String? intersectionEvidenceId,
  });

  void trackTagClick(
    String contentId, {
    String? contentType,
    String? authorId,
    List<String>? tags,
    String? feedRequestId,
    int? position,
    ReferralSource? referralSource,
    String? channelId,
    String? policyDigest,
    String? recallPath,
    String? supplySource,
    String? intersectionId,
    String? intersectionDimension,
    String? intersectionSourceRef,
    List<String>? intersectionTagRefs,
    String? intersectionClass,
    String? intersectionEvidenceId,
  });

  void trackIntersectionExpand({
    String? contentId,
    String? intersectionId,
    String? intersectionDimension,
    String? intersectionClass,
    String? intersectionSourceRef,
    String? surfaceId,
    ReferralSource? referralSource,
  });

  void trackDislike(
    String contentId, {
    String? contentType,
    List<String>? tags,
    String? authorId,
    String? feedRequestId,
    int? position,
    ReferralSource? referralSource,
    String? channelId,
    String? policyDigest,
    String? recallPath,
    String? supplySource,
  });

  void trackUndoDislike(
    String contentId, {
    String? contentType,
    String? authorId,
    String? feedRequestId,
    int? position,
    ReferralSource? referralSource,
    String? channelId,
    String? policyDigest,
    String? recallPath,
    String? supplySource,
  });

  void trackHideAuthor(
    String contentId, {
    required String authorId,
    String? contentType,
    List<String>? tags,
    String? feedRequestId,
    int? position,
    ReferralSource? referralSource,
    String? channelId,
    String? policyDigest,
    String? recallPath,
    String? supplySource,
  });

  void trackHideContentType(
    String contentId, {
    required String contentType,
    List<String>? tags,
    String? authorId,
    String? feedRequestId,
    int? position,
    ReferralSource? referralSource,
    String? channelId,
    String? policyDigest,
    String? recallPath,
    String? supplySource,
  });

  void trackShare(
    String contentId, {
    String? contentType,
    List<String>? tags,
    String? feedRequestId,
    int? position,
    ReferralSource? referralSource,
    String? channelId,
    String? policyDigest,
    String? recallPath,
    String? supplySource,
  });

  void trackSkip(
    String contentId, {
    double? dwellSeconds,
    String? contentType,
    List<String>? tags,
    String? feedRequestId,
    int? position,
    ReferralSource? referralSource,
    String? channelId,
    String? policyDigest,
    String? recallPath,
    String? supplySource,
  });

  void trackFollow(
    String authorId, {
    String? feedRequestId,
    ReferralSource? referralSource,
    String? channelId,
    String? policyDigest,
    String? intersectionDimension,
    String? intersectionSourceRef,
    List<String>? intersectionTagRefs,
  });

  void trackJoinCircle(
    String circleId, {
    String? feedRequestId,
    ReferralSource? referralSource,
    String? channelId,
    String? policyDigest,
    String? intersectionDimension,
    String? intersectionSourceRef,
    List<String>? intersectionTagRefs,
  });

  void trackAddContact(
    String authorId, {
    String? feedRequestId,
    ReferralSource? referralSource,
    String? channelId,
    String? policyDigest,
    String? intersectionDimension,
    String? intersectionSourceRef,
    List<String>? intersectionTagRefs,
  });

  void trackAssistantInterest(List<String> tagRefs);

  void trackIntersectionFeedback(
    String subjectId, {
    required String feedbackKind,
    String? intersectionId,
    String? intersectionDimension,
    String? intersectionClass,
    String? intersectionSourceRef,
  });

  void trackWishlistAdd(
    String objectId, {
    required String objectKind,
    String? displayName,
    String? sourceSurface,
    String? feedRequestId,
    int? position,
    ReferralSource? referralSource,
    String? channelId,
    String? policyDigest,
  });

  void trackWishlistRemove(
    String objectId, {
    required String objectKind,
    String? sourceSurface,
    String? feedRequestId,
    int? position,
    ReferralSource? referralSource,
    String? channelId,
    String? policyDigest,
  });

  void trackWorksImagePageflipMotion(
    String contentId, {
    required String direction,
    required String motionProfile,
    required int settleMs,
    required bool reducedMotion,
    required bool committed,
    String? contentType,
    String? feedRequestId,
    int? position,
    ReferralSource? referralSource,
    String? channelId,
    String? policyDigest,
    String? recallPath,
    String? supplySource,
  });

  void trackEffectivePlayback(
    String contentId, {
    required String playbackSessionId,
    required int effectivePlayMs,
    required double consumedRatio,
    required int totalUnits,
    String? contentType,
    String? feedRequestId,
    ReferralSource? referralSource,
  });

  Future<void> flush();
}
