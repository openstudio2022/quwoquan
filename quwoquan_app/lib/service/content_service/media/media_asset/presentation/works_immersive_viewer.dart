import 'dart:async';
import 'dart:math' show max;
import 'dart:ui' show FontFeature, ImageFilter;
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Theme;
import 'package:flutter/rendering.dart'
    show RenderBox, RenderObject, RenderParagraph;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart' show LaunchMode, launchUrl;
import 'package:video_player/video_player.dart' show VideoViewType;
import 'package:quwoquan_app/runtime/errors/generated/content/content_errors.g.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/generated/content_media_post_projection_keys.g.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_media_viewer_policy.dart';
import 'package:quwoquan_app/runtime/di/content_media_viewer_policy_dependencies.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart'
    as runtime_error_display;
import 'package:quwoquan_app/service/content_service/content/post/application/public/discovery_feed_load_result.dart'
    show DiscoveryFeedLoadResult, DiscoveryFeedLoadTerminal;
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/video_preview_track_query.dart';
import 'package:quwoquan_app/runtime/di/presentation/home_feed_cross_object_composition.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_delete.dart'
    show contentPostDeleteIdempotencyKey;
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/image_book_canvas.dart';
import 'package:quwoquan_app/design_system/gestures/immersive_gesture_intent_controller.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/media_page_flip_book.dart';
import 'package:quwoquan_app/runtime/di/object_intersection_provider.dart';
import 'package:quwoquan_app/runtime/di/navigation/intersection_target_navigator.dart';
import 'package:quwoquan_app/l10n/copy/gathering_text_constants.dart'
    show GatheringText;
import 'package:quwoquan_app/runtime/di/gathering_dependencies.dart'
    show gatheringQueryReaderProvider;
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_ports.dart'
    show GatheringBySourceListQuery;
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/public/generated/homepage_ui_config.g.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/application/public/object_intersection_query.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/application/public/intersection_kind_mapping.dart'
    show intersectionMutualCountOf;
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/surfaces/app_modal_presenter.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/immersive_engagement_bar.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/media_viewer_toolbar.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/immersive_viewer_layout.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/media_caption_widgets.dart';
import 'package:quwoquan_app/design_system/surfaces/app_modal_surface.dart';
import 'package:quwoquan_app/design_system/surfaces/app_action_sheet.dart';
import 'package:quwoquan_app/design_system/navigation/tab_swipe_switch_region.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/l10n/copy/discovery_feed_text_constants.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/page_context/application/public/assistant_open_context.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/public/media_viewer_extra.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/domain/work_browser_view_data.dart';
import 'package:quwoquan_app/runtime/models/visit_models.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart'
    show ReferralSource;
import 'package:quwoquan_app/runtime/auth/auth_continuation.dart';
import 'package:quwoquan_app/runtime/auth/auth_gate.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart'
    show AuthSessionState, authSessionControllerProvider;
import 'package:quwoquan_app/runtime/transport/media/content_media_url.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_app/runtime/di/video_preview_track_dependencies.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/observability/trackers/article_reader_observability.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_tracker_port.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_engagement_tracker.dart'
    show ContentEngagementTracker;
