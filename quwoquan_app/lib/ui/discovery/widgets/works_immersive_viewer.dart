import 'dart:async';
import 'dart:math' show max;
import 'dart:ui' show FontFeature, ImageFilter;
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Theme;
import 'package:flutter/scheduler.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter/services.dart';
import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/errors/runtime_error_display.dart'
    as runtime_error_display;
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/work_browser_item_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/work_browser_media_item_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_target.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_text_span.g.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_statement_synthesizer.dart';
import 'package:video_player/video_player.dart'
    show VideoPlayerController, VideoPlayerValue;
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
import 'package:quwoquan_app/core/auth/auth_gate.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart'
    show authSessionControllerProvider;
import 'package:quwoquan_app/core/media/content_media_url.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/providers/feed_session_provider.dart';
import 'package:quwoquan_app/core/trackers/article_reader_observability.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/core/trackers/content_engagement_tracker.dart'
    show ContentType;
import 'package:quwoquan_app/core/trackers/feed_performance_observability.dart';
import 'package:quwoquan_app/core/trackers/page_lifecycle_observability.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/components/media/video/player/video_player_widget.dart';
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
part 'works_immersive_viewer_controls.dart';
part 'works_immersive_viewer_canvas.dart';
part 'works_immersive_viewer_engagement_actions.dart';

const double _worksImmersiveVerticalCommitFraction = 0.20;
double _worksContentIntersectionLineHeight(BuildContext context) {
  return AppTypography.xxs * AppSpacing.textLineHeightFootnote;
}

double _worksContentIntersectionBottomClearance(BuildContext context) {
  return ImmersiveEngagementBar.overlayClearance(
    context,
    gap: AppSpacing.intraGroupXs,
  );
}

double _worksContentOverlayBottomClearance(
  BuildContext context, {
  required bool includeIntersection,
  required double gap,
}) {
  if (!includeIntersection) {
    return ImmersiveEngagementBar.overlayClearance(context, gap: gap);
  }
  return ImmersiveEngagementBar.reservedHeight(context) +
      AppSpacing.intraGroupXs +
      _worksContentIntersectionLineHeight(context) +
      gap;
}

class _WorksImmersiveVerticalPagePhysics extends PageScrollPhysics {
  const _WorksImmersiveVerticalPagePhysics({
    required this.currentPage,
    this.holdVerticalScroll,
    super.parent,
  });
  final int Function() currentPage;
  final bool Function()? holdVerticalScroll;

  @override
  _WorksImmersiveVerticalPagePhysics applyTo(ScrollPhysics? ancestor) {
    return _WorksImmersiveVerticalPagePhysics(
      currentPage: currentPage,
      holdVerticalScroll: holdVerticalScroll,
      parent: buildParent(ancestor),
    );
  }

  @override
  bool shouldAcceptUserOffset(ScrollMetrics position) {
    if (holdVerticalScroll?.call() ?? false) {
      return false;
    }
    return super.shouldAcceptUserOffset(position);
  }

  @override
  double applyPhysicsToUserOffset(ScrollMetrics position, double offset) {
    if (holdVerticalScroll?.call() ?? false) {
      return 0;
    }
    return super.applyPhysicsToUserOffset(position, offset);
  }

  @override
  Simulation? createBallisticSimulation(
    ScrollMetrics position,
    double velocity,
  ) {
    if ((velocity <= 0.0 && position.pixels <= position.minScrollExtent) ||
        (velocity >= 0.0 && position.pixels >= position.maxScrollExtent)) {
      return super.createBallisticSimulation(position, velocity);
    }
    final tolerance = toleranceFor(position);
    final target = _targetPixels(position, tolerance, velocity);
    if ((target - position.pixels).abs() < tolerance.distance) {
      return null;
    }
    return ScrollSpringSimulation(
      spring,
      position.pixels,
      target,
      velocity,
      tolerance: tolerance,
    );
  }

  double _targetPixels(
    ScrollMetrics position,
    Tolerance tolerance,
    double velocity,
  ) {
    final anchorPage = currentPage().toDouble();
    final currentScrollPage = _pageForPixels(position, position.pixels);
    var targetPage = anchorPage;
    final deltaFromAnchor = currentScrollPage - anchorPage;
    if (deltaFromAnchor >= _worksImmersiveVerticalCommitFraction) {
      targetPage = anchorPage + 1;
    } else if (deltaFromAnchor <= -_worksImmersiveVerticalCommitFraction) {
      targetPage = anchorPage - 1;
    } else if (velocity < -tolerance.velocity) {
      targetPage = anchorPage + 1;
    } else if (velocity > tolerance.velocity) {
      targetPage = anchorPage - 1;
    }

    final minPage = _pageForPixels(position, position.minScrollExtent);
    final maxPage = _pageForPixels(position, position.maxScrollExtent);
    final clampedPage = targetPage.clamp(minPage, maxPage).toDouble();
    return _pixelsForPage(
      position,
      clampedPage,
    ).clamp(position.minScrollExtent, position.maxScrollExtent).toDouble();
  }

  double _pageForPixels(ScrollMetrics position, double pixels) {
    if (position is PageMetrics && position.page != null) {
      final extent = _pageExtent(position);
      return extent <= 0 ? 0 : pixels / extent;
    }
    final viewport = position.viewportDimension;
    return viewport <= 0 ? 0 : pixels / viewport;
  }

  double _pixelsForPage(ScrollMetrics position, double page) {
    return page * _pageExtent(position);
  }

  double _pageExtent(ScrollMetrics position) {
    final fraction = position is PageMetrics ? position.viewportFraction : 1.0;
    return max(1.0, position.viewportDimension * fraction);
  }
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

  Set<String> _selectedWorkFilterIds = <String>{'all'};
  int _currentPage = 0;
  final Map<String, int> _photoInnerIndex = <String, int>{};
  final Map<String, int> _articleInnerIndex = <String, int>{};
  final Map<String, int> _resolvedArticlePageCount = <String, int>{};
  final Map<String, String> _articlePaperThemeOverrides = <String, String>{};
  final Map<String, int> _videoInnerIndex = <String, int>{};
  final Set<String> _expandedCaptionPostIds = <String>{};
  String? _commentSplitPostId;

  // Dwell tracking：记录当前帖子进入时间
  DateTime? _pageEnterTime;
  final DateTime _viewerOpenedAt = DateTime.now();
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

