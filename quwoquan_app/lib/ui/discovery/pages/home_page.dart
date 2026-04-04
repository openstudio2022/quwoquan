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
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/global_surface_actions.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/ui/content/entry/widgets/create_action_sheet.dart';
import 'package:quwoquan_app/ui/assistant/widgets/assistant_half_sheet.dart';
import 'package:quwoquan_app/ui/circle/pages/circles_hub_page.dart';
import 'package:quwoquan_app/ui/content/post_summary_view.dart';
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
  static const String _defaultTab = 'following';
  static const List<String> _tabOrder = <String>[
    'following',
    'featured',
    'circles',
  ];
  late String _activeTab;
  late String _lastNonFeaturedTab;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _activeTab = _initialTabForRoute(widget.routeLocation);
    _lastNonFeaturedTab = _activeTab == 'featured' ? _defaultTab : _activeTab;
    // Ensure state consistency on load
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _updateImmersiveState();
    });
  }

  @override
  void didUpdateWidget(HomePage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.routeLocation == widget.routeLocation) {
      return;
    }
    final routeTab = _routeDrivenTab(widget.routeLocation);
    if (routeTab == null ||
        _activeTab == 'featured' ||
        routeTab == _activeTab) {
      return;
    }
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      setState(() {
        _activeTab = routeTab;
        _lastNonFeaturedTab = routeTab;
      });
      _updateImmersiveState();
    });
  }

  String _initialTabForRoute(String? location) {
    return _routeDrivenTab(location) ?? _defaultTab;
  }

  String? _routeDrivenTab(String? location) {
    switch (location) {
      case AppRoutePaths.home:
        return 'following';
      default:
        return null;
    }
  }

  void _syncShellRouteForTab(String id) {
    final targetLocation = switch (id) {
      'following' => AppRoutePaths.home,
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
    if (id == 'featured' && _activeTab != 'featured') {
      _lastNonFeaturedTab = _activeTab;
    } else if (id != 'featured') {
      _lastNonFeaturedTab = id;
    }
    setState(() => _activeTab = id);
    _syncShellRouteForTab(id);
    _updateImmersiveState();
  }

  void _handleFeaturedBack() {
    final nextTab = _lastNonFeaturedTab == 'featured'
        ? _defaultTab
        : _lastNonFeaturedTab;
    _handleTabChange(nextTab);
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

  void _updateImmersiveState() {
    final isImmersive = _activeTab == 'featured';
    // Use Future.microtask to avoid build conflicts if called during build
    Future.microtask(() {
      if (!mounted) return;
      ref.read(bottomNavHiddenProvider.notifier).setHidden(isImmersive);
      ref.read(videoForceDarkProvider.notifier).setForceDark(isImmersive);
    });
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);

    // 沉浸式模式（精品页）直接返回全屏 Viewer
    if (_activeTab == 'featured') {
      return CupertinoPageScaffold(
        backgroundColor: AppColors.black,
        // 与 AppScaffold 一致：Cupertino 壳下补透明 Material，避免 Text 继承到错误的
        // DefaultTextStyle/Material 回退样式（真机易出现黄色下划线等强调线）。
        child: Material(
          type: MaterialType.transparency,
          child: WorksImmersiveViewer(
            showWorksToolbar: true,
            onUserTap: _openUserProfile,
            onAssistantTap: _openAssistantHalfSheet,
            onTapBack: _handleFeaturedBack,
            onSwitchToMoment: () => _handleTabChange('following'),
            onSwitchToFollowing: () => _handleTabChange('following'),
            onSwitchToCircles: () => _handleTabChange('circles'),
          ),
        ),
      );
    }

    // 常规模式
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
        child: SafeArea(
          bottom: false,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Container(
                height: AppSpacing.tabNavigationHeight,
                decoration: BoxDecoration(
                  color: bg,
                  border: Border(
                    bottom: BorderSide(
                      color: borderColor,
                      width: AppSpacing.hairline,
                    ),
                  ),
                ),
                child: Stack(
                  children: [
                    Positioned.fill(
                      child: Center(
                        child: HomePrimaryTabStrip(
                          activeTab: _activeTab,
                          onTabChange: _handleTabChange,
                          onHorizontalDragEnd: _handleTabSwipeDragEnd,
                          isDark: isDark,
                        ),
                      ),
                    ),
                    Positioned(
                      right: AppSpacing.topBarTrailingButtonInset(context),
                      top: 0,
                      bottom: 0,
                      child: const Center(
                        child: GlobalTopActions(
                          initialSearchScope: GlobalSearchScope.content,
                          quickActionPriority:
                              CreateActionSheetPriority.createPrimary,
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
      ),
    );
  }

  Widget _buildBody(bool isDark) {
    switch (_activeTab) {
      case 'following':
        return MomentSocialFeed(
          isDark: isDark,
          feedTabId: 'following',
          onUserTap: _openUserProfile,
          onPostTap: (post, index, {feedPosts}) {
            _openFeedPost(post, index, feedPosts: feedPosts);
          },
        );
      case 'featured':
        // This case is handled in the main build method now for full screen
        return const SizedBox.shrink();
      case 'circles':
        return CirclesHubPage(onPrimaryOverflowSwipe: _handleTabSwipe);
      default:
        return const SizedBox.shrink();
    }
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
        profileSubjectId: userId,
        avatar: avatarUrl,
        displayName: displayName,
        backgroundImage: backgroundUrl,
      ),
    );
  }

  void _openAssistantHalfSheet() {
    final target = VisitTarget.page('home_$_activeTab');
    final service = ref.read(visitRecorderServiceProvider);
    final ctx = AssistantOpenContext(
      source: AssistantSource.discovery,
      tab: _activeTab,
      visitTarget: target,
      experienceLevel: service.getExperience(target),
    );
    AssistantHalfSheet.show(context, ctx);
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
    final postViews = viewerPosts
        .map(PostSummaryView.fromDto)
        .toList(growable: false);
    final initialIndex = viewerPosts.isNotEmpty
        ? viewerPosts
              .indexWhere((item) => item.id == post.id)
              .clamp(0, viewerPosts.length - 1)
        : mediaIndex;
    final discoveryState = ref.read(discoveryStateProvider);
    final relationshipState = ref.read(userRelationshipStateProvider);
    final postInteractionState = ref.read(postInteractionStateProvider);
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
        rawPostsById: <String, Map<String, Object?>>{
          for (final item in viewerPosts)
            item.id: Map<String, Object?>.from(
              ref
                      .read(appContentRepositoryProvider)
                      .discoveryFeedWireRowByPostId(item.id) ??
                  item.toMap(),
            ),
        },
        interactionSnapshot: MediaViewerInteractionSnapshot(
          followingUsers: Set<String>.from(
            relationshipState.followingProfileIds.isEmpty
                ? discoveryState.followingUsers
                : relationshipState.followingProfileIds,
          ),
          likedPosts: Set<String>.from(
            postInteractionState.likedPostIds.isEmpty
                ? discoveryState.likedPosts
                : postInteractionState.likedPostIds,
          ),
          savedPosts: Set<String>.from(
            postInteractionState.savedPostIds.isEmpty
                ? discoveryState.savedPosts
                : postInteractionState.savedPostIds,
          ),
          postLikesCount: {
            for (final item in viewerPosts)
              item.id: postInteractionState.likeCountFor(
                item.id,
                fallback: discoveryState.getPostLikesCount(item.id) > 0
                    ? discoveryState.getPostLikesCount(item.id)
                    : item.likeCount,
              ),
          },
          postBookmarksCount: {
            for (final item in viewerPosts)
              item.id: postInteractionState.bookmarkCountFor(
                item.id,
                fallback: discoveryState.getPostBookmarksCount(item.id) > 0
                    ? discoveryState.getPostBookmarksCount(item.id)
                    : item.favoriteCount,
              ),
          },
          postSharesCount: {
            for (final item in viewerPosts)
              item.id: postInteractionState.shareCountFor(
                item.id,
                fallback: discoveryState.getPostSharesCount(item.id) > 0
                    ? discoveryState.getPostSharesCount(item.id)
                    : item.shareCount,
              ),
          },
        ),
      ),
    );
    if (result is MediaViewerResult) {
      ref
          .read(userRelationshipStateProvider.notifier)
          .applyViewerResult(result);
      ref.read(postInteractionStateProvider.notifier).applyViewerResult(result);
      ref.read(discoveryStateProvider.notifier).applyMediaViewerResult(result);
    }
  }

  bool _supportsUnifiedViewer(PostBaseDto post) {
    return post.supportsUnifiedViewer;
  }
}
