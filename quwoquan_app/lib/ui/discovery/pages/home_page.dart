import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Material, MaterialType;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/components/navigation/home_primary_tab_strip.dart';
import 'package:quwoquan_app/components/navigation/tab_swipe_switch_region.dart';
import 'package:quwoquan_app/core/models/assistant_open_context.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/models/user_profile_route_extra.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/ui/discovery/services/home_feed_media_viewer_wiring.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/global_surface_actions.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/ui/assistant/widgets/assistant_half_sheet.dart';
import 'package:quwoquan_app/ui/content/media_viewer_interaction_bridge.dart';
import 'package:quwoquan_app/ui/content/post_summary_view.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart'
    show BehaviorAction, ReferralSource;
import 'package:quwoquan_app/core/providers/feed_session_provider.dart';
import 'package:quwoquan_app/ui/discovery/widgets/moment_social_feed.dart';
import 'package:quwoquan_app/ui/discovery/widgets/works_immersive_viewer.dart';

class HomePage extends ConsumerStatefulWidget {
  const HomePage({super.key, this.routeLocation});

  final String? routeLocation;

  @override
  ConsumerState<HomePage> createState() => _HomePageState();
}

class _HomePageState extends ConsumerState<HomePage>
    with AutomaticKeepAliveClientMixin {
  static const String _defaultTab = HomePrimaryTabStrip.recommendedTabId;
  static const List<String> _tabOrder = HomePrimaryTabStrip.homeTabIds;
  late String _activeTab;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _activeTab = _initialTabForRoute(widget.routeLocation);
  }

  @override
  void didUpdateWidget(HomePage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.routeLocation == widget.routeLocation) {
      return;
    }
    final routeTab = _routeDrivenTab(widget.routeLocation);
    if (routeTab == null || routeTab == _activeTab) {
      return;
    }
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      setState(() {
        _activeTab = routeTab;
      });
    });
  }

  String _initialTabForRoute(String? location) {
    return _routeDrivenTab(location) ?? _defaultTab;
  }

  String? _routeDrivenTab(String? location) {
    switch (location) {
      case AppRoutePaths.home:
        return _defaultTab;
      case '/following':
        return HomePrimaryTabStrip.followingTabId;
      default:
        return null;
    }
  }

  void _syncShellRouteForTab(String id) {
    final targetLocation = switch (id) {
      HomePrimaryTabStrip.followingTabId => AppRoutePaths.home,
      _ => null,
    };
    final router = GoRouter.maybeOf(context);
    if (targetLocation == null ||
        widget.routeLocation == targetLocation ||
        router == null) {
      return;
    }
    Future.microtask(() {
      if (!mounted) return;
      router.go(targetLocation);
    });
  }

  void _handleTabChange(String id) {
    if (_activeTab == id) return;
    setState(() => _activeTab = id);
    _syncShellRouteForTab(id);
  }

  void _handleTabSwipeDragEnd(DragEndDetails details) {
    final direction = TabSwipeSwitchRegion.directionFromDragEnd(details);
    if (direction == null) {
      return;
    }
    _handleTabSwipe(direction);
  }

  void _handleTabSwipe(TabSwipeDirection direction) {
    final currentIndex = _tabOrder.indexOf(_activeTab);
    if (currentIndex < 0) {
      return;
    }
    final nextIndex = currentIndex + direction.delta;
    if (nextIndex < 0 || nextIndex >= _tabOrder.length) {
      return;
    }
    _handleTabChange(_tabOrder[nextIndex]);
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final safeTop = MediaQuery.viewPaddingOf(context).top;
    final effectiveTopInset = AppSpacing.appChromeTopSafeInset(
      safeTop,
      context,
    );

    final isDark = ref.watch(isDarkProvider);
    final bg = AppColorsFunctional.getColor(isDark, ColorType.pageBackground);
    final borderColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.separatorSubtle,
    );

    return CupertinoPageScaffold(
      backgroundColor: bg,
      child: Material(
        type: MaterialType.transparency,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            SizedBox(height: effectiveTopInset),
            Container(
              height:
                  AppSpacing.appChromeTopBarHeight(context) +
                  AppSpacing.primaryTopBarHeight(context) +
                  AppSpacing.hairline,
              decoration: BoxDecoration(
                color: bg,
                border: Border(
                  bottom: BorderSide(
                    color: borderColor,
                    width: AppSpacing.hairline,
                  ),
                ),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  SizedBox(
                    height: AppSpacing.appChromeTopBarHeight(context),
                    child: Padding(
                      padding: EdgeInsets.symmetric(
                        horizontal: AppSpacing.feedContentHorizontal(context),
                      ),
                      child: const Center(
                        child: GlobalXiaoquSearchBar(
                          initialSearchScope: GlobalSearchScope.content,
                        ),
                      ),
                    ),
                  ),
                  SizedBox(
                    height: AppSpacing.primaryTopBarHeight(context),
                    child: Padding(
                      padding: EdgeInsets.symmetric(
                        horizontal: AppSpacing.feedContentHorizontal(context),
                      ),
                      child: HomePrimaryTabStrip(
                        activeTab: _activeTab,
                        onTabChange: _handleTabChange,
                        onHorizontalDragEnd: _handleTabSwipeDragEnd,
                        isDark: isDark,
                      ),
                    ),
                  ),
                ],
              ),
            ),
            Expanded(
              child: TabSwipeSwitchRegion(
                enabled: true,
                onSwipe: _handleTabSwipe,
                child: _buildBody(isDark),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildBody(bool isDark) {
    switch (_activeTab) {
      case HomePrimaryTabStrip.followingTabId:
        return _buildFeedTab(isDark, HomePrimaryTabStrip.followingTabId);
      case HomePrimaryTabStrip.recommendedTabId:
        return _buildFeedTab(isDark, 'moment');
      case HomePrimaryTabStrip.travelPhotographyTabId:
        return _buildFeedTab(isDark, HomePrimaryTabStrip.travelTabId);
      case HomePrimaryTabStrip.campusTabId:
        return _buildFeedTab(isDark, HomePrimaryTabStrip.campusTabId);
      case HomePrimaryTabStrip.travelTabId:
        return _buildFeedTab(isDark, HomePrimaryTabStrip.travelTabId);
      case HomePrimaryTabStrip.photographyTabId:
        return _buildFeedTab(isDark, HomePrimaryTabStrip.photographyTabId);
      case HomePrimaryTabStrip.techTabId:
        return _buildFeedTab(isDark, HomePrimaryTabStrip.techTabId);
      case HomePrimaryTabStrip.carFriendsTabId:
        return _buildFeedTab(isDark, HomePrimaryTabStrip.carFriendsTabId);
      default:
        return const SizedBox.shrink();
    }
  }

  Widget _buildFeedTab(bool isDark, String feedTabId) {
    final visualPriority = _isInlineImageCarouselTab(feedTabId);
    return MomentSocialFeed(
      isDark: isDark,
      feedTabId: feedTabId,
      inlineImageCarousel: visualPriority,
      disableImageViewerOnTap: visualPriority,
      onUserTap: _openUserProfile,
      onPostTap: (post, index, {feedPosts}) {
        _openFeedPost(post, index, feedPosts: feedPosts);
      },
    );
  }

  bool _isInlineImageCarouselTab(String feedTabId) {
    return feedTabId == HomePrimaryTabStrip.travelTabId ||
        feedTabId == HomePrimaryTabStrip.photographyTabId;
  }

  void _openUserProfile(
    String userId, {
    String? avatarUrl,
    String? displayName,
    String? backgroundUrl,
  }) {
    context.push(
      AppRoutePaths.userProfile(username: userId),
      extra: UserProfileRouteExtra(
        subAccountId: userId,
        avatar: avatarUrl,
        displayName: displayName,
        backgroundImage: backgroundUrl,
      ),
    );
  }

  Future<void> _openFeedPost(
    PostBaseDto post,
    int mediaIndex, {
    List<PostBaseDto>? feedPosts,
  }) async {
    final viewerPosts = (feedPosts ?? const <PostBaseDto>[])
        .where(_supportsUnifiedViewer)
        .toList(growable: false);
    if (viewerPosts.isEmpty) {
      return;
    }

    final navFeedRequestId = ref
        .read(feedSessionProvider.notifier)
        .newFeedRequestId();
    ref
        .read(behaviorRepositoryProvider)
        .reportSingle(
          contentId: post.id,
          action: BehaviorAction.click,
          authorId: post.authorId,
          referralSource: ReferralSource.organicFeed,
          feedRequestId: navFeedRequestId,
        );

    final rawPostsById = homeFollowingMediaViewerRaws(
      content: ref.read(contentRepositoryProvider),
      viewerPosts: viewerPosts,
    );
    final postViews = viewerPosts
        .map(
          (dto) => PostSummaryView.fromDto(
            dto,
            surfaceId: PostReadSurfaceId.immersive,
            wire: rawPostsById[dto.id]!.toDynamicMap(),
          ),
        )
        .toList(growable: false);
    final initialIndex = viewerPosts.isNotEmpty
        ? viewerPosts
              .indexWhere((item) => item.id == post.id)
              .clamp(0, viewerPosts.length - 1)
        : mediaIndex;
    final interactionSnapshot = buildMediaViewerInteractionSnapshot(
      posts: viewerPosts,
      discoveryState: ref.read(discoveryStateProvider),
      relationshipState: ref.read(userRelationshipStateProvider),
      postInteractionState: ref.read(postInteractionStateProvider),
    );
    primeMediaViewerInteractionSnapshot(ref, interactionSnapshot);
    final result = await context.push<Object?>(
      post.isVideoLike
          ? '/video-viewer/$initialIndex'
          : '/media-viewer/photo/$initialIndex',
      extra: MediaViewerExtra(
        posts: postViews,
        dtoPosts: viewerPosts,
        initialIndex: initialIndex,
        category: 'following',
        source: 'following',
        initialImageIndex: mediaIndex,
        rawPostsById: rawPostsById,
        interactionSnapshot: interactionSnapshot,
        feedRequestId: navFeedRequestId,
      ),
    );
    if (result is MediaViewerResult) {
      applyMediaViewerResultToInteractionState(ref, result);
    }
  }

  bool _supportsUnifiedViewer(PostBaseDto post) {
    return post.supportsUnifiedViewer;
  }
}

class HomeFeaturedImmersivePage extends ConsumerWidget {
  const HomeFeaturedImmersivePage({super.key, required this.onExitToHome});

  final VoidCallback onExitToHome;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final safeTop = MediaQuery.viewPaddingOf(context).top;
    final effectiveTopInset = AppSpacing.appChromeTopSafeInset(
      safeTop,
      context,
    );
    return CupertinoPageScaffold(
      backgroundColor: AppColors.black,
      child: Material(
        type: MaterialType.transparency,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            SizedBox(height: effectiveTopInset),
            Expanded(
              child: WorksImmersiveViewer(
                showWorksToolbar: true,
                topChromeSafeInset: AppSpacing.zero,
                onUserTap: (userId, {avatarUrl, displayName, backgroundUrl}) =>
                    _openUserProfile(
                      context,
                      userId,
                      avatarUrl: avatarUrl,
                      displayName: displayName,
                      backgroundUrl: backgroundUrl,
                    ),
                onAssistantTap: () => _openAssistantHalfSheet(context, ref),
                onTapBack: onExitToHome,
                onSwitchToMoment: onExitToHome,
                onSwitchToFollowing: onExitToHome,
                onSwitchToCircles: onExitToHome,
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _openUserProfile(
    BuildContext context,
    String userId, {
    String? avatarUrl,
    String? displayName,
    String? backgroundUrl,
  }) {
    context.push(
      AppRoutePaths.userProfile(username: userId),
      extra: UserProfileRouteExtra(
        subAccountId: userId,
        avatar: avatarUrl,
        displayName: displayName,
        backgroundImage: backgroundUrl,
      ),
    );
  }

  void _openAssistantHalfSheet(BuildContext context, WidgetRef ref) {
    final target = VisitTarget.page('home_featured');
    final service = ref.read(visitRecorderServiceProvider);
    final ctx = AssistantOpenContext(
      source: AssistantSource.discovery,
      tab: HomePrimaryTabStrip.featuredTabId,
      visitTarget: target,
      experienceLevel: service.getExperience(target),
    );
    AssistantHalfSheet.show(context, ctx);
  }
}
