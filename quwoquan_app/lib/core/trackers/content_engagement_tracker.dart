import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';

/// Content type for engagement depth calculation.
enum ContentType { article, photo, video, moment }

/// Tracks in-progress content engagement and computes depth on exit.
class _ContentSession {
  _ContentSession({
    required this.contentId,
    required this.contentType,
    required this.referralSource,
    this.totalPages,
    this.totalImages,
    this.totalDurationMs,
    this.authorId,
    this.tags,
    this.entityRefs,
    this.feedRequestId,
    this.position,
  });

  final String contentId;
  final ContentType contentType;
  final ReferralSource referralSource;
  final int? totalPages;
  final int? totalImages;
  final int? totalDurationMs;
  final String? authorId;
  final List<String>? tags;
  final List<String>? entityRefs;
  final String? feedRequestId;
  final int? position;

  final DateTime enterTime = DateTime.now();
  int maxPageReached = 0;
  int maxImageReached = 0;
  int lastPlayPositionMs = 0;
  double maxScrollDepth = 0.0;
}

/// Unified content engagement tracker that handles all content types with
/// differentiated depth calculation and referral source attribution.
class ContentEngagementTracker {
  ContentEngagementTracker({required BehaviorRepository repository})
      : _repository = repository;

  final BehaviorRepository _repository;
  final Map<String, _ContentSession> _activeSessions = {};

  /// Called when user opens/enters a content item.
  void trackContentEnter(
    String contentId, {
    required ContentType contentType,
    required ReferralSource referralSource,
    int? totalPages,
    int? totalImages,
    int? totalDurationMs,
    String? authorId,
    List<String>? tags,
    List<String>? entityRefs,
    String? feedRequestId,
    int? position,
  }) {
    _activeSessions[contentId] = _ContentSession(
      contentId: contentId,
      contentType: contentType,
      referralSource: referralSource,
      totalPages: totalPages,
      totalImages: totalImages,
      totalDurationMs: totalDurationMs,
      authorId: authorId,
      tags: tags,
      entityRefs: entityRefs,
      feedRequestId: feedRequestId,
      position: position,
    );

    _repository.reportEvents(events: [
      BehaviorEvent(
        contentId: contentId,
        action: 'impression',
        tags: tags,
        feedRequestId: feedRequestId,
        position: position,
        authorId: authorId,
        referralSource: referralSource,
        entityRefs: entityRefs,
      ),
    ]);
  }

  /// Called to update progress (page flip, image swipe, video progress).
  void trackContentProgress(
    String contentId, {
    int? currentPage,
    int? currentImageIndex,
    int? playPositionMs,
    double? scrollDepth,
  }) {
    final session = _activeSessions[contentId];
    if (session == null) return;

    if (currentPage != null && currentPage > session.maxPageReached) {
      session.maxPageReached = currentPage;
    }
    if (currentImageIndex != null &&
        currentImageIndex > session.maxImageReached) {
      session.maxImageReached = currentImageIndex;
    }
    if (playPositionMs != null && playPositionMs > session.lastPlayPositionMs) {
      session.lastPlayPositionMs = playPositionMs;
    }
    if (scrollDepth != null && scrollDepth > session.maxScrollDepth) {
      session.maxScrollDepth = scrollDepth;
    }
  }

  /// Called when user exits/leaves a content item. Computes final depth.
  void trackContentExit(String contentId) {
    final session = _activeSessions.remove(contentId);
    if (session == null) return;

    final dwellMs =
        DateTime.now().difference(session.enterTime).inMilliseconds;
    final dwellSeconds = dwellMs / 1000.0;

    if (dwellSeconds < 1.0) return;

    final depth = _computeEngagementDepth(session, dwellMs);
    final ratio = _computeConsumedRatio(session);
    final totalUnits = _computeTotalUnits(session);

    final events = <BehaviorEvent>[
      BehaviorEvent(
        contentId: contentId,
        action: 'dwell',
        duration: dwellSeconds,
        tags: session.tags,
        feedRequestId: session.feedRequestId,
        position: session.position,
        authorId: session.authorId,
        referralSource: session.referralSource,
        engagementDepth: depth,
        consumedRatio: ratio,
        totalUnits: totalUnits,
        entityRefs: session.entityRefs,
      ),
      BehaviorEvent(
        contentId: contentId,
        action: 'content_depth',
        tags: session.tags,
        feedRequestId: session.feedRequestId,
        authorId: session.authorId,
        referralSource: session.referralSource,
        engagementDepth: depth,
        consumedRatio: ratio,
        totalUnits: totalUnits,
        entityRefs: session.entityRefs,
      ),
    ];

    _repository.reportEvents(events: events);
  }

