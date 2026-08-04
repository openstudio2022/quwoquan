// ignore_for_file: prefer_initializing_formals

import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart'
    show BehaviorEventType, BehaviorEvent, BehaviorReporter, ReferralSource;
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show ContentType;

export 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show ContentType;

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

  /// Last reported play_progress threshold to avoid duplicate reports.
  double lastReportedPlayThreshold = 0.0;
  bool effectivePlaybackReported = false;
}

/// Unified content engagement tracker that handles all content types with
/// differentiated depth calculation and referral source attribution.
class ContentEngagementTracker {
  ContentEngagementTracker({required BehaviorReporter reporter})
    : _reporter = reporter;

  final BehaviorReporter _reporter;
  final Map<String, _ContentSession> _activeSessions = {};
  final List<Future<void>> _pendingReports = [];

  void _fireAndTrack(Future<void> future) {
    _pendingReports.add(future);
    future.whenComplete(() => _pendingReports.remove(future));
  }

  /// Flush all pending report futures. Call before teardown.
  Future<void> dispose() async {
    for (final id in _activeSessions.keys.toList()) {
      await trackContentExit(id);
    }
    await Future.wait(List<Future<void>>.of(_pendingReports));
  }

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

    _fireAndTrack(
      _reporter.reportEvents(
        events: [
          BehaviorEvent(
            contentId: contentId,
            action: BehaviorEventType.impression,
            state: 'visible',
            clientEventId: _clientEventId(
              action: BehaviorEventType.impression,
              contentId: contentId,
              feedRequestId: feedRequestId,
            ),
            contentType: contentType.wireName,
            tags: tags,
            feedRequestId: feedRequestId,
            position: position,
            authorId: authorId,
            referralSource: referralSource,
            entityRefs: entityRefs,
          ),
        ],
      ),
    );
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
  Future<void> trackContentExit(
    String contentId, {
    bool emitDwell = true,
  }) async {
    final session = _activeSessions.remove(contentId);
    if (session == null) return;

    final dwellMs = DateTime.now().difference(session.enterTime).inMilliseconds;
    final dwellSeconds = dwellMs / 1000.0;

    if (dwellSeconds < 1.0) return;

    final depth = _computeEngagementDepth(session, dwellMs);
    final ratio = _computeConsumedRatio(session);
    final totalUnits = _computeTotalUnits(session);

    final ct = session.contentType.wireName;
    final events = <BehaviorEvent>[
      if (emitDwell)
        BehaviorEvent(
          contentId: contentId,
          action: BehaviorEventType.dwell,
          state: 'dwell',
          clientEventId: _clientEventId(
            action: BehaviorEventType.dwell,
            contentId: contentId,
            feedRequestId: session.feedRequestId,
          ),
          contentType: ct,
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
        action: BehaviorEventType.contentDepth,
        state: 'interaction',
        clientEventId: _clientEventId(
          action: BehaviorEventType.contentDepth,
          contentId: contentId,
          feedRequestId: session.feedRequestId,
        ),
        contentType: ct,
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

    await _reporter.reportEvents(events: events);
  }

  /// Track author profile view.
  void trackAuthorProfileView(String authorId, {required ReferralSource from}) {
    _fireAndTrack(
      _reporter.reportEvents(
        events: [
          BehaviorEvent(
            contentId: authorId,
            action: BehaviorEventType.authorView,
            state: 'interaction',
            clientEventId: _clientEventId(
              action: BehaviorEventType.authorView,
              contentId: authorId,
            ),
            referralSource: from,
            authorId: authorId,
          ),
        ],
      ),
    );
  }

  /// Track tag click within content.
  void trackTagClick(
    String tagRef, {
    required String fromContentId,
    ReferralSource? referralSource,
    String? feedRequestId,
  }) {
    final session = _activeSessions[fromContentId];
    _fireAndTrack(
      _reporter.reportEvents(
        events: [
          BehaviorEvent(
            contentId: fromContentId,
            action: BehaviorEventType.tagClick,
            state: 'interaction',
            clientEventId: _clientEventId(
              action: BehaviorEventType.tagClick,
              contentId: fromContentId,
              feedRequestId: feedRequestId ?? session?.feedRequestId,
            ),
            tags: [tagRef],
            referralSource:
                referralSource ??
                session?.referralSource ??
                ReferralSource.organicFeed,
            feedRequestId: feedRequestId ?? session?.feedRequestId,
            authorId: session?.authorId,
          ),
        ],
      ),
    );
  }

  /// Track entity page navigation.
  void trackEntityPageView(String entityId, {required ReferralSource from}) {
    _fireAndTrack(
      _reporter.reportEvents(
        events: [
          BehaviorEvent(
            contentId: entityId,
            action: BehaviorEventType.entityPageView,
            state: 'interaction',
            clientEventId: _clientEventId(
              action: BehaviorEventType.entityPageView,
              contentId: entityId,
            ),
            referralSource: from,
            entityRefs: [entityId],
          ),
        ],
      ),
    );
  }

  /// Track video play progress (called periodically or on pause/seek).
  /// Throttled to fire only when crossing 0.25/0.50/0.75/0.90/1.0 thresholds.
  void trackPlayProgress(
    String contentId, {
    required int positionMs,
    required int totalDurationMs,
  }) {
    trackContentProgress(contentId, playPositionMs: positionMs);

    if (totalDurationMs <= 0) return;
    final ratio = positionMs / totalDurationMs.toDouble();

    const thresholds = [0.25, 0.50, 0.75, 0.90, 1.0];
    final session = _activeSessions[contentId];
    if (session == null) return;

    double currentThreshold = 0.0;
    for (final t in thresholds) {
      if (ratio >= t) currentThreshold = t;
    }
    if (currentThreshold <= 0 ||
        currentThreshold <= session.lastReportedPlayThreshold) {
      return;
    }
    session.lastReportedPlayThreshold = currentThreshold;

    _fireAndTrack(
      _reporter.reportEvents(
        events: [
          BehaviorEvent(
            contentId: contentId,
            action: BehaviorEventType.playProgress,
            state: 'interaction',
            clientEventId: _clientEventId(
              action: BehaviorEventType.playProgress,
              contentId: contentId,
              feedRequestId: session.feedRequestId,
              suffix: currentThreshold.toStringAsFixed(2),
            ),
            contentType: session.contentType.wireName,
            consumedRatio: ratio,
            totalUnits: (totalDurationMs / 1000).round(),
            referralSource: session.referralSource,
            feedRequestId: session.feedRequestId,
            authorId: session.authorId,
          ),
        ],
      ),
    );
  }

  void trackEffectivePlayback(
    String contentId, {
    required String playbackSessionId,
    required int effectivePlayMs,
    required double consumedRatio,
    required int totalUnits,
  }) {
    final session = _activeSessions[contentId];
    if (session == null ||
        session.contentType != ContentType.video ||
        session.effectivePlaybackReported ||
        playbackSessionId.trim().isEmpty ||
        effectivePlayMs < 5000 ||
        totalUnits <= 0) {
      return;
    }
    session.effectivePlaybackReported = true;
    _fireAndTrack(
      _reporter.reportEvents(
        events: [
          BehaviorEvent(
            contentId: contentId,
            action: BehaviorEventType.effectivePlay,
            state: 'foreground_visible_playing',
            clientEventId:
                'eng:effective_play:$contentId:${playbackSessionId.trim()}',
            playbackSessionId: playbackSessionId.trim(),
            contentType: session.contentType.wireName,
            effectivePlayMs: effectivePlayMs,
            consumedRatio: consumedRatio.clamp(0.0, 1.0),
            totalUnits: totalUnits,
            referralSource: session.referralSource,
            feedRequestId: session.feedRequestId,
            authorId: session.authorId,
          ),
        ],
      ),
    );
  }

  String _clientEventId({
    required BehaviorEventType action,
    required String contentId,
    String? feedRequestId,
    String? suffix,
  }) {
    final now = DateTime.now().toUtc().microsecondsSinceEpoch;
    final feed = feedRequestId == null || feedRequestId.trim().isEmpty
        ? now.toString()
        : feedRequestId.trim();
    final safeSuffix = suffix == null || suffix.isEmpty
        ? now.toString()
        : suffix;
    return 'eng:${action.wireName}:$contentId:$feed:$safeSuffix';
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
        if (session.maxScrollDepth > 0) return session.maxScrollDepth;
        final total = session.totalPages ?? 0;
        if (total <= 2) return -1;
        if (total <= 0 || session.maxPageReached <= 0) return 0;
        return session.maxPageReached / total;
      case ContentType.image:
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
      case ContentType.micro:
        return -1;
    }
  }

  int _computeTotalUnits(_ContentSession session) {
    switch (session.contentType) {
      case ContentType.article:
        return session.totalPages ?? 0;
      case ContentType.image:
        return session.totalImages ?? 0;
      case ContentType.video:
        return ((session.totalDurationMs ?? 0) / 1000).round();
      case ContentType.micro:
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
      case ContentType.image:
        if (dwellMs < 3000) return 0;
        if (dwellMs < 8000) return 1;
        if (dwellMs < 15000) return 2;
        return 3;
      case ContentType.micro:
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
