import 'dart:async';
import 'dart:math' show max;
import 'dart:ui' show FontFeature, ImageFilter;
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Theme;
import 'package:flutter/rendering.dart'
    show RenderBox, RenderObject, RenderParagraph;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter/services.dart';
import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/assistant/assistant_cloud_api_wire.g.dart'
    show AssistantIntersectionEvidenceRef;
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/core/errors/runtime_error_display.dart'
    as runtime_error_display;
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/source_attribution_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/work_browser_item_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/work_browser_media_item_dto.g.dart';
import 'package:quwoquan_app/application/content/media/video_preview_track_query.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_target.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_text_span.g.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_statement_synthesizer.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository_contract.dart'
    show contentPostDeleteIdempotencyKey;
import 'package:quwoquan_app/components/media/image/book/image_book_canvas.dart';
import 'package:quwoquan_app/components/media/shared/gesture/immersive_gesture_intent_controller.dart';
import 'package:quwoquan_app/components/media/shared/pageflip/media_page_flip_book.dart';
import 'package:quwoquan_app/components/object_page/object_intersection_provider.dart';
import 'package:quwoquan_app/components/object_page/intersection_target_navigator.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/core/widgets/app_modal_presenter.dart';
import 'package:quwoquan_app/ui/content/comments/widgets/immersive_comment_split_sheet.dart';
import 'package:quwoquan_app/components/media/shared/toolbar/immersive_engagement_bar.dart';
import 'package:quwoquan_app/components/media/shared/toolbar/immersive_intersection_statement.dart';
import 'package:quwoquan_app/components/media/shared/toolbar/media_viewer_toolbar.dart';
import 'package:quwoquan_app/components/media/shared/viewer/immersive_viewer_layout.dart';
import 'package:quwoquan_app/components/media/shared/viewer/media_caption_widgets.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/core/widgets/app_modal_surface.dart';
import 'package:quwoquan_app/core/widgets/app_action_sheet.dart';
import 'package:quwoquan_app/components/settings_conversation/more_actions_popup/configs/media_post_config.dart';
import 'package:quwoquan_app/components/settings_conversation/more_actions_popup/more_action_popup.dart';
import 'package:quwoquan_app/components/navigation/tab_swipe_switch_region.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/constants/discovery_feed_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/models/assistant_open_context.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart'
    show ReferralSource;
import 'package:quwoquan_app/core/auth/auth_continuation.dart';
import 'package:quwoquan_app/core/auth/auth_gate.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart'
    show AuthSessionState, authSessionControllerProvider;
import 'package:quwoquan_app/core/media/content_media_url.dart';
import 'package:quwoquan_app/core/media/media_delivery_reference.dart';
import 'package:quwoquan_app/core/di/video_preview_track_dependencies.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/providers/feed_session_provider.dart';
import 'package:quwoquan_app/core/trackers/article_reader_observability.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/core/trackers/content_engagement_tracker.dart'
    show ContentEngagementTracker, ContentType;
import 'package:quwoquan_app/core/trackers/feed_performance_observability.dart';
import 'package:quwoquan_app/core/trackers/page_lifecycle_observability.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';
import 'package:quwoquan_app/core/widgets/app_request_feedback.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/core/utils/content_keyword_suggester.dart';
import 'package:quwoquan_app/core/widgets/blocked_keyword_confirmation_sheet.dart';
import 'package:quwoquan_app/core/widgets/content_report_reason_sheet.dart';
import 'package:quwoquan_app/components/media/video/player/video_playback_session.dart';
import 'package:quwoquan_app/components/media/video/player/video_playback_center_glyph.dart';
import 'package:quwoquan_app/components/media/video/player/video_playback_timeline.dart';
import 'package:quwoquan_app/components/media/video/player/video_player_widget.dart';
import 'package:quwoquan_app/components/media/video/player/video_timeline_preview.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart'
    show ActivePersonaContextViewData;
import 'package:quwoquan_app/ui/content/share/content_share_actions.dart';
import 'package:quwoquan_app/ui/content/share/content_share_sheet.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view_mapper.dart';
import 'package:quwoquan_app/ui/content/share/content_share_template.dart';
import 'package:quwoquan_app/ui/content/models/article_detail_view.dart';
import 'package:quwoquan_app/ui/content/models/article_document_models.dart';
import 'package:quwoquan_app/ui/content/models/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/article_reader/hosts/article_reader_host_adapter.dart';
import 'package:quwoquan_app/ui/content/article_reader/hosts/immersive_browser_reader_adapter.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/host/article_read_only_book_deck.dart'
    show ArticleReadOnlyBookDeckPresentationStyle;