import 'package:quwoquan_app/runtime/observability/trackers/feed_performance_observability_provider.dart';
import 'package:quwoquan_app/runtime/observability/trackers/feed_performance_observability.dart';
import 'package:quwoquan_app/runtime/observability/trackers/page_lifecycle_observability.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_keyword_suggester.dart';
import 'package:quwoquan_app/runtime/shell/actions/blocked_keyword_confirmation_sheet.dart';
import 'package:quwoquan_app/runtime/shell/actions/content_report_reason_sheet.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/video_playback_session.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/video_playback_center_glyph.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/video_playback_timeline.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/video_player_widget.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/video_timeline_preview.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart'
    show ActivePersonaContextViewData;
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/works_viewer_article_hydration_admission.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/works_video_episode_identity.dart';
import 'package:quwoquan_app/runtime/di/content_surface_view_mapper.dart';
import 'package:quwoquan_app/runtime/di/works_viewer_content_action_dependencies.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/public/works_viewer_content_action_contract.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_detail_view.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_document_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_presentation_values.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_surface_view.dart';
import 'package:quwoquan_app/design_system/formatters/content_time_label.dart';
import 'package:quwoquan_app/runtime/di/media_viewer_interaction_facade.dart';
import 'package:quwoquan_app/runtime/di/works_viewer_article_dependencies.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/works_article_events.dart';
import 'package:quwoquan_app/runtime/di/works_viewer_feed_bridge.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/post_article_detail_projector.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/public/home_feed_video_autoplay_policy.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/domain/works_viewer_state_budget.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/works_immersive_viewer_observability.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/works_immersive_viewer_paging.dart';
part 'works_immersive_viewer_controls.dart';
part 'works_immersive_viewer_canvas.dart';
part 'works_immersive_viewer_engagement_actions.dart';
part 'works_immersive_viewer_feed_terminal.dart';
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
    required this.policyDigest,
  });

  final ReferralSource referralSource;
  final String? feedRequestId;
  final int position;
  final String channelId;
  final String? policyDigest;
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
    this.policyDigest,
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
  final VoidCallback? onRevealSystemNav;
  final VoidCallback? onHideSystemNav;
  final bool showTopNavigation;
  final List<ContentPostViewData>? externalPosts;
  final List<ContentSurfaceView>? externalPostViews;
  final int initialPostIndex;
  final int initialImageIndex;
  final String source;
  final ReferralSource referralSource;
  final String? feedRequestId;
  final String? policyDigest;
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
    with TickerProviderStateMixin, WidgetsBindingObserver {
  static const int _tailPrefetchThreshold = 2;
  static const int _maxOriginalImageAccessEntriesPerPost = 12;
  static const double _edgeDismissHotzoneWidth = AppSpacing.lg;
  static const double _edgeDismissMinDistance = 56;
  static const double _edgeDismissMinVelocity = 520;
  static const Duration _externalEmptyExitDelay = Duration(seconds: 6);

  ContentMediaViewerPolicy get _contentMediaViewerPolicy =>
      ref.read(contentMediaViewerPolicyProvider);

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
  ContentPostViewData? _activeTrackedPost;
  _WorksTrackingAttribution? _activeTrackingAttribution;
  final DateTime _viewerOpenedAt = DateTime.now();
  final Map<String, Map<int, WorksViewerOriginalImageAccess>>
  _originalImageUrlsByPostId =
      <String, Map<int, WorksViewerOriginalImageAccess>>{};
  // 仅保存 canonical operation deadline 内的在途去重；finally 必须移除，
  // 不作为跨请求、跨作品或跨会话缓存。
  final Set<String> _requestingOriginalMediaIds = <String>{};
  // 想去状态：按 primaryHomepageId 缓存当前会话内读到/写入的 wishlist 状态；
  // 只反映服务端事实或本次确认写入，不做本地推断。
  final Map<String, bool> _wishlistStateByHomepageId = <String, bool>{};
  final Set<String> _loadingWishlistHomepageIds = <String>{};

  // 经历溯源（L0 氛围层）：种草内容按 content 锚点社会证明（成形级）判定
  // 「他们从这条内容出发一起去了」；回顾内容由 wire gatheringRef 直接锚定。
  // 只缓存服务端事实；null 表示尚未读取，false 表示已确认无成形行动。
  final Map<String, bool> _seedProvenanceByPostId = <String, bool>{};
  final Set<String> _loadingSeedProvenancePostIds = <String>{};
  final Map<String, Map<String, Object?>> _hydratedRawPostsById =
      <String, Map<String, Object?>>{};
  // GetPost 严格串行且只保留最新可见文章；切换作品会 cooperative cancel
  // 旧 operation，迟到结果不得进入 resident LRU。
  final WorksViewerArticleHydrationAdmission _articleHydrationAdmission =
      WorksViewerArticleHydrationAdmission();
  int _feedRecoveryGeneration = 0;
  final Set<String> _failedArticleHydrationIds = <String>{};
  final Map<String, Object> _failedArticleHydrationErrorsById =
      <String, Object>{};
  final WorksViewerLruCache<String, WorkBrowserViewData> _workItemCache =
      WorksViewerLruCache<String, WorkBrowserViewData>();
  late final WorksViewerPostStateWindow _postStateWindow;
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
  late final ContentBehaviorTrackerPort _contentBehaviorTracker;
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

  void _evictPostLocalState(String postId) {
    _articleHydrationAdmission.cancelPost(postId);
    _photoInnerIndex.remove(postId);
    _articleInnerIndex.remove(postId);
    _resolvedArticlePageCount.remove(postId);
    _articlePaperThemeOverrides.remove(postId);
    _videoInnerIndex.remove(postId);
    _videoInnerIdentity.remove(postId);
    _expandedCaptionPostIds.remove(postId);
    _originalImageUrlsByPostId.remove(postId);
    _hydratedRawPostsById.remove(postId);
    _failedArticleHydrationIds.remove(postId);
    _failedArticleHydrationErrorsById.remove(postId);
    _workItemCache.remove(postId);
  }

  void _rememberPostLocalState(String postId) {
    _postStateWindow.touch(postId);
  }

  void _retainPostLocalStateAround(
    List<ContentPostViewData> posts,
    int visibleIndex,
  ) {
    if (posts.isEmpty) {
      return;
    }
    _postStateWindow.updateViewport(
      itemCount: posts.length,
      currentIndex: visibleIndex,
      postIdAt: (index) => posts[index].id,
    );
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _postStateWindow = WorksViewerPostStateWindow(_evictPostLocalState);
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
          final feedCommands = ref.read(worksViewerFeedCommandsProvider);
          if (!feedCommands.contains(tabId)) {
            unawaited(feedCommands.load(tabId));
          }
        }
      }
      final posts = _buildFeed();
      if (posts.isNotEmpty) {
        final initialIndex = _currentPage.clamp(0, posts.length - 1);
        _retainPostLocalStateAround(posts, initialIndex);
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
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      final posts = _buildFeed();
      _retainPostLocalStateAround(posts, _currentPage);
    });
  }

  @override
  void didHaveMemoryPressure() {
    super.didHaveMemoryPressure();
    final posts = _buildFeed();
    final currentPostId = posts.isEmpty
        ? null
        : posts[_currentPage.clamp(0, posts.length - 1)].id;
    _postStateWindow.handleMemoryPressure(currentPostId: currentPostId);
    _workItemCache.clear();
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
    WidgetsBinding.instance.removeObserver(this);
    _gestureIntentController.removeListener(_handleGestureIntentChanged);
    _gestureIntentController.dispose();
    _pageController.dispose();
    _articleHydrationAdmission.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => _buildViewer(context);
}