  // 当前可见视频作品的播放控制器（由 _WorksVideoCanvas 上报，供极简控制条消费）。
  VideoPlayerController? _activeVideoController;
  String? _activeVideoStageKey;
  late final FeedPerformanceObservability _feedPerformanceObservability;

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
    final initialPage = _safeInitialPage;
    _currentPage = initialPage;
    _pageController = PageController(initialPage: initialPage);
    WidgetsBinding.instance.addPostFrameCallback((timeStamp) {
      if (!mounted) return;
      primeMediaViewerInteractionSnapshot(
        ref,
        widget.initialInteractionSnapshot,
      );
      if (!_usesExternalFeed) {
        for (final tabId in <String>['photo', 'video', 'article']) {
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
          setState(() => _commentSplitPostId = posts[initialIndex].id);
        }
        // Track impression for the first post
        _trackImpressionForPost(posts[initialIndex]);
        _pageEnterTime = DateTime.now();
      }
    });
  }

  @override
  void dispose() {
    AppToast.dismiss();
    _gestureIntentController.removeListener(_handleGestureIntentChanged);
    _gestureIntentController.dispose();
    _pageController.dispose();
    super.dispose();
  }

  bool get _usesExternalFeed =>
      widget.externalPosts != null && widget.externalPosts!.isNotEmpty;

  void _handleGestureIntentChanged() {
    // 边界只保留轻量回弹，不弹出沉浸打断提示。
  }

  void _handleImmersivePointerDown(PointerDownEvent event) {
    final capabilities = _gestureCapabilitiesForCurrentPost();
    if (capabilities == null) {
      return;
    }
    _gestureIntentController.begin(
      position: event.position,
      capabilities: capabilities,
    );
  }

  void _handleImmersivePointerMove(PointerMoveEvent event) {
    final capabilities = _gestureCapabilitiesForCurrentPost();
    if (capabilities == null) {
      return;
    }
    if (!_gestureIntentController.isTracking) {
      _gestureIntentController.begin(
        position: event.position,
        capabilities: capabilities,
      );
      return;
    }
    _gestureIntentController.update(
      position: event.position,
      capabilities: capabilities,
    );
  }

  void _handleImmersivePointerEnd() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_gestureIntentController.isTracking) {
        return;
      }
      _gestureIntentController.finish();
    });
  }

  ImmersiveGestureCapabilities? _gestureCapabilitiesForCurrentPost() {
    final posts = _buildFeed();
    if (posts.isEmpty) {
      return null;
    }
    final post = posts[_currentPage.clamp(0, posts.length - 1).toInt()];
    final allowVerticalSwitch = posts.length > 1;
    if (_isImageLikePost(post)) {
      final images = _imageUrlsForPost(post);
      final current = (_photoInnerIndex[post.id] ?? _defaultImageIndexFor(post))
          .clamp(0, max(0, images.length - 1))
          .toInt();
      return ImmersiveGestureCapabilities(
        pageCount: images.length,
        currentPageIndex: current,
        canFlipForward: current < images.length - 1,
        canFlipBack: current > 0,
        allowVerticalSwitch: allowVerticalSwitch,
        allowBoundaryRubberBand: true,
      );
    }
    if (_isArticleLikePost(post)) {
      final total = _articlePageCount(post);
      final current = (_articleInnerIndex[post.id] ?? 0)
          .clamp(0, total - 1)
          .toInt();
      return ImmersiveGestureCapabilities(
        pageCount: total,
        currentPageIndex: current,
        canFlipForward: current < total - 1,
        canFlipBack: current > 0,
        allowVerticalSwitch: allowVerticalSwitch,
        allowBoundaryRubberBand: true,
      );
    }
    return ImmersiveGestureCapabilities(
      pageCount: 1,
      currentPageIndex: 0,
      canFlipForward: false,
      canFlipBack: false,
      allowVerticalSwitch: allowVerticalSwitch,
      allowBoundaryRubberBand: false,
      startedInPageFlipHotzone: false,
    );
  }

  bool get _enableArticlePageCurl {
    final runtimeConfig = ref.read(contentRuntimeConfigProvider);
    return runtimeConfig.featureFlags.containsKey('enable_article_page_curl')
        ? runtimeConfig.isEnabled('enable_article_page_curl')
        : true;
  }

  List<String> get _trackedFeedTabIds {
    if (_usesExternalFeed) {
      return const <String>[];
    }
    final contentTypes = _effectiveFilterContentTypes;
    if (contentTypes.isEmpty) {
      return const <String>['photo', 'video', 'article'];
    }
    final tracked = <String>[];
    if (contentTypes.contains('image')) tracked.add('photo');
    if (contentTypes.contains('video')) tracked.add('video');
    if (contentTypes.contains('article')) tracked.add('article');
    return tracked;
  }

  DiscoveryFeedState? _readFeedState(String tabId) {
    return ref.read(discoveryFeedProvider(tabId)).value;
  }

  bool _trackedFeedsHaveMore() {
    return _trackedFeedTabIds.any(
      (tabId) => _readFeedState(tabId)?.hasMore ?? false,
    );
  }

  bool _trackedFeedsLoading() {
    return _trackedFeedTabIds.any(
      (tabId) => _readFeedState(tabId)?.isLoading ?? false,
    );
  }

  Object? _trackedFeedsError() {
    for (final tabId in _trackedFeedTabIds) {
      final error = _readFeedState(tabId)?.appendError;
      if (error != null) {
        return error;
      }
    }
    return null;
  }

  void _requestPrefetchNow({
    required int visibleIndex,
    required int postsLength,
    bool force = false,
  }) {
    if (_usesExternalFeed) {
      return;
    }
    final thresholdIndex = max(0, postsLength - 1 - _tailPrefetchThreshold);
    if (!force && visibleIndex < thresholdIndex) {
      return;
    }
    for (final tabId in _trackedFeedTabIds) {
      final feedState = _readFeedState(tabId);
      if (feedState == null || !feedState.hasMore || feedState.isLoading) {
        continue;
      }
      unawaited(
        ref.read(discoveryFeedMapProvider.notifier).appendNextPage(tabId),
      );
    }
  }

  void _schedulePrefetch({
    required int visibleIndex,
    required int postsLength,
    bool force = false,
  }) {
    if (_usesExternalFeed || _prefetchScheduled) {
      return;
    }
    _prefetchScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _prefetchScheduled = false;
      if (!mounted) {
        return;
      }
      _requestPrefetchNow(
        visibleIndex: visibleIndex,
        postsLength: postsLength,
        force: force,
      );
    });
  }

  int get _safeInitialPage {
    if (_usesExternalFeed) {
      return widget.initialPostIndex.clamp(0, widget.externalPosts!.length - 1);
    }
    return 0;
  }

  MediaViewerResult _buildResult() {
    final posts = _buildFeed();
    final postsById = <String, PostBaseDto>{
      for (final post in posts) post.id: post,
    };
    final scopePostIds =
        widget.initialInteractionSnapshot.effectiveScopePostIds;
    final scopeProfileIds =
        widget.initialInteractionSnapshot.effectiveScopeProfileIds;
    final postInteractionState = ref.read(postInteractionStateProvider);
    final relationshipState = ref.read(userRelationshipStateProvider);
    return MediaViewerResult(
      scopePostIds: Set<String>.from(scopePostIds),
      scopeProfileIds: Set<String>.from(scopeProfileIds),
      followingUsers: {
        for (final profileId in scopeProfileIds)
          if (relationshipState.isFollowing(profileId)) profileId,
      },
      likedPosts: {
        for (final postId in scopePostIds)
          if (postInteractionState.isLiked(postId)) postId,
      },
      postLikesCount: {
        for (final postId in scopePostIds)
          postId: postInteractionState.likeCountFor(
            postId,
            fallback: postsById[postId]?.likeCount ?? 0,
          ),
      },
      postSharesCount: {
        for (final postId in scopePostIds)
          postId: postInteractionState.shareCountFor(
            postId,
            fallback: postsById[postId]?.shareCount ?? 0,
          ),
      },
      postCommentCount: {
        for (final postId in scopePostIds)
          postId: postInteractionState.commentCountFor(
            postId,
            fallback: postsById[postId]?.commentCount ?? 0,
          ),
      },
    );
  }

  void _dismissViewer() {
    final result = _buildResult();
    if (widget.onDismissed != null) {
      widget.onDismissed!(result);
      return;
    }
    widget.onTapBack?.call();
  }

  bool _canDeletePost(
    PostBaseDto post,
    ActivePersonaContextViewData? activePersonaContext,
  ) {
    final postSubAccountId = post.subAccountId.trim();
    if (postSubAccountId.isEmpty) {
      return false;
    }
    final personaSubAccountId = activePersonaContext?.subAccountId.trim() ?? '';
    if (personaSubAccountId.isNotEmpty) {
      return personaSubAccountId == postSubAccountId;
    }
    final sessionSubAccountId = ref
        .read(authSessionControllerProvider)
        .activeSubAccountId
        .trim();
    if (sessionSubAccountId.isNotEmpty) {
      return sessionSubAccountId == postSubAccountId;
    }
    final currentUserId = ref.read(currentUserIdProvider).trim();
    return currentUserId.isNotEmpty && currentUserId == postSubAccountId;
  }

  Future<void> _deleteCurrentPost(
    BuildContext context,
    PostBaseDto post,
  ) async {
    runWhenLoggedIn(ref, context, AuthGateReason.deletePost, () async {
      final displayName = post.displayName.trim().isNotEmpty
          ? post.displayName.trim()
          : post.title.trim().isNotEmpty
          ? post.title.trim()
          : UITextConstants.contentUnavailable;
      final confirmed = await showAppActionSheet<bool>(
        context,
        title: UITextConstants.messageActionDelete,
        message: UITextConstants.profileSubAccountDeleteConfirmTemplate
            .replaceFirst('%s', displayName),
        sections: const [
          AppActionSheetSection<bool>(
            items: [
              AppActionSheetItem<bool>(
                value: true,
                label: UITextConstants.messageActionDelete,
                icon: CupertinoIcons.delete,
                isDestructive: true,
              ),
            ],
          ),
        ],
      );
      if (confirmed != true || !context.mounted) {
        return;
      }
      try {
        await ref
            .read(contentWriteRepositoryProvider)
            .deletePost(postId: post.id);
        ref.read(discoveryFeedMapProvider.notifier).removePostLocally(post.id);
        if (context.mounted) {
          AppToast.show(context, UITextConstants.contentDeleteSuccess);
        }
        if (!mounted) {
          return;
        }
        setState(() {
          _commentSplitPostId = null;
          _hydratedRawPostsById.remove(post.id);
          _workItemCache.remove(post.id);
          _failedArticleHydrationIds.remove(post.id);
          _failedArticleHydrationErrorsById.remove(post.id);
          _hydratingArticleIds.remove(post.id);
        });
        _dismissViewer();
      } catch (error) {
        if (!context.mounted) {
          return;
        }
        final semantic = runtime_error_display.runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.submit,
          scope: UiErrorScope.global,
        );
        await AppActionErrorFeedback.show(context, semantic: semantic);
      }
    });
  }

  Set<String> get _effectiveFilterIds {
    if (_selectedWorkFilterIds.isEmpty ||
        _selectedWorkFilterIds.contains('all')) {
      return <String>{'all'};
    }
    return _selectedWorkFilterIds;
  }

  Set<String> get _effectiveFilterContentTypes {
    final types = <String>{};
    for (final filter in ContentUIConfig.workFormatFilters) {
      if (_effectiveFilterIds.contains(filter.id) &&
          filter.contentType != null) {
        types.add(filter.contentType!);
      }
    }
    return types;
  }

  /// Opens the post-level more-options sheet for the currently visible post.
  ///
  /// Work Browser V1.0：媒体筛选入口在「更多」菜单内（全部作品/图片/视频/文章）。
  void _showWorksMoreSheet(BuildContext context) {
    final posts = _buildFeed();
    final post = posts.isEmpty
        ? null
        : posts[_currentPage.clamp(0, posts.length - 1)] as PostBaseDto?;
    if (post == null) return;
    final enableIdentityTemplate = ref.read(
      contentFeatureFlagProvider('enable_identity_share_template'),
    );
    final activePersonaContext = ref
        .read(activePersonaContextProvider)
        .asData
        ?.value;
    final canDelete = _canDeletePost(post, activePersonaContext);
    final filterOptions = <MoreActionFilterOption>[
      for (final filter in ContentUIConfig.workFormatFilters)
        MoreActionFilterOption(
          id: filter.id,
          label: UITextConstants.contentLabelForKey(filter.labelKey),
        ),
    ];
    final isArticle = _isArticleLikePost(post);
    final readingOptions = isArticle
        ? <MoreActionReadingOption>[
            for (final option in ContentUIConfig.articlePaperThemeOptions)
              MoreActionReadingOption(
                id: option.id,
                label: UITextConstants.contentLabelForKey(option.labelKey),
              ),
          ]
        : const <MoreActionReadingOption>[];
    MoreActionPopup.show(
      context: context,
      config: MediaPostMoreActionConfig(
        filterOptions: filterOptions,
        selectedFilterIds: _effectiveFilterIds.toList(growable: false),
        onFilterSelectionChanged: _applyFilterSelection,
        readingOptions: readingOptions,
        selectedReadingOptionId: isArticle
            ? (_articlePaperThemeOverrides[post.id] ?? 'system')
            : null,
        onReadingOptionChanged: isArticle
            ? (id) => setState(() {
                if (id == 'system') {
                  _articlePaperThemeOverrides.remove(post.id);
                } else {
                  _articlePaperThemeOverrides[post.id] = id;
                }
              })
            : null,
        forceDarkAppearance: true,
        onCopyLink: () => _copyLink(
          context,
          post,
          enableIdentityTemplate: enableIdentityTemplate,
        ),
        onShare: () => _sharePost(
          context,
          post,
          enableIdentityTemplate: enableIdentityTemplate,
        ),
        onNotInterested: () {
          ref
              .read(contentBehaviorTrackerProvider)
              .trackDislike(
                post.id,
                contentType: post.type,
                authorId: post.authorId,
              );
        },
        onBlockUser: () {
          ref.read(blockRepositoryProvider).blockUser(post.authorId);
          ref
              .read(contentBehaviorTrackerProvider)
              .trackHideAuthor(
                post.id,
                authorId: post.authorId,
                contentType: post.type,
                feedRequestId: ref
                    .read(feedSessionProvider.notifier)
                    .currentFeedRequestId,
                channelId: _immersiveChannelId(),
                rankingVersion: ref
                    .read(feedSessionProvider.notifier)
                    .currentRankingVersion,
                reasonVersion: ref
                    .read(feedSessionProvider.notifier)
                    .currentReasonVersion,
                recallPath: post.recallPath,
                contentVertical: post.contentVertical,
                supplySource: post.supplySource,
              );
        },
        onBlockWords: () async {
          final keyword = _keywordForPost(post);
          if (keyword.isEmpty) return;
          await ref
              .read(keywordBlockRepositoryProvider)
              .addBlockedKeyword(keyword);
          ref
              .read(contentBehaviorTrackerProvider)
              .trackHideContentType(
                post.id,
                contentType: post.type,
                authorId: post.authorId,
                feedRequestId: ref
                    .read(feedSessionProvider.notifier)
                    .currentFeedRequestId,
                channelId: _immersiveChannelId(),
                rankingVersion: ref
                    .read(feedSessionProvider.notifier)
                    .currentRankingVersion,
                reasonVersion: ref
                    .read(feedSessionProvider.notifier)
                    .currentReasonVersion,
                recallPath: post.recallPath,
                contentVertical: post.contentVertical,
                supplySource: post.supplySource,
              );
        },
        onReport: () {
          runWhenLoggedIn(
            ref,
            context,
            AuthGateReason.report,
            () async {
              try {
                await ref
                    .read(workBrowserContentReportCommandWriterProvider)
                    .createReport(
                      CreateContentReportCommand(
                        targetId: post.id,
                        targetType: ContentReportTargetType.post,
                        reason: ContentReportReason.other,
                      ),
                    );
                if (!context.mounted) return;
                AppToast.show(context, UITextConstants.commentReportSubmitted);
              } catch (error) {
                if (!context.mounted) return;
                await AppActionErrorFeedback.show(
                  context,
                  semantic: runtime_error_display.runtimeErrorSemantic(
                    context,
                    error: error,
                    category: UiErrorCategory.submit,
                    scope: UiErrorScope.global,
                  ),
                );
              }
            },
            dismissPolicy: LoginDismissPolicy.safeFallback,
          );
        },
        showDeleteAction: canDelete,
        onDelete: canDelete ? () => _deleteCurrentPost(context, post) : null,
      ),
    );
  }

  List<PostBaseDto> _buildFeed() {
    if (_usesExternalFeed) {
      final external = widget.externalPosts!;
      final filterTypes = _effectiveFilterContentTypes;
      if (filterTypes.contains('image') && filterTypes.length == 1) {
        return external.where(_isImageLikePost).toList(growable: false);
      }
      if (filterTypes.contains('video') && filterTypes.length == 1) {
        return external.where(_isVideoLikePost).toList(growable: false);
      }
      if (filterTypes.contains('article') && filterTypes.length == 1) {
        return external
            .where(
              (post) => _isArticleLikePost(post) || _isTextOnlyMomentPost(post),
            )
            .toList(growable: false);
      }
      if (filterTypes.isNotEmpty) {
        return external
            .where((post) {
              if (filterTypes.contains('image') && _isImageLikePost(post)) {
                return true;
              }
              if (filterTypes.contains('video') && _isVideoLikePost(post)) {
                return true;
              }
              if (filterTypes.contains('article') &&
                  (_isArticleLikePost(post) || _isTextOnlyMomentPost(post))) {
                return true;
              }
              return false;
            })
            .toList(growable: false);
      }
      return external;
    }
    final photos = ref.watch(discoveryFeedProvider('photo')).value?.items ?? [];
    final videos = ref.watch(discoveryFeedProvider('video')).value?.items ?? [];
    final articles =
        ref.watch(discoveryFeedProvider('article')).value?.items ?? [];

    final filterTypes = _effectiveFilterContentTypes;
    if (filterTypes.contains('image') && filterTypes.length == 1) return photos;
    if (filterTypes.contains('video') && filterTypes.length == 1) return videos;
    if (filterTypes.contains('article') && filterTypes.length == 1) {
      return articles;
    }
    if (filterTypes.isNotEmpty) {
      final result = <PostBaseDto>[];
      final maxLen = max(photos.length, max(videos.length, articles.length));
      for (var i = 0; i < maxLen; i++) {
        if (filterTypes.contains('image') && i < photos.length) {
          result.add(photos[i]);
        }
        if (filterTypes.contains('video') && i < videos.length) {
          result.add(videos[i]);
        }
        if (filterTypes.contains('article') && i < articles.length) {
          result.add(articles[i]);
        }
      }
      return result;
    }

    final result = <PostBaseDto>[];
    final maxLen = max(photos.length, max(videos.length, articles.length));
    for (var i = 0; i < maxLen; i++) {
      if (i < photos.length) result.add(photos[i]);
      if (i < videos.length) result.add(videos[i]);
      if (i < articles.length) result.add(articles[i]);
    }
    return result;
  }

  bool _hasStructuredArticlePayload(Map<String, Object?>? raw) {
    if (raw == null) {
      return false;
    }
    if ((raw[ArticleDetailWireKeys.articleMarkdown]?.toString().trim() ?? '')
        .isNotEmpty) {
      return true;
    }
    return false;
  }

  Map<String, Object?>? _effectiveRawPostById(String postId) {
    return _hydratedRawPostsById[postId] ?? _rawPostById(postId);
  }

  Map<String, Object?> _rawArticleDataFor(PostBaseDto post) {
    final raw = _effectiveRawPostById(post.id);
    final hasStructuredPayload = _hasStructuredArticlePayload(raw);
    final rawTitle = raw?['title']?.toString().trim() ?? '';
    final rawBody = raw?['body']?.toString().trim() ?? '';
    return <String, Object?>{
      ...?raw,
      'postId': post.id,
      'type': (raw?['type'] ?? raw?['contentType'] ?? 'article').toString(),
      'contentType': (raw?['contentType'] ?? raw?['type'] ?? 'article')
          .toString(),
      'authorId': (raw?['authorId'] ?? post.authorId).toString(),
      'displayName':
          (raw?['displayName'] ?? raw?['authorNickname'] ?? post.displayName)
              .toString(),
      'authorAvatarUrl': (raw?['authorAvatarUrl'] ?? post.avatarUrl).toString(),
      'title': rawTitle.isNotEmpty
          ? rawTitle
          : (hasStructuredPayload ? '' : post.title),
      'body': rawBody.isNotEmpty
          ? rawBody
          : (hasStructuredPayload ? '' : post.body),
      'coverUrl': (raw?[ArticleDetailWireKeys.coverUrl] ?? post.coverUrl)
          .toString(),
      'thumbnailUrl': (raw?['thumbnailUrl'] ?? post.thumbnailUrl).toString(),
      'mediaUrls': raw?['mediaUrls'] ?? post.imageUrls,
      'likeCount': raw?['likeCount'] ?? post.likeCount,
      'commentCount': raw?['commentCount'] ?? post.commentCount,
      'shareCount': raw?['shareCount'] ?? post.shareCount,
      'createdAt': raw?['createdAt'] ?? post.createdAt,
    };
  }

  ContentArticleRender _articleViewFor(PostBaseDto post) {
    return projectArticleDetailView(
      Map<String, dynamic>.from(_rawArticleDataFor(post)),
      fallbackArticleId: post.id,
    );
  }

  int _articlePageCount(PostBaseDto post) {
    return (_resolvedArticlePageCount[post.id] ??
            _articleViewFor(post).pages.length)
        .clamp(1, 99);
  }

  void _handleResolvedArticlePageCount(String postId, int pageCount) {
    final safePageCount = pageCount.clamp(1, 99);
    if (_resolvedArticlePageCount[postId] == safePageCount) {
      return;
    }
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || _resolvedArticlePageCount[postId] == safePageCount) {
        return;
      }
      setState(() {
        _resolvedArticlePageCount[postId] = safePageCount;
      });
    });
  }

  ({int current, int total}) _innerProgress(List<PostBaseDto> posts) {
    if (posts.isEmpty) return (current: 1, total: 1);
    final idx = _currentPage.clamp(0, posts.length - 1);
    final current = posts[idx];
    if (_isImageLikePost(current)) {
      final imageUrls = _imageUrlsForPost(current);
      final total = imageUrls.isEmpty ? 1 : imageUrls.length;
      final currentIndex =
          (_photoInnerIndex[current.id] ?? _defaultImageIndexFor(current))
              .clamp(0, total - 1) +
          1;
      return (current: currentIndex, total: total);
    }
    if (_isArticleLikePost(current)) {
      final total = _articlePageCount(current);
      final currentCard =
          (_articleInnerIndex[current.id] ?? 0).clamp(0, total - 1) + 1;
      return (current: currentCard, total: total);
    }
    if (_isTextOnlyMomentPost(current)) {
      return (current: 1, total: 1);
    }
    if (_isVideoLikePost(current)) {
      final items = _videoItemsFor(current);
      final total = items.isEmpty ? 1 : items.length.clamp(1, 99);
      final currentEpisode =
          (_videoInnerIndex[current.id] ?? 0).clamp(0, total - 1) + 1;
      return (current: currentEpisode, total: total);
    }
    return (current: 1, total: 1);
  }

  bool _isVideoLikePost(PostBaseDto post) {
    if (post.isVideoLike) {
      return true;
    }
    if (post.type.trim().toLowerCase() == 'video') {
      return true;
    }
    return _videoItemsFor(post).isNotEmpty;
  }

  bool _isArticleLikePost(PostBaseDto post) {
    return post.isArticleLike;
  }

  bool _isTextOnlyMomentPost(PostBaseDto post) {
    return post.identity == 'moment' && post.isTextOnly;
  }

  bool _isImageLikePost(PostBaseDto post) {
    if (_isVideoLikePost(post) ||
        _isArticleLikePost(post) ||
        _isTextOnlyMomentPost(post)) {
      return false;
    }
    return _imageUrlsForPost(post).isNotEmpty;
  }

  bool get _canSwipePrimaryTabs =>
      widget.showTopNavigation &&
      (widget.onSwitchToFollowing != null ||
          widget.onSwitchToCircles != null ||
          widget.onSwitchToMoment != null);

  bool get _canDismissViewerWithEdgeGesture =>
      widget.onDismissed != null || widget.onTapBack != null;

  bool _supportsEdgeDismissDirection(TabSwipeDirection direction) {
    if (!_canDismissViewerWithEdgeGesture) {
      return false;
    }
    return switch (Theme.of(context).platform) {
      TargetPlatform.android || TargetPlatform.fuchsia => true,
      TargetPlatform.iOS ||
      TargetPlatform.macOS ||
      TargetPlatform.linux ||
      TargetPlatform.windows => direction == TabSwipeDirection.previous,
    };
  }

  bool _edgeDismissWouldStealPageFlip(TabSwipeDirection direction) {
    final capabilities = _gestureCapabilitiesForCurrentPost();
    if (capabilities == null) {
      return false;
    }
    return switch (direction) {
      TabSwipeDirection.previous => capabilities.canFlipBack,
      TabSwipeDirection.next => capabilities.canFlipForward,
    };
  }

  void _resetEdgeDismissTracking() {
    _activeEdgeDismissDirection = null;
    _activeEdgeDismissDistance = 0;
  }

  void _handleEdgeDismissDragStart(TabSwipeDirection direction) {
    _activeEdgeDismissDirection = direction;
    _activeEdgeDismissDistance = 0;
  }

  void _handleEdgeDismissDragUpdate(
    DragUpdateDetails details,
    TabSwipeDirection direction,
  ) {
    if (_activeEdgeDismissDirection != direction) {
      return;
    }
    final signedDelta = direction == TabSwipeDirection.previous
        ? details.delta.dx
        : -details.delta.dx;
    _activeEdgeDismissDistance = max(
      0,
      _activeEdgeDismissDistance + signedDelta,
    );
  }

  void _handleEdgeDismissDragEnd(
    DragEndDetails details,
    TabSwipeDirection direction,
  ) {
    if (_activeEdgeDismissDirection != direction) {
      return;
    }
    final signedVelocity = direction == TabSwipeDirection.previous
        ? (details.primaryVelocity ?? 0)
        : -(details.primaryVelocity ?? 0);
    final shouldDismiss =
        _activeEdgeDismissDistance >= _edgeDismissMinDistance ||
        signedVelocity >= _edgeDismissMinVelocity;
    _resetEdgeDismissTracking();
    if (shouldDismiss) {
      _dismissViewer();
    }
  }

  Widget _buildEdgeDismissHotzone(TabSwipeDirection direction) {
    if (!_supportsEdgeDismissDirection(direction) ||
        _edgeDismissWouldStealPageFlip(direction)) {
      return const SizedBox.shrink();
    }
    return Positioned(
      top: 0,
      bottom: 0,
      left: direction == TabSwipeDirection.previous ? 0 : null,
      right: direction == TabSwipeDirection.next ? 0 : null,
      child: SizedBox(
        key: ValueKey<String>('works-edge-dismiss-${direction.name}'),
        width: _edgeDismissHotzoneWidth,
        child: GestureDetector(
          behavior: HitTestBehavior.translucent,
          onHorizontalDragStart: (_) => _handleEdgeDismissDragStart(direction),
          onHorizontalDragUpdate: (details) =>
              _handleEdgeDismissDragUpdate(details, direction),
          onHorizontalDragEnd: (details) =>
              _handleEdgeDismissDragEnd(details, direction),
          onHorizontalDragCancel: _resetEdgeDismissTracking,
          child: const SizedBox.expand(),
        ),
      ),
    );
  }

  void _switchToPreviousPrimaryTab() {
    if (widget.onSwitchToFollowing != null) {
      widget.onSwitchToFollowing!();
      return;
    }
    widget.onSwitchToMoment?.call();
  }

  void _switchToNextPrimaryTab() {
    widget.onSwitchToCircles?.call();
  }

  void _handlePrimaryTabSwipe(TabSwipeDirection direction) {
    if (!_canSwipePrimaryTabs) {
      return;
    }
    if (direction == TabSwipeDirection.previous) {
      _switchToPreviousPrimaryTab();
      return;
    }
    _switchToNextPrimaryTab();
  }

  void _handlePrimaryTabSwipeDragEnd(DragEndDetails details) {
    final direction = TabSwipeSwitchRegion.directionFromDragEnd(details);
    if (direction == null) {
      return;
    }
    _handlePrimaryTabSwipe(direction);
  }

  List<String> _imageUrlsForPost(PostBaseDto post) {
    if (post.hasImages) return post.mediaImageUrls;
    if (post.primaryImageUrl.isNotEmpty) return <String>[post.primaryImageUrl];
    return const <String>[];
  }

  int _defaultImageIndexFor(PostBaseDto post) {
    if (!_usesExternalFeed) return 0;
    final initialPost = widget.externalPosts![_safeInitialPage];
    if (post.id != initialPost.id) return 0;
    final total = _imageUrlsForPost(post).length;
    if (total <= 1) return 0;
    return widget.initialImageIndex.clamp(0, total - 1);
  }

  /// 作品级统一投影：raw wire + PostBaseDto 收敛为 [WorkBrowserItemDto]。
  /// 视频集（mediaItems）、图片序列、交集摘要只允许从该投影读取。
  WorkBrowserItemDto _workItemFor(PostBaseDto post) {
    final cached = _workItemCache[post.id];
    if (cached != null) return cached;
    final raw = _effectiveRawPostById(post.id);
    final source = raw == null
        ? post.toMap()
        : Map<String, dynamic>.from(
            raw.map((k, v) => MapEntry(k.toString(), v)),
          );
    final item = WorkBrowserItemDto.fromMap(source);
    _workItemCache[post.id] = item;
    return item;
  }

  /// 视频集序列：契约 mediaItems[kind=video]，为空时回落单视频。
  List<WorkBrowserMediaItemDto> _videoItemsFor(PostBaseDto post) {
    final items = _workItemFor(post).videoItems;
    if (items.isNotEmpty) return items;
    if (post.mediaVideoUrl.isEmpty) return const <WorkBrowserMediaItemDto>[];
    return <WorkBrowserMediaItemDto>[
      WorkBrowserMediaItemDto(
        kind: 'video',
        url: post.mediaVideoUrl,
        coverUrl: post.mediaVideoCoverUrl.isEmpty
            ? null
            : post.mediaVideoCoverUrl,
      ),
    ];
  }

  void _applyFilterSelection(Set<String> selectedIds) {
    final nextIds = selectedIds.isEmpty || selectedIds.contains('all')
        ? <String>{'all'}
        : selectedIds;
    setState(() {
      _selectedWorkFilterIds = nextIds;
      _currentPage = 0;
      _pageController.jumpToPage(0);
    });
  }

  Map<String, Object?>? _rawPostById(String postId) {
    final external = widget.rawPostsById[postId];
    if (external != null) return external.toObjectMap();
    final wire = ref
        .read(contentReadRepositoryProvider)
        .discoveryPresentationWireForPost(postId);
    if (wire == null) return null;
    return Map<String, Object?>.from(wire.toWireMap());
  }

  ContentSurfaceView? _summaryForPost(String postId) {
    final external = widget.externalPostViews;
    if (external == null || external.isEmpty) return null;
    for (final item in external) {
      if (item.postId == postId) return item;
    }
    return null;
  }

  Map<String, dynamic> _wireMapForPresentation(PostBaseDto post) {
    final raw = _effectiveRawPostById(post.id);
    if (raw == null) {
      return post.toMap();
    }
    return Map<String, dynamic>.from(
      raw.map((k, v) => MapEntry(k.toString(), v)),
    );
  }

  String _titleForPost(PostBaseDto post) {
    final raw = _effectiveRawPostById(post.id);
    final rawTitle = raw?['title']?.toString().trim() ?? '';
    if (rawTitle.isNotEmpty) return rawTitle;
    final summary = _summaryForPost(post.id);
    final summaryTitle = summary?.title?.trim() ?? '';
    if (summaryTitle.isNotEmpty) return summaryTitle;
    final pres = PostReadPresentation.fromPostBase(
      post,
      wire: _wireMapForPresentation(post),
    );
    return pres.title.isNotEmpty ? pres.title : post.normalizedTitle;
  }

  String _bodyForPost(PostBaseDto post) {
    final raw = _effectiveRawPostById(post.id);
    final rawBody =
        raw?['body']?.toString().trim() ??
        raw?[ContentPostImmersiveWireKeys.description]?.toString().trim() ??
        raw?[ContentPostImmersiveWireKeys.content]?.toString().trim() ??
        raw?[ContentPostImmersiveWireKeys.caption]?.toString().trim() ??
        '';
    if (rawBody.isNotEmpty) return rawBody;
    final summary = _summaryForPost(post.id);
    final summaryBody = summary?.body?.trim() ?? '';
    if (summaryBody.isNotEmpty) return summaryBody;
    final pres = PostReadPresentation.fromPostBase(
      post,
      wire: _wireMapForPresentation(post),
    );
    return pres.body.isNotEmpty ? pres.body : post.normalizedBody;
  }

  String _overlayTitleForPost(PostBaseDto post) {
    if (_isArticleLikePost(post) || _isTextOnlyMomentPost(post)) {
      return '';
    }
    return _titleForPost(post);
  }

  String _overlayBodyForPost(PostBaseDto post) {
    if (_isArticleLikePost(post) || _isTextOnlyMomentPost(post)) {
      return '';
    }
    return _bodyForPost(post);
  }

  _WorksTopChromeTheme _topChromeThemeForPost(
    BuildContext context,
    PostBaseDto? post,
  ) {
    return _WorksTopChromeTheme(
      overlayStyle: const SystemUiOverlayStyle(
        statusBarColor: AppColors.black,
        statusBarIconBrightness: Brightness.light,
        statusBarBrightness: Brightness.dark,
        systemNavigationBarColor: AppColors.black,
        systemNavigationBarIconBrightness: Brightness.light,
      ),
      foregroundColor: AppColors.white,
      mutedForegroundColor: AppColors.white.withValues(alpha: 0.72),
    );
  }

  ArticlePaperTexture _resolveArticlePaperTexture(PostBaseDto post) {
    final override = _articlePaperThemeOverrides[post.id];
    if (override != null && override != 'system') {
      return articlePaperTextureFromString(override);
    }
    final item = _workItemFor(post);
    final profile = item.articleRenderProfile ?? const <String, dynamic>{};
    final profileTexture = _stringFromProfile(profile, 'paperTexture');
    if (profileTexture != null && profileTexture.trim().isNotEmpty) {
      return articlePaperTextureFromString(profileTexture);
    }
    final topLevelTexture = item.paperTexture;
    if (topLevelTexture != null && topLevelTexture.trim().isNotEmpty) {
      return articlePaperTextureFromString(topLevelTexture);
    }
    final vertical =
        item.contentVertical ??
        _stringFromProfile(profile, 'contentVertical') ??
        ContentUIConfig.articleDarkPaperDefaultTheme;
    final mapped = ContentUIConfig.articlePaperVerticalDefaults[vertical];
    return articlePaperTextureFromString(
      mapped ?? ContentUIConfig.articleDarkPaperDefaultTheme,
    );
  }

  String? _stringFromProfile(Map<String, dynamic> profile, String key) {
    final value = profile[key];
    if (value == null) return null;
    return value.toString();
  }

  void _handleArticleInlineMentionTap(
    PostBaseDto post,
    ArticleInlineSpan span,
  ) {
    final targetType = span.targetType?.trim();
    final targetId = span.targetId?.trim() ?? '';
    if (targetId.isEmpty) return;
    if (span.isTag) {
      final tagRef = _tagRefForArticleMention(targetId);
      if (tagRef.isEmpty) return;
      context.push(AppRoutePaths.globalSearchNetworkResults(query: tagRef));
      return;
    }
    if (targetType == 'homepage') {
      context.push(AppRoutePaths.homepageDetail(id: targetId));
      return;
    }
    if (targetType != 'entity') return;
    final homepageId = _workItemFor(post).entityMentions
        .where((mention) => mention.subjectId.trim() == targetId)
        .map((mention) => mention.homepageId.trim())
        .where((id) => id.isNotEmpty)
        .firstOrNull;
    if (homepageId == null) return;
    context.push(AppRoutePaths.homepageDetail(id: homepageId));
  }

  String _tagRefForArticleMention(String targetId) {
    final normalized = targetId.trim();
    return normalized.startsWith('tag:')
        ? normalized.substring('tag:'.length)
        : normalized;
  }

  bool _showsCaptionOverlay(PostBaseDto post) {
    if (_isArticleLikePost(post)) {
      return false;
    }
    // 视频作品恒显示 caption 区（极简控制条挂载在 caption header）。
    if (_isVideoLikePost(post)) {
      return true;
    }
    // 图片多图作品恒显示（点指示器挂载在 caption header）。
    if (_isImageLikePost(post) && _imageUrlsForPost(post).length > 1) {
      return true;
    }
    return _overlayTitleForPost(post).isNotEmpty ||
        _overlayBodyForPost(post).isNotEmpty;
  }

  ImmersiveViewerStageLayoutSpec _layoutSpecForPost(PostBaseDto post) {
    if (_isArticleLikePost(post)) {
      return ImmersiveViewerStageLayoutSpec.articleStage;
    }
    if (_isTextOnlyMomentPost(post)) {
      return ImmersiveViewerStageLayoutSpec.textStage;
    }
    return ImmersiveViewerStageLayoutSpec.mediaStage;
  }

  ImmersiveViewerStageLayoutSpec _engagementLayoutSpecForPost(
    PostBaseDto post,
  ) {
    if (_isArticleLikePost(post)) {
      return ImmersiveViewerStageLayoutSpec.articleStage;
    }
    if (_isTextOnlyMomentPost(post)) {
      return ImmersiveViewerStageLayoutSpec.textStage;
    }
    return ImmersiveViewerStageLayoutSpec.mediaStage;
  }

  double _statusBarContentInsetFor(PostBaseDto post) {
    if (_isArticleLikePost(post)) {
      return AppSpacing.zero;
    }
    if (widget.topChromeSafeInset <= AppSpacing.zero) {
      return AppSpacing.zero;
    }
    return _shouldMediaInvadeStatusBar(post)
        ? AppSpacing.zero
        : widget.topChromeSafeInset;
  }

  bool _shouldMediaInvadeStatusBar(PostBaseDto post) {
    if (_isVideoLikePost(post)) {
      return true;
    }
    if (!_isImageLikePost(post)) {
      return false;
    }
    final aspectRatio = post.aspectRatio;
    if (aspectRatio == null || aspectRatio <= AppSpacing.zero) {
      return false;
    }
    return aspectRatio <= AppSpacing.immersiveStatusBarMaxAspectRatio;
  }

  bool _isCaptionExpanded(String postId) {
    return _expandedCaptionPostIds.contains(postId);
  }

  void _toggleCaptionExpanded(String postId) {
    setState(() {
      if (_expandedCaptionPostIds.contains(postId)) {
        _expandedCaptionPostIds.remove(postId);
      } else {
        _expandedCaptionPostIds.add(postId);
      }
    });
  }

  // ── 交集（推荐解释层）────────────────────────────────────────

  IntersectionTarget _postIntersectionContextTarget(PostBaseDto post) {
    return IntersectionTarget(
      objectType: 'post',
      objectId: post.id,
      objectKind: 'content',
      routeId: 'workBrowser',
    );
  }

  bool _sameIntersectionTarget(
    IntersectionTarget? left,
    IntersectionTarget? right,
  ) {
    if (left == null || right == null) {
      return false;
    }
    final leftId = left.objectId.trim();
    final rightId = right.objectId.trim();
    if (leftId.isEmpty || rightId.isEmpty || leftId != rightId) {
      return false;
    }
    final leftType = left.objectType.trim();
    final rightType = right.objectType.trim();
    if (leftType.isNotEmpty && rightType.isNotEmpty && leftType != rightType) {
      return false;
    }
    return true;
  }

  IntersectionReason? _primaryIntersectionReasonFor(PostBaseDto post) {
    final reasons = post.intersectionReasons ?? const <IntersectionReason>[];
    final contextTarget = _postIntersectionContextTarget(post);
    for (final reason in reasons) {
      final displayReason = displayReadyIntersectionReason(
        reason,
        contextObjectTarget: contextTarget,
      );
      if (displayReason != null) {
        return displayReason;
      }
    }
    return null;
  }

  /// 点击交集入口弹出推荐解释层（V1.0：解释层弹出，禁止卡片/标签遮挡内容）。
  void _showIntersectionDetail(BuildContext context, PostBaseDto post) {
    final reasons = post.intersectionReasons ?? const <IntersectionReason>[];
    if (reasons.isEmpty) return;
    showAppBottomModal<void>(
      context: context,
      builder: (sheetContext) => _WorksIntersectionDetailSheet(
        reasons: reasons,
        contextObjectTarget: _postIntersectionContextTarget(post),
        onAskAssistant: () {
          unawaited(
            dismissAppModalAndRun(
              sheetContext,
              action: () {
                if (!context.mounted) {
                  return;
                }
                _openAssistantForIntersectionReason(context, post, reasons);
              },
            ),
          );
        },
      ),
    );
  }

  void _openAssistantForIntersectionReason(
    BuildContext context,
    PostBaseDto post,
    List<IntersectionReason> reasons,
  ) {
    if (reasons.isEmpty) return;
    final primary = reasons.first;
    final target = VisitTarget.page('work_intersection_${post.id}');
    final openContext = AssistantOpenContext(
      source: AssistantSource.article,
      tab: 'work_intersection',
      dimension: primary.dimension,
      entityId: post.id,
      objectType: 'post',
      intersectionRefs: _intersectionRefsForReasons(reasons),
      visitTarget: target,
      experienceLevel: ref
          .read(visitRecorderServiceProvider)
          .getExperience(target),
      hints: <String, dynamic>{
        'postId': post.id,
        'contentType': post.type,
        'primaryText': primary.primaryText,
        'reasonCount': reasons.length,
      },
    );
    context.push(AppRoutePaths.assistantPersonal, extra: openContext);
  }

  List<String> _intersectionRefsForReasons(List<IntersectionReason> reasons) {
    final refs = <String>{};
    for (final reason in reasons) {
      final id = reason.intersectionId.trim();
      if (id.isNotEmpty) {
        refs.add('intersection:$id');
      }
      for (final tag in reason.tagRefs) {
        final normalized = tag.trim();
        if (normalized.isNotEmpty) {
          refs.add(normalized);
        }
      }
    }
    return refs.toList(growable: false);
  }

  void _openIntersectionSpan(
    BuildContext context,
    PostBaseDto post,
    IntersectionReason reason,
    IntersectionTextSpan span,
  ) {
    final navigator = IntersectionTargetNavigator(
      onTrack: (target, attribution) {
        _trackIntersectionTargetClick(
          post: post,
          target: target,
          attribution: attribution,
        );
      },
    );
    navigator.open(
      context,
      span.target,
      sourceRef: reason.source,
      attribution: _intersectionNavAttribution(reason),
    );
  }

  void _openIntersectionFallback(
    BuildContext context,
    PostBaseDto post,
    IntersectionReason reason,
  ) {
    final navigator = IntersectionTargetNavigator(
      onTrack: (target, attribution) {
        _trackIntersectionTargetClick(
          post: post,
          target: target,
          attribution: attribution,
        );
      },
    );
    final reasonTarget = IntersectionTargetNavigator.targetForReason(reason);
    if (!_sameIntersectionTarget(
          reasonTarget,
          _postIntersectionContextTarget(post),
        ) &&
        navigator.open(
          context,
          reasonTarget,
          sourceRef: reason.source,
          attribution: _intersectionNavAttribution(reason),
        )) {
      return;
    }
    for (final visual in reason.sampleVisuals) {
      if (navigator.open(
        context,
        visual.target,
        sourceRef: reason.source,
        attribution: _intersectionNavAttribution(reason),
      )) {
        return;
      }
    }
    final dimension = reason.dimension.trim();
    if (dimension.isNotEmpty &&
        navigator.open(
          context,
          IntersectionTarget(
            objectType: 'dimension',
            objectId: dimension,
            objectKind: 'tag',
            routeId: 'myIntersections',
          ),
          sourceRef: reason.source,
          attribution: _intersectionNavAttribution(reason),
        )) {
      return;
    }
    _showIntersectionDetail(context, post);
  }

  void _trackIntersectionTargetClick({
    required PostBaseDto post,
    required IntersectionTarget target,
    required IntersectionNavAttribution attribution,
  }) {
    final feedSession = ref.read(feedSessionProvider.notifier);
    ref
        .read(contentBehaviorTrackerProvider)
        .trackTagClick(
          target.objectId,
          contentType: target.objectKind.trim().isNotEmpty
              ? target.objectKind
              : post.type,
          authorId: target.objectKind == 'user' ? target.objectId : null,
          referralSource: ReferralSource.organicFeed,
          tags: attribution.tagRefs,
          feedRequestId: feedSession.currentFeedRequestId,
          channelId: _immersiveChannelId(),
          rankingVersion: feedSession.currentRankingVersion,
          reasonVersion: feedSession.currentReasonVersion,
          recallPath: post.recallPath,
          contentVertical: post.contentVertical,
          supplySource: post.supplySource,
          intersectionId: attribution.intersectionId,
          intersectionDimension: attribution.dimension,
          intersectionSourceRef: attribution.sourceRef,
          intersectionTagRefs: attribution.tagRefs,
          intersectionClass: attribution.intersectionClass,
          intersectionEvidenceId: attribution.evidenceId,
        );
  }

  IntersectionNavAttribution _intersectionNavAttribution(
    IntersectionReason reason,
  ) {
    return IntersectionNavAttribution(
      intersectionId: reason.intersectionId,
      dimension: reason.dimension,
      intersectionClass: reason.intersectionClass,
      sourceRef: reason.source,
      tagRefs: reason.tagRefs,
      evidenceId: reason.pointSummarySnapshotId,
    );
  }

  /// 视频画布上报当前激活的播放控制器（stageKey = postId-episodeIndex）。
  void _handleActiveVideoController(
    String stageKey,
    VideoPlayerController? controller,
  ) {
    if (!mounted) return;
    if (_activeVideoStageKey == stageKey &&
        identical(_activeVideoController, controller)) {
      return;
    }
    void applyState() {
      if (!mounted) return;
      setState(() {
        _activeVideoStageKey = stageKey;
        _activeVideoController = controller;
      });
    }

    final schedulerPhase = SchedulerBinding.instance.schedulerPhase;
    if (schedulerPhase == SchedulerPhase.idle ||
        schedulerPhase == SchedulerPhase.postFrameCallbacks) {
      applyState();
    } else {
      WidgetsBinding.instance.addPostFrameCallback((_) => applyState());
    }
    _feedPerformanceObservability.recordActiveVideoControllerCount(
      surfaceId: 'works_immersive_viewer',
      activeCount: controller == null ? 0 : 1,
    );
  }

  // ── 行为追踪辅助 ──────────────────────────────────────────────

  String _immersiveChannelId() {
    final normalized = widget.source.trim().toLowerCase();
    switch (normalized) {
      case 'featured':
      case 'premium':
      case 'premium_stream':
      case 'immersive':
        return 'premium_stream';
      default:
        return normalized.isEmpty ? 'premium_stream' : normalized;
    }
  }

  void _trackImpressionForPost(PostBaseDto post) {
    final tracker = ref.read(contentBehaviorTrackerProvider);
    final feedSession = ref.read(feedSessionProvider.notifier);
    tracker.trackImpression(
      post.id,
      contentType: post.type,
      referralSource: ReferralSource.organicFeed,
      feedRequestId: feedSession.currentFeedRequestId,
      channelId: _immersiveChannelId(),
      rankingVersion: feedSession.currentRankingVersion,
      reasonVersion: feedSession.currentReasonVersion,
      recallPath: post.recallPath,
      contentVertical: post.contentVertical,
      supplySource: post.supplySource,
    );

    final engTracker = ref.read(contentEngagementTrackerProvider);
    engTracker.trackContentEnter(
      post.id,
      contentType: _mapPostContentType(post),
      referralSource: ReferralSource.organicFeed,
      totalImages: post.imageUrls.length,
      authorId: post.authorId,
    );

    if (!_isArticleLikePost(post)) {
      return;
    }
    final bookReaderEnabled = ref.read(
      contentFeatureFlagProvider('enable_article_book_reader'),
    );
    final article = _articleViewFor(post);
    ref
        .read(articleReaderObservabilityProvider)
        .trackReaderOpen(
          postId: post.id,
          durationMs: DateTime.now().difference(_viewerOpenedAt).inMilliseconds,
          source: widget.source,
          template: article.template.name,
          fontPreset: article.fontPreset.name,
          pageCount: article.pages.length.clamp(1, 99),
          bookReaderEnabled: bookReaderEnabled,
        );
    if (!bookReaderEnabled) {
      ref
          .read(articleReaderObservabilityProvider)
          .trackReaderFallback(
            postId: post.id,
            reason: 'feature_flag_disabled',
            bookReaderEnabled: false,
          );
    }
    _trackDocumentStructureFallback(
      post: post,
      article: article,
      hydrated: _hydratedRawPostsById.containsKey(post.id),
    );
    unawaited(_maybeHydrateArticleDetail(post));
  }

  String _documentSourceName(ArticleDetailDocumentSource source) {
    return switch (source) {
      ArticleDetailDocumentSource.markdown => 'markdown',
      ArticleDetailDocumentSource.empty => 'empty',
    };
  }

  void _trackDocumentStructureFallback({
    required PostBaseDto post,
    required ContentArticleRender article,
    required bool hydrated,
  }) {
    if (article.documentSource == ArticleDetailDocumentSource.markdown) {
      return;
    }
    final bookReaderEnabled = ref.read(
      contentFeatureFlagProvider('enable_article_book_reader'),
    );
    ref
        .read(articleReaderObservabilityProvider)
        .trackReaderFallback(
          postId: post.id,
          reason:
              'document_structure:${_documentSourceName(article.documentSource)}:hydrated=$hydrated',
          bookReaderEnabled: bookReaderEnabled,
        );
  }

  Future<void> _maybeHydrateArticleDetail(
    PostBaseDto post, {
    bool force = false,
  }) async {
    final raw = _effectiveRawPostById(post.id);
    if (_hasStructuredArticlePayload(raw) ||
        _hydratingArticleIds.contains(post.id) ||
        (!force && _failedArticleHydrationIds.contains(post.id))) {
      return;
    }
    if (force) {
      _failedArticleHydrationIds.remove(post.id);
      _failedArticleHydrationErrorsById.remove(post.id);
    }
    _hydratingArticleIds.add(post.id);
    final startedAt = DateTime.now();
    try {
      final detail = await ref
          .read(workBrowserContentPostDetailReaderProvider)
          .getPost(postId: post.id);
      applyConfirmedInteractionPost(ref, detail.post);
      if (!mounted) {
        return;
      }
      setState(() {
        _hydratedRawPostsById[post.id] = <String, Object?>{
          ...?raw,
          ...Map<String, Object?>.from(detail.mergedArticleWireMap),
        };
        _failedArticleHydrationIds.remove(post.id);
        _failedArticleHydrationErrorsById.remove(post.id);
        _workItemCache.remove(post.id);
      });
      final hydratedArticle = _articleViewFor(post);
      _trackDocumentStructureFallback(
        post: post,
        article: hydratedArticle,
        hydrated: true,
      );
      ref
          .read(articleReaderObservabilityProvider)
          .trackHydration(
            postId: post.id,
            durationMs: DateTime.now().difference(startedAt).inMilliseconds,
            result: 'success',
            trigger: 'get_post',
            hadStructuredPayload: false,
          );
    } catch (error) {
      if (mounted) {
        setState(() {
          _failedArticleHydrationIds.add(post.id);
          _failedArticleHydrationErrorsById[post.id] = error;
        });
      } else {
        _failedArticleHydrationIds.add(post.id);
        _failedArticleHydrationErrorsById[post.id] = error;
      }
      ref
          .read(articleReaderObservabilityProvider)
          .trackHydration(
            postId: post.id,
            durationMs: DateTime.now().difference(startedAt).inMilliseconds,
            result: 'error',
            trigger: 'get_post',
            hadStructuredPayload: false,
          );
    } finally {
      _hydratingArticleIds.remove(post.id);
    }
  }

  bool _shouldShowArticleHydrationError(
    PostBaseDto post,
    ContentArticleRender article,
  ) {
    return article.documentSource == ArticleDetailDocumentSource.empty &&
        _failedArticleHydrationIds.contains(post.id);
  }

  UiErrorSemantic _articleHydrationErrorSemantic(PostBaseDto post) {
    return runtime_error_display.runtimeErrorSemantic(
      context,
      error:
          _failedArticleHydrationErrorsById[post.id] ??
          Exception('article hydration failed'),
      category: UiErrorCategory.pageLoad,
      scope: UiErrorScope.page,
    );
  }

  String _fallbackReasonName(ArticleReaderFallbackReason reason) {
    return switch (reason) {
      ArticleReaderFallbackReason.forcedDegradedPager =>
        'forced_degraded_pager',
      ArticleReaderFallbackReason.pageCurlDisabled => 'page_curl_disabled',
      ArticleReaderFallbackReason.accessibilityDisableAnimations =>
        'accessibility_disable_animations',
      ArticleReaderFallbackReason.longDocument => 'long_document',
    };
  }

  void _trackArticleReaderFallback(
    PostBaseDto post,
    ArticleReaderFallbackReason reason, {
    required bool bookReaderEnabled,
  }) {
    ref
        .read(articleReaderObservabilityProvider)
        .trackReaderFallback(
          postId: post.id,
          reason: _fallbackReasonName(reason),
          bookReaderEnabled: bookReaderEnabled,
        );
  }

  void _trackArticlePageFlipCommit(
    PostBaseDto post,
    ArticleReaderPageFlipCommit event,
  ) {
    ref
        .read(articleReaderObservabilityProvider)
        .trackPageFlipCommit(
          postId: post.id,
          durationMs: event.durationMs,
          mechanism: event.mechanism,
          direction: event.direction,
          fromPage: event.fromPage,
          toPage: event.toPage,
        );
  }

  void _trackImagePageflipMotion(
    PostBaseDto post,
    MediaPageFlipMotionEvent event,
  ) {
    final feedSession = ref.read(feedSessionProvider.notifier);
    ref
        .read(contentBehaviorTrackerProvider)
        .trackWorksImagePageflipMotion(
          post.id,
          direction: event.directionName,
          motionProfile: event.motionProfile,
          settleMs: event.settleDuration.inMilliseconds,
          reducedMotion: event.reducedMotion,
          committed: event.committed,
          contentType: post.type,
          referralSource: ReferralSource.organicFeed,
          feedRequestId: feedSession.currentFeedRequestId,
          position: _currentPage,
          channelId: _immersiveChannelId(),
          rankingVersion: feedSession.currentRankingVersion,
          reasonVersion: feedSession.currentReasonVersion,
          recallPath: post.recallPath,
          contentVertical: post.contentVertical,
          supplySource: post.supplySource,
        );
  }

  void _trackArticlePageCurlAbort(
    PostBaseDto post,
    ArticleReaderPageCurlAbort event,
  ) {
    ref
        .read(articleReaderObservabilityProvider)
        .trackPageCurlAbort(
          postId: post.id,
          corner: event.corner,
          progress: event.progress,
          direction: event.direction,
        );
  }

  void _flushDwell(PostBaseDto post) {
    final enterTime = _pageEnterTime;
    if (enterTime == null) return;
    final durationSec =
        DateTime.now().difference(enterTime).inMilliseconds / 1000.0;
    final tracker = ref.read(contentBehaviorTrackerProvider);
    final feedSession = ref.read(feedSessionProvider.notifier);
    tracker.trackDwell(
      post.id,
      durationSeconds: durationSec,
      contentType: post.type,
      referralSource: ReferralSource.organicFeed,
      feedRequestId: feedSession.currentFeedRequestId,
      channelId: _immersiveChannelId(),
      rankingVersion: feedSession.currentRankingVersion,
      reasonVersion: feedSession.currentReasonVersion,
      recallPath: post.recallPath,
      contentVertical: post.contentVertical,
      supplySource: post.supplySource,
    );
    _pageEnterTime = null;

    ref.read(contentEngagementTrackerProvider).trackContentExit(post.id);
  }

  ContentType _mapPostContentType(PostBaseDto post) {
    final fmt = post.displayFormat;
    if (fmt == 'video') return ContentType.video;
    if (fmt == 'article') return ContentType.article;
    if (post.type == 'micro') return ContentType.micro;
    return ContentType.image;
  }

  // ── 互动操作（乐观 UI + 云侧 API 同步）────────────────────────

  void _onLike(PostBaseDto post) {
    runWhenLoggedIn(ref, context, AuthGateReason.like, () {
      final isLiked = effectivePostLiked(ref, post.id);
      final currentCount = effectivePostLikeCount(
        ref,
        post.id,
        fallback: post.likeCount,
      );
      final nextLiked = !isLiked;
      final nextLikeCount = nextLiked
          ? currentCount + 1
          : (currentCount - 1).clamp(0, 1 << 31).toInt();
      syncPostLikeIntent(
        ref,
        postId: post.id,
        previousLiked: isLiked,
        isLiked: nextLiked,
        likeCount: nextLikeCount,
      );
    });
  }

  void _onFollow(PostBaseDto post) {
    runWhenLoggedIn(ref, context, AuthGateReason.follow, () {
      final subjectId = post.subAccountId;
      final wasFollowing = effectiveProfileFollowing(ref, subjectId);
      final nextFollowing = !wasFollowing;
      syncProfileFollowIntent(
        ref,
        subAccountId: subjectId,
        previousFollowing: wasFollowing,
        isFollowing: nextFollowing,
      );
    });
  }

  String _keywordForPost(PostBaseDto post) {
    final raw = _rawPostById(post.id);
    final source = [
      raw?['title']?.toString() ?? '',
      raw?['body']?.toString() ?? '',
    ].where((e) => e.trim().isNotEmpty).join(' ');
    final tokens = source
        .split(RegExp(r'[^\\u4e00-\\u9fa5A-Za-z0-9_]+'))
        .map((e) => e.trim())
        .where((e) => e.length >= 2)
        .toList();
    return tokens.isEmpty ? '' : tokens.first;
  }

  @override
  Widget build(BuildContext context) {
    ref.watch(postInteractionStateProvider);
    ref.watch(userRelationshipStateProvider);
    ref.watch(contentRuntimeConfigProvider);
    ref.watch(activePersonaContextProvider);
    final enableArticlePageCurl = _enableArticlePageCurl;
    final posts = _buildFeed();
    final showLoadMoreSentinel =
        !_usesExternalFeed &&
        posts.isNotEmpty &&
        (_trackedFeedsHaveMore() ||
            _trackedFeedsLoading() ||
            _trackedFeedsError() != null);
    final isOnLoadMoreSentinel =
        showLoadMoreSentinel && _currentPage >= posts.length;
    final currentPost = posts.isEmpty || isOnLoadMoreSentinel
        ? null
        : posts[_currentPage.clamp(0, posts.length - 1)];
    final loadMoreError = !_usesExternalFeed ? _trackedFeedsError() : null;
    final isLoadingMore = !_usesExternalFeed && _trackedFeedsLoading();
    if (posts.isNotEmpty) {
      _schedulePrefetch(
        visibleIndex: _currentPage.clamp(0, posts.length),
        postsLength: posts.length,
        force: isOnLoadMoreSentinel,
      );
    }
    if (_awaitingPrefetchedReveal && currentPost != null) {
      final revealedPost = currentPost;
      final revealedIndex = _currentPage;
      _awaitingPrefetchedReveal = false;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) {
          return;
        }
        widget.onPostIndexChanged?.call(revealedIndex);
        _trackImpressionForPost(revealedPost);
        _pageEnterTime = DateTime.now();
      });
    }
    final commentSplitPost = _commentSplitPostId == null
        ? null
        : _postById(posts, _commentSplitPostId!);
    if (commentSplitPost != null) {
      final interaction = ref.watch(postInteractionStateProvider);
      final splitPostId = commentSplitPost.id;
      // 评论分屏复用沉浸式状态栏样式（透明 + 浅色图标），避免回落为白底。
      return AnnotatedRegion<SystemUiOverlayStyle>(
        value: const SystemUiOverlayStyle(
          statusBarColor: AppColors.transparent,
          statusBarIconBrightness: Brightness.light,
          statusBarBrightness: Brightness.dark,
        ),
        child: DefaultTextStyle.merge(
          style: const TextStyle(
            decoration: TextDecoration.none,
            decorationThickness: 0,
          ),
          child: ImmersiveCommentSplitSheet(
            postId: splitPostId,
            content: _buildCommentSplitContent(commentSplitPost),
            entryObservedCommentCount: interaction.commentCountFor(
              splitPostId,
              fallback: commentSplitPost.commentCount,
            ),
            commentContext: widget.initialCommentContext,
            likeCount: interaction.likeCountFor(splitPostId),
            shareCount: effectivePostShareCount(
              ref,
              splitPostId,
              fallback: commentSplitPost.shareCount,
            ),
            isLiked: interaction.isLiked(splitPostId),
            onLikeTap: () => _onLike(commentSplitPost),
            onShareTap: () => _sharePost(
              context,
              commentSplitPost,
              enableIdentityTemplate: ref.read(
                contentFeatureFlagProvider('enable_identity_share_template'),
              ),
            ),
            onClose: () => setState(() => _commentSplitPostId = null),
          ),
        ),
      );
    }
    final currentLayoutSpec = currentPost == null
        ? ImmersiveViewerStageLayoutSpec.feedRail
        : _layoutSpecForPost(currentPost);
    final currentEngagementLayoutSpec = currentPost == null
        ? ImmersiveViewerStageLayoutSpec.feedRail
        : _engagementLayoutSpecForPost(currentPost);
    final progress = _innerProgress(posts);
    final overlayTitle = currentPost == null
        ? ''
        : _overlayTitleForPost(currentPost);
    final overlayBody = currentPost == null
        ? ''
        : _overlayBodyForPost(currentPost);
    final topChromeTheme = _topChromeThemeForPost(context, currentPost);
    final intersectionReason = currentPost == null
        ? null
        : _primaryIntersectionReasonFor(currentPost);
    final showContentIntersection = intersectionReason != null;
    // caption header（内容下方、标题上方）：
    // - 图片多图：点指示器（● ● ○ ● ●，最多 6 点）
    // - 视频：极简播放控制条 + 视频集进度
    Widget? counterIndicator;
    if (currentPost != null) {
      if (_isImageLikePost(currentPost) && progress.total > 1) {
        counterIndicator = _WorksPageIndicator(
          total: progress.total,
          current: progress.current,
        );
      } else if (_isVideoLikePost(currentPost)) {
        counterIndicator = _WorksVideoControlRow(
          key: ValueKey<String>('works-video-controls-${currentPost.id}'),
          controller:
              _activeVideoStageKey ==
                  '${currentPost.id}-${(_videoInnerIndex[currentPost.id] ?? 0)}'
              ? _activeVideoController
              : null,
          episodeCurrent: progress.current,
          episodeTotal: progress.total,
        );
      }
    }
    // 与 welcome_screen 一致：阻断 MaterialApp 默认 TextStyle 合并带来的误装饰（黄下划线等）。
    return DefaultTextStyle.merge(
      style: const TextStyle(
        decoration: TextDecoration.none,
        decorationThickness: 0,
      ),
      child: AnnotatedRegion<SystemUiOverlayStyle>(
        value: topChromeTheme.overlayStyle,
        child: GestureDetector(
          behavior: HitTestBehavior.deferToChild,
          onTap: () {
            if (!widget.showWorksToolbar) widget.onHideSystemNav?.call();
          },
          child: Stack(
            fit: StackFit.expand,
            children: [
              Positioned(
                top: 0,
                left: 0,
                right: 0,
                bottom: 0,
                child: Listener(
                  onPointerDown: _handleImmersivePointerDown,
                  onPointerMove: _handleImmersivePointerMove,
                  onPointerUp: (_) {
                    _handleImmersivePointerEnd();
                  },
                  onPointerCancel: (_) {
                    _gestureIntentController.cancel();
                  },
                  child: PageView.builder(
                    controller: _pageController,
                    scrollDirection: Axis.vertical,
                    physics: _WorksImmersiveVerticalPagePhysics(
                      currentPage: () => _currentPage,
                      holdVerticalScroll: () =>
                          _gestureIntentController.shouldHoldVerticalScroll,
                    ),
                    itemCount: posts.isEmpty
                        ? 1
                        : posts.length + (showLoadMoreSentinel ? 1 : 0),
                    onPageChanged: (index) {
                      if (_currentPage != index) {
                        // Flush dwell time for the previous post
                        if (posts.isNotEmpty && _currentPage < posts.length) {
                          final prevPost =
                              posts[_currentPage.clamp(0, posts.length - 1)];
                          _flushDwell(prevPost);
                          // Track skip: user swiped away from prevPost
                          final enterTime = _pageEnterTime;
                          final skipDwell = enterTime != null
                              ? DateTime.now()
                                        .difference(enterTime)
                                        .inMilliseconds /
                                    1000.0
                              : null;
                          ref
                              .read(contentBehaviorTrackerProvider)
                              .trackSkip(
                                prevPost.id,
                                dwellSeconds: skipDwell,
                                contentType: prevPost.type,
                                referralSource: ReferralSource.organicFeed,
                                feedRequestId: ref
                                    .read(feedSessionProvider.notifier)
                                    .currentFeedRequestId,
                                channelId: _immersiveChannelId(),
                                rankingVersion: ref
                                    .read(feedSessionProvider.notifier)
                                    .currentRankingVersion,
                                reasonVersion: ref
                                    .read(feedSessionProvider.notifier)
                                    .currentReasonVersion,
                                recallPath: prevPost.recallPath,
                                contentVertical: prevPost.contentVertical,
                                supplySource: prevPost.supplySource,
                              );
                        }

                        final nextIsSentinel =
                            showLoadMoreSentinel && index >= posts.length;
                        setState(() {
                          _currentPage = index;
                          _awaitingPrefetchedReveal = nextIsSentinel;
                        });
                        if (nextIsSentinel) {
                          _pageEnterTime = null;
                          _schedulePrefetch(
                            visibleIndex: index,
                            postsLength: posts.length,
                            force: true,
                          );
                          return;
                        }
                        widget.onPostIndexChanged?.call(index);
                        final newPost = posts[index.clamp(0, posts.length - 1)];
                        _trackImpressionForPost(newPost);
                        _pageEnterTime = DateTime.now();
                      }
                    },
                    itemBuilder: (context, index) {
                      if (posts.isEmpty) {
                        return Center(child: CupertinoActivityIndicator());
                      }
                      if (showLoadMoreSentinel && index >= posts.length) {
                        return _buildLoadMoreSentinel(
                          isLoading: isLoadingMore,
                          error: loadMoreError,
                          onRetry: () => _schedulePrefetch(
                            visibleIndex: index,
                            postsLength: posts.length,
                            force: true,
                          ),
                        );
                      }
                      final post = posts[index];
                      return Padding(
                        padding: EdgeInsets.only(
                          top: _statusBarContentInsetFor(post),
                        ),
                        child: KeyedSubtree(
                          key: ValueKey<String>(
                            'works-status-content-canvas-${post.id}',
                          ),
                          child: _buildPostCanvas(
                            post,
                            enableArticlePageCurl: enableArticlePageCurl,
                          ),
                        ),
                      );
                    },
                  ),
                ),
              ),

              _buildEdgeDismissHotzone(TabSwipeDirection.previous),
              _buildEdgeDismissHotzone(TabSwipeDirection.next),

              if (currentPost != null &&
                  _isArticleLikePost(currentPost) &&
                  widget.topChromeSafeInset > AppSpacing.zero)
                Positioned(
                  key: const ValueKey<String>('works-article-status-bar-scrim'),
                  top: 0,
                  left: 0,
                  right: 0,
                  height: widget.topChromeSafeInset,
                  child: const ColoredBox(color: AppColors.black),
                ),

              Positioned(
                top: 0,
                left: 0,
                right: 0,
                child: Padding(
                  padding: EdgeInsets.only(top: widget.topChromeSafeInset),
                  child: _WorksPrimaryTopBar(
                    layoutSpec: currentLayoutSpec,
                    foregroundColor: topChromeTheme.foregroundColor,
                    onTapClose: _dismissViewer,
                    onTapMore: () => _showWorksMoreSheet(context),
                    onHorizontalDragEnd: _handlePrimaryTabSwipeDragEnd,
                  ),
                ),
              ),

              if (currentPost != null && _showsCaptionOverlay(currentPost))
                Positioned(
                  left: 0,
                  right: 0,
                  bottom: _worksContentOverlayBottomClearance(
                    context,
                    includeIntersection: showContentIntersection,
                    gap: AppSpacing.containerSm,
                  ),
                  child: MediaCaptionBlock(
                    layoutSpec: currentLayoutSpec,
                    railKey: const ValueKey<String>('works-caption-rail'),
                    header: counterIndicator,
                    title: overlayTitle,
                    caption: overlayBody,
                    isExpanded: _isCaptionExpanded(currentPost.id),
                    onToggle: () => _toggleCaptionExpanded(currentPost.id),
                  ),
                ),

              // 文章页码：正文下方、作者工具栏上方（V1.0：`‹ 1 / 6 ›`，chevron 可点切页）。
              if (currentPost != null && _isArticleLikePost(currentPost))
                Positioned(
                  left: 0,
                  right: 0,
                  bottom: _worksContentOverlayBottomClearance(
                    context,
                    includeIntersection: showContentIntersection,
                    gap: AppSpacing.intraGroupSm,
                  ),
                  child: Center(
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        _WorksArticlePageChevron(
                          key: const ValueKey<String>(
                            'works-article-page-prev',
                          ),
                          icon: CupertinoIcons.chevron_back,
                          enabled: progress.current > 1,
                          color: topChromeTheme.mutedForegroundColor,
                          onTap: () => _stepArticlePage(currentPost, -1),
                        ),
                        SizedBox(width: AppSpacing.intraGroupXs),
                        Text(
                          UITextConstants.workArticlePageProgress(
                            progress.current,
                            progress.total,
                          ),
                          key: const ValueKey<String>(
                            'works-article-page-progress',
                          ),
                          style: TextStyle(
                            color: topChromeTheme.mutedForegroundColor,
                            fontSize: AppTypography.xs,
                            fontWeight: AppTypography.medium,
                            fontFeatures: const [FontFeature.tabularFigures()],
                          ),
                        ),
                        SizedBox(width: AppSpacing.intraGroupXs),
                        _WorksArticlePageChevron(
                          key: const ValueKey<String>(
                            'works-article-page-next',
                          ),
                          icon: CupertinoIcons.chevron_forward,
                          enabled: progress.current < progress.total,
                          color: topChromeTheme.mutedForegroundColor,
                          onTap: () => _stepArticlePage(currentPost, 1),
                        ),
                      ],
                    ),
                  ),
                ),

              if (currentPost != null && intersectionReason != null)
                Positioned(
                  left: 0,
                  right: 0,
                  bottom: _worksContentIntersectionBottomClearance(context),
                  child: ImmersiveViewerLayout.alignToRail(
                    context: context,
                    layoutSpec: currentEngagementLayoutSpec,
                    includeBottomSafeSideInset: true,
                    child: SizedBox(
                      key: const ValueKey<String>(
                        'works-caption-intersection-reason',
                      ),
                      width: double.infinity,
                      child: ImmersiveIntersectionStatement(
                        reason: intersectionReason,
                        contextObjectName:
                            currentPost.normalizedTitle.trim().isNotEmpty
                            ? currentPost.normalizedTitle.trim()
                            : currentPost.normalizedBody.trim(),
                        contextObjectTarget: IntersectionTarget(
                          objectType: 'post',
                          objectId: currentPost.id,
                          objectKind: 'content',
                          routeId: 'workBrowser',
                        ),
                        onSpanTap: (span) => _openIntersectionSpan(
                          context,
                          currentPost,
                          intersectionReason,
                          span,
                        ),
                        onFallbackTap: () => _openIntersectionFallback(
                          context,
                          currentPost,
                          intersectionReason,
                        ),
                      ),
                    ),
                  ),
                ),

              if (currentPost != null && widget.showWorksToolbar)
                Positioned(
                  left: 0,
                  right: 0,
                  bottom: 0,
                  child: Builder(
                    builder: (context) {
                      return ImmersiveEngagementBar(
                        layoutSpec: currentEngagementLayoutSpec,
                        avatarUrl: currentPost.avatarUrl,
                        displayName: currentPost.displayName,
                        authorBadge:
                            _workItemFor(currentPost).authorBadge ?? '',
                        likeCount: effectivePostLikeCount(
                          ref,
                          currentPost.id,
                          fallback: currentPost.likeCount,
                        ),
                        shareCount: effectivePostShareCount(
                          ref,
                          currentPost.id,
                          fallback: currentPost.shareCount,
                        ),
                        commentCount: effectivePostCommentCount(
                          ref,
                          currentPost.id,
                          fallback: currentPost.commentCount,
                        ),
                        isLiked: effectivePostLiked(ref, currentPost.id),
                        isFollowing: effectiveProfileFollowing(
                          ref,
                          currentPost.subAccountId,
                        ),
                        onUserTap: () {
                          // §7.3 旅程无断点：携该作品的最强证据组 kind 跳作者主页高亮。
                          ref
                              .read(
                                intersectionHighlightIntentProvider.notifier,
                              )
                              .primeFromReasons(
                                currentPost.subAccountId,
                                currentPost.intersectionReasons,
                              );
                          widget.onUserTap(
                            currentPost.subAccountId,
                            avatarUrl: currentPost.avatarUrl,
                            displayName: currentPost.displayName,
                            backgroundUrl: currentPost.authorBackgroundUrl,
                          );
                        },
                        onFollowTap: () => _onFollow(currentPost),
                        onLikeTap: () => _onLike(currentPost),
                        onCommentTap: () => _openCommentFor(currentPost.id),
                        onShareTap: () => _sharePost(
                          context,
                          currentPost,
                          enableIdentityTemplate: ref.read(
                            contentFeatureFlagProvider(
                              'enable_identity_share_template',
                            ),
                          ),
                        ),
                        onRevealSystemNav: widget.onRevealSystemNav,
                      );
                    },
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildPostCanvas(
    PostBaseDto post, {
    required bool enableArticlePageCurl,
  }) {
    return _buildTypedCanvas(
      post,
      enableArticlePageCurl: enableArticlePageCurl,
    );
  }

  Widget _buildLoadMoreSentinel({
    required bool isLoading,
    required Object? error,
    required VoidCallback onRetry,
  }) {
    final hasError = error != null;
    return ColoredBox(
      key: const ValueKey<String>('works-load-more-sentinel'),
      color: AppColors.black,
      child: Center(
        child: Padding(
          padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerLg),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (hasError)
                AppListAppendErrorFooter(
                  key: const ValueKey<String>('works-load-more-retry'),
                  semantic: runtime_error_display.runtimeErrorSemantic(
                    context,
                    error: error,
                    category: UiErrorCategory.listAppend,
                    scope: UiErrorScope.section,
                    presentation: UiErrorPresentation.appendFooter,
                  ),
                  onAction: isLoading
                      ? null
                      : (action) async {
                          if (action.type == UiErrorActionType.retry ||
                              action.type == UiErrorActionType.resubmit) {
                            onRetry();
                          }
                        },
                )
              else ...[
                const CupertinoActivityIndicator(radius: 16),
                SizedBox(height: AppSpacing.containerSm),
                Text(
                  UITextConstants.worksVideoBookLoadingTitle,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: AppColors.white,
                    fontSize: AppTypography.body,
                    fontWeight: AppTypography.semiBold,
                  ),
                ),
                SizedBox(height: AppSpacing.intraGroupSm),
                Text(
                  UITextConstants.worksVideoBookLoadingSubtitle,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: AppColors.white.withValues(alpha: 0.72),
                    fontSize: AppTypography.iosSubheadline,
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildTypedCanvas(
    PostBaseDto post, {
    required bool enableArticlePageCurl,
  }) {
    if (_isImageLikePost(post)) {
      return ImageBookCanvas(
        imageUrls: _imageUrlsForPost(post),
        initialIndex: _photoInnerIndex[post.id] ?? _defaultImageIndexFor(post),
        gestureIntentController: _gestureIntentController,
        onImageChanged: (index) =>
            setState(() => _photoInnerIndex[post.id] = index),
        onPageflipMotion: (event) => _trackImagePageflipMotion(post, event),
        onMediaLoad: (event) {
          ref
              .read(pageLifecycleObservabilityProvider)
              .recordMediaLoad(
                mediaType: 'image',
                result: event.result,
                pageName: 'works_image_book',
                copyKey: event.result == 'failure' ? 'imageLoadFailed' : null,
                error: event.error,
                durationMs: event.durationMs,
                candidatesTried: event.candidatesTried,
              );
        },
        onOverflowPrevious: null,
        onOverflowNext: null,
      );
    }
    if (_isVideoLikePost(post)) {
      return _WorksVideoCanvas(
        post: post,
        items: _videoItemsFor(post),
        onEpisodeChanged: (idx) =>
            setState(() => _videoInnerIndex[post.id] = idx),
        onActiveControllerChanged: (episodeIndex, controller) =>
            _handleActiveVideoController(
              '${post.id}-$episodeIndex',
              controller,
            ),
      );
    }
    if (_isArticleLikePost(post)) {
      final article = _articleViewFor(post);
      if (_shouldShowArticleHydrationError(post, article)) {
        return AppPageErrorState(
          key: ValueKey<String>('article-hydration-error-${post.id}'),
          semantic: _articleHydrationErrorSemantic(post),
          onAction: (action) async {
            if (action.type == UiErrorActionType.retry ||
                action.type == UiErrorActionType.resubmit) {
              await _maybeHydrateArticleDetail(post, force: true);
            }
          },
        );
      }
      final safeInitialPage = (_articleInnerIndex[post.id] ?? 0)
          .clamp(0, _articlePageCount(post) - 1)
          .toInt();
      return _WorksArticleCanvas(
        post: post,
        article: article,
        timeLine: ContentTimeLabel.readerLine(
          createdAt: post.createdAt,
          updatedAt: post.updatedAt,
        ),
        paperTexture: _resolveArticlePaperTexture(post),
        enablePageCurl: enableArticlePageCurl,
        initialPage: safeInitialPage,
        topChromeSafeInset: widget.topChromeSafeInset,
        reserveContentIntersection: _primaryIntersectionReasonFor(post) != null,
        onPageChanged: (index) => _handleArticleInnerPageChanged(post, index),
        onResolvedPageCountChanged: (pageCount) =>
            _handleResolvedArticlePageCount(post.id, pageCount),
        onFallbackResolved: (reason) =>
            _trackArticleReaderFallback(post, reason, bookReaderEnabled: true),
        onPageFlipCommitted: (event) =>
            _trackArticlePageFlipCommit(post, event),
        onPageCurlAborted: (event) => _trackArticlePageCurlAbort(post, event),
        onEntityTap: (span) => _handleArticleInlineMentionTap(post, span),
        gestureIntentController: _gestureIntentController,
        onOverflowPrevious: null,
        onOverflowNext: null,
      );
    }
    if (_isTextOnlyMomentPost(post)) {
      return TabSwipeSwitchRegion(
        enabled: _canSwipePrimaryTabs,
        onSwipe: _handlePrimaryTabSwipe,
        child: _WorksTextCanvas(
          layoutSpec: _layoutSpecForPost(post),
          title: _titleForPost(post),
          body: _bodyForPost(post),
          reserveContentIntersection:
              _primaryIntersectionReasonFor(post) != null,
          imageUrl: _rawPostById(
            post.id,
          )?[ArticleDetailWireKeys.coverUrl]?.toString(),
        ),
      );
    }
    return Container(color: AppColors.worksBackground);
  }

  /// 页码 chevron 切页（V1.0 `‹ n / m ›`）：更新 inner index 后由
  /// `_WorksArticleCanvas.initialPage` 驱动 deck `didUpdateWidget` 跳页，
  /// 不引入第二套翻页控制通路。
  void _stepArticlePage(PostBaseDto post, int delta) {
    final total = _articlePageCount(post);
    final current = (_articleInnerIndex[post.id] ?? 0).clamp(0, total - 1);
    final next = (current + delta).clamp(0, total - 1).toInt();
    if (next == current) return;
    setState(() => _articleInnerIndex[post.id] = next);
  }

  void _handleArticleInnerPageChanged(PostBaseDto post, int index) {
    final previousIndex = _articleInnerIndex[post.id] ?? 0;
    if (previousIndex != index) {
      _trackArticlePageFlipCommit(
        post,
        ArticleReaderPageFlipCommit(
          fromPage: previousIndex,
          toPage: index,
          durationMs: 0,
          mechanism: 'page_curl',
        ),
      );
    }
    setState(() => _articleInnerIndex[post.id] = index);
  }
}