import 'package:quwoquan_app/ui/content/article_reader/pageflip/host/article_reader_flip_host.dart';
import 'package:quwoquan_app/ui/content/services/post_view_projection.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view.dart';
import 'package:quwoquan_app/components/content/content_time_label.dart';
import 'package:quwoquan_app/ui/discovery/services/media_viewer_interaction_bridge.dart';
import 'package:quwoquan_app/ui/content/widgets/article_paged_canvas.dart';
import 'package:quwoquan_app/ui/discovery/providers/discovery_feed_provider.dart';
import 'package:quwoquan_app/ui/discovery/models/home_feed_video_autoplay_policy.dart';
import 'package:quwoquan_app/ui/discovery/widgets/works_immersive_viewer_observability.dart';
import 'package:quwoquan_app/ui/discovery/widgets/works_immersive_viewer_paging.dart';
part 'works_immersive_viewer_controls.dart';
part 'works_immersive_viewer_canvas.dart';
part 'works_immersive_viewer_engagement_actions.dart';
part 'works_immersive_viewer_intersection_actions.dart';
part 'works_immersive_viewer_social_actions.dart';
part 'works_immersive_viewer_video_chrome.dart';
part 'works_immersive_viewer_lifecycle.dart';
part 'works_immersive_viewer_presentation.dart';
part 'works_immersive_viewer_build.dart';

class _WorksTrackingAttribution {
  const _WorksTrackingAttribution({
    required this.referralSource,
    required this.feedRequestId,
    required this.position,
    required this.channelId,
    required this.rankingVersion,
    required this.reasonVersion,
  });

  final ReferralSource referralSource;
  final String? feedRequestId;
  final int position;
  final String channelId;
  final String? rankingVersion;
  final String? reasonVersion;
}

class WorksImmersiveViewer extends ConsumerStatefulWidget {
  const WorksImmersiveViewer({
    super.key,
    required this.showWorksToolbar,
    required this.onUserTap,
    required this.onAssistantTap,
    this.onTapBack,
    this.onSwitchToFollowing,
    this.onSwitchToCircles,
    this.onSwitchToMoment, // Deprecated/Fallback
    this.onRevealSystemNav,
    this.onHideSystemNav,
    this.showTopNavigation = true,
    this.externalPosts,
    this.externalPostViews,
    this.initialPostIndex = 0,
    this.initialImageIndex = 0,
    this.source = 'featured',
    this.referralSource = ReferralSource.organicFeed,
    this.feedRequestId,
    this.initialFeedPosition,
    this.rawPostsById = const <String, MediaViewerPostWireRow>{},
    this.initialInteractionSnapshot = const MediaViewerInteractionSnapshot(),
    this.initialCommentContext = const MediaViewerCommentContext(),
    this.onDismissed,
    this.onPostIndexChanged,
    this.topChromeSafeInset = 0,
  });

  final bool showWorksToolbar;
  final void Function(
    String userId, {
    String? avatarUrl,
    String? displayName,
    String? backgroundUrl,
  })
  onUserTap;
  final VoidCallback onAssistantTap;
  final VoidCallback? onTapBack;
  final VoidCallback? onSwitchToFollowing;
  final VoidCallback? onSwitchToCircles;
  final VoidCallback? onSwitchToMoment;
  final VoidCallback? onRevealSystemNav;
  final VoidCallback? onHideSystemNav;
  final bool showTopNavigation;
  final List<PostBaseDto>? externalPosts;
  final List<ContentSurfaceView>? externalPostViews;
  final int initialPostIndex;
  final int initialImageIndex;
  final String source;
  final ReferralSource referralSource;
  final String? feedRequestId;
  final int? initialFeedPosition;
  final Map<String, MediaViewerPostWireRow> rawPostsById;
  final MediaViewerInteractionSnapshot initialInteractionSnapshot;
  final MediaViewerCommentContext initialCommentContext;
  final ValueChanged<MediaViewerResult>? onDismissed;
  final ValueChanged<int>? onPostIndexChanged;
  final double topChromeSafeInset;

  @override
  ConsumerState<WorksImmersiveViewer> createState() =>
      _WorksImmersiveViewerState();
}