  /// Track author profile view.
  void trackAuthorProfileView(String authorId, {required ReferralSource from}) {
    _repository.reportEvents(events: [
      BehaviorEvent(
        contentId: authorId,
        action: 'author_view',
        referralSource: from,
        authorId: authorId,
      ),
    ]);
  }

  /// Track tag click within content.
  void trackTagClick(String tagRef, {required String fromContentId}) {
    _repository.reportEvents(events: [
      BehaviorEvent(
        contentId: fromContentId,
        action: 'tag_click',
        tags: [tagRef],
      ),
    ]);
  }

  /// Track entity page navigation.
  void trackEntityPageView(String entityId, {required ReferralSource from}) {
    _repository.reportEvents(events: [
      BehaviorEvent(
        contentId: entityId,
        action: 'author_view',
        referralSource: from,
        entityRefs: [entityId],
      ),
    ]);
  }

  /// Track video play progress (called periodically or on pause/seek).
  void trackPlayProgress(
    String contentId, {
    required int positionMs,
    required int totalDurationMs,
  }) {
    trackContentProgress(contentId, playPositionMs: positionMs);

    if (totalDurationMs <= 0) return;
    final ratio = positionMs / totalDurationMs;
    if (ratio < 0.25) return; // only report at meaningful thresholds

    _repository.reportEvents(events: [
      BehaviorEvent(
        contentId: contentId,
        action: 'play_progress',
        consumedRatio: positionMs / totalDurationMs.toDouble(),
        totalUnits: (totalDurationMs / 1000).round(),
      ),
    ]);
  }

  /// Compute engagement depth level (0-4).
  int _computeEngagementDepth(_ContentSession session, int dwellMs) {
    final ratio = _computeConsumedRatio(session);
    if (ratio < 0) {
      return _depthFromDwell(dwellMs, session.contentType);
    }
    return _ratioToDepthLevel(ratio);
  }

  double _computeConsumedRatio(_ContentSession session) {
    switch (session.contentType) {
      case ContentType.article:
        final total = session.totalPages ?? 0;
        if (total <= 2) return -1;
        if (total <= 0 || session.maxPageReached <= 0) return 0;
        return session.maxPageReached / total;
      case ContentType.photo:
        final total = session.totalImages ?? 0;
        if (total <= 2) return -1;
        if (total <= 0 || session.maxImageReached <= 0) return 0;
        return session.maxImageReached / total;
      case ContentType.video:
        final total = session.totalDurationMs ?? 0;
        if (total > 0 && total < 10000) {
          if (session.lastPlayPositionMs <= 0) return 0;
          return (session.lastPlayPositionMs / total) * 1.3;
        }
        if (total <= 0 || session.lastPlayPositionMs <= 0) return 0;
        return session.lastPlayPositionMs / total;
      case ContentType.moment:
        return -1;
    }
  }

  int _computeTotalUnits(_ContentSession session) {
    switch (session.contentType) {
      case ContentType.article:
        return session.totalPages ?? 0;
      case ContentType.photo:
        return session.totalImages ?? 0;
      case ContentType.video:
        return ((session.totalDurationMs ?? 0) / 1000).round();
      case ContentType.moment:
        return 1;
    }
  }

  int _depthFromDwell(int dwellMs, ContentType type) {
    switch (type) {
      case ContentType.article:
        if (dwellMs < 5000) return 0;
        if (dwellMs < 15000) return 1;
        if (dwellMs < 30000) return 2;
        return 3;
      case ContentType.photo:
        if (dwellMs < 3000) return 0;
        if (dwellMs < 8000) return 1;
        if (dwellMs < 15000) return 2;
        return 3;
      case ContentType.moment:
        if (dwellMs < 2000) return 0;
        if (dwellMs < 5000) return 1;
        if (dwellMs < 10000) return 2;
        if (dwellMs < 20000) return 3;
        return 4;
      case ContentType.video:
        if (dwellMs < 3000) return 0;
        if (dwellMs < 10000) return 1;
        if (dwellMs < 30000) return 2;
        if (dwellMs < 60000) return 3;
        return 4;
    }
  }

  int _ratioToDepthLevel(double ratio) {
    if (ratio < 0.1) return 0;
    if (ratio < 0.3) return 1;
    if (ratio < 0.6) return 2;
    if (ratio < 0.9) return 3;
    return 4;
  }
}