class _WorksImmersiveViewerState extends ConsumerState<WorksImmersiveViewer>
    with TickerProviderStateMixin {
  static const int _tailPrefetchThreshold = 2;
  static const double _edgeDismissHotzoneWidth = AppSpacing.lg;
  static const double _edgeDismissMinDistance = 56;
  static const double _edgeDismissMinVelocity = 520;
  static const Duration _externalEmptyExitDelay = Duration(seconds: 6);

  Set<String> _selectedWorkFilterIds = <String>{'all'};
  int _currentPage = 0;
  final Map<String, int> _photoInnerIndex = <String, int>{};
  final Map<String, int> _articleInnerIndex = <String, int>{};
  final Map<String, int> _resolvedArticlePageCount = <String, int>{};
  final Map<String, String> _articlePaperThemeOverrides = <String, String>{};
  final Map<String, int> _videoInnerIndex = <String, int>{};
  final Map<String, String> _videoInnerIdentity = <String, String>{};
  final Set<String> _expandedCaptionPostIds = <String>{};
  String? _commentSplitPostId;

  // Dwell tracking：记录当前帖子进入时间
  DateTime? _pageEnterTime;
  PostBaseDto? _activeTrackedPost;
  _WorksTrackingAttribution? _activeTrackingAttribution;
  final DateTime _viewerOpenedAt = DateTime.now();
  final Map<String, Map<int, String>> _originalImageUrlsByPostId =
      <String, Map<int, String>>{};
  final Set<String> _requestingOriginalMediaIds = <String>{};
  final Map<String, Map<String, Object?>> _hydratedRawPostsById =
      <String, Map<String, Object?>>{};
  final Set<String> _hydratingArticleIds = <String>{};
  final Set<String> _failedArticleHydrationIds = <String>{};
  final Map<String, Object> _failedArticleHydrationErrorsById =
      <String, Object>{};
  final Map<String, WorkBrowserItemDto> _workItemCache =
      <String, WorkBrowserItemDto>{};
  final ImmersiveGestureIntentController _gestureIntentController =
      ImmersiveGestureIntentController();

  // 当前可见视频作品的播放会话与 viewport epoch 必须原子绑定；任何 epoch
  // 失效都同步清空，防止评论/筛选重建后旧 session 短暂回挂。
  ({
    String postId,
    String episodeIdentity,
    int episodeIndex,
    int viewportEpoch,
    VideoPlaybackSession session,
  })?
  _activeVideoBinding;
  int _videoEpisodeCallbackGeneration = 0;
  int _activeVideoSessionCallbackGeneration = 0;

  /// 外层作品页切换时失效旧 canvas 的延迟 session 回调。
  int _videoViewportEpoch = 0;
  String? _videoDurationStageKey;
  bool _videoDurationWindowActive = false;
  int _videoDurationWindowRevision = 0;
  Timer? _videoDurationWindowTimer;
  Timer? _externalEmptyTimer;
  bool _externalEmptyTimedOut = false;
  bool _authContinuationResumeScheduled = false;
  late final FeedPerformanceObservability _feedPerformanceObservability;
  late final ContentBehaviorTracker _contentBehaviorTracker;
  late final ContentEngagementTracker _contentEngagementTracker;
  late final ArticleReaderObservability _articleReaderObservability;

  late final PageController _pageController;
  bool _prefetchScheduled = false;
  bool _awaitingPrefetchedReveal = false;
  TabSwipeDirection? _activeEdgeDismissDirection;
  double _activeEdgeDismissDistance = 0;

  void _setMountedState(VoidCallback update) {
    if (!mounted) {
      return;
    }
    setState(update);
  }

  @override
  void initState() {
    super.initState();
    _gestureIntentController.addListener(_handleGestureIntentChanged);
    _feedPerformanceObservability = ref.read(
      feedPerformanceObservabilityProvider,
    );
    _contentBehaviorTracker = ref.read(contentBehaviorTrackerProvider);
    _contentEngagementTracker = ref.read(contentEngagementTrackerProvider);
    _articleReaderObservability = ref.read(articleReaderObservabilityProvider);
    final initialPage = _safeInitialPage;
    _currentPage = initialPage;
    _pageController = PageController(initialPage: initialPage);
    _configureExternalEmptyDeadline();
    WidgetsBinding.instance.addPostFrameCallback((timeStamp) {
      if (!mounted) return;
      primeMediaViewerInteractionSnapshot(
        ref,
        widget.initialInteractionSnapshot,
      );
      if (!_usesExternalFeed) {
        for (final tabId in _trackedFeedTabIds) {
          final feedMap = ref.read(discoveryFeedMapProvider);
          if (!feedMap.containsKey(tabId)) {
            ref.read(discoveryFeedMapProvider.notifier).load(tabId);
          }
        }
      }
      final posts = _buildFeed();
      if (posts.isNotEmpty) {
        final initialIndex = _currentPage.clamp(0, posts.length - 1);
        if (widget.initialCommentContext.shouldOpen &&
            _commentSplitPostId == null) {
          setState(() {
            _commentSplitPostId = posts[initialIndex].id;
            _invalidateVideoViewport(resetDurationWindow: false);
          });
        }
        // Track impression for the first post
        _trackImpressionForPost(posts[initialIndex], position: initialIndex);
      }
    });
  }

  @override
  void didUpdateWidget(covariant WorksImmersiveViewer oldWidget) {
    super.didUpdateWidget(oldWidget);
    final presentationChanged =
        !identical(oldWidget.rawPostsById, widget.rawPostsById) ||
        !identical(oldWidget.externalPosts, widget.externalPosts) ||
        !identical(oldWidget.externalPostViews, widget.externalPostViews);
    if (!presentationChanged) {
      return;
    }
    // 同一 postId 的 mediaItems 可能被契约水合、替换或重排。缓存必须先失效；
    // Canvas 再按 media identity 对齐并上报 binding，单纯重排不得误重启五秒窗口。
    _workItemCache.clear();
    _configureExternalEmptyDeadline();
  }

  @override
  void dispose() {
    final activePost = _activeTrackedPost;
    if (activePost != null) {
      _flushDwell(activePost);
    }
    AppToast.dismiss();
    _videoDurationWindowTimer?.cancel();
    _externalEmptyTimer?.cancel();
    _gestureIntentController.removeListener(_handleGestureIntentChanged);
    _gestureIntentController.dispose();
    _pageController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => _buildViewer(context);
}
