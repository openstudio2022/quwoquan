import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/components/navigation/centered_scrollable_tab_bar.dart';
import 'package:quwoquan_app/components/navigation/tab_navigation.dart';
import 'package:quwoquan_app/components/navigation/tab_swipe_switch_region.dart';
import 'package:quwoquan_app/core/models/assistant_open_context.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/models/user_profile_route_extra.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/global_surface_actions.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/ui/assistant/widgets/assistant_half_sheet.dart';
import 'package:quwoquan_app/ui/content/post_summary_view.dart';
import 'package:quwoquan_app/ui/circle/pages/home_circles_hub_page.dart';
import 'package:quwoquan_app/ui/discovery/widgets/moment_social_feed.dart';
import 'package:quwoquan_app/ui/discovery/widgets/works_immersive_viewer.dart';

class HomePage extends ConsumerStatefulWidget {
  const HomePage({super.key});

  @override
  ConsumerState<HomePage> createState() => _HomePageState();
}

class _HomePageState extends ConsumerState<HomePage>
    with AutomaticKeepAliveClientMixin {
  static const String _defaultTab =
      'circles'; // Change default to circles to avoid starting in immersive mode without nav
  static const List<String> _tabOrder = <String>[
    'following',
    'featured',
    'circles',
  ];
  String _activeTab = _defaultTab;
  String _lastNonFeaturedTab = _defaultTab;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    // Ensure state consistency on load
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _updateImmersiveState();
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
        backgroundColor: Colors.black, // Immersive background
        child: Material(
          type: MaterialType.transparency,
          child: WorksImmersiveViewer(
            showWorksToolbar: true,
            onUserTap: _openUserProfile,
            onAssistantTap: _openAssistantHalfSheet,
            onTapBack: _handleFeaturedBack,
            // 兼容已有入口：直接切回常规首页态
            onSwitchToMoment: () => _handleTabChange('circles'),
            // 顶部导航回调
            onSwitchToFollowing: () => _handleTabChange('following'),
            onSwitchToCircles: () => _handleTabChange('circles'),
          ),
        ),
      );
    }

    // 常规模式
    final isDark = ref.watch(isDarkProvider);
    final bg = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final tabs = const <TabItem>[
      TabItem(id: 'following', label: UITextConstants.homeTabFollowing),
      TabItem(id: 'featured', label: UITextConstants.homeTabFeatured),
      TabItem(id: 'circles', label: UITextConstants.homeTabCircles),
    ];

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
                      color: fgSecondary.withValues(alpha: 0.15),
                    ),
                  ),
                ),
                child: Stack(
                  children: [
                    // Layer 1: Absolutely Centered Tabs
                    Positioned.fill(
                      child: Center(
                        child: CenteredScrollableTabBar(
                          tabs: tabs,
                          activeTab: _activeTab,
                          onTabChange: _handleTabChange,
                          onHorizontalDragEnd: _handleTabSwipeDragEnd,
                          // Remove actions from here to ensure centering
                          leadingActions: const [],
                          trailingActions: const [],
                          // Ensure background is transparent so it doesn't cover actions if expanding
                          transparentBackground: true,
                        ),
                      ),
                    ),
                    // Layer 2: Trailing Actions
                    Positioned(
                      right:
                          AppSpacing.feedContentHorizontal(context) -
                          AppSpacing.intraGroupXs,
                      top: 0,
                      bottom: 0,
                      child: const Center(
                        child: GlobalTopActions(
                          initialSearchScope: GlobalSearchScope.content,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              Expanded(
                child: TabSwipeSwitchRegion(
                  enabled: _activeTab != 'circles',
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
      case 'circles':
        return HomeCirclesHubPage(onPrimaryOverflowSwipe: _handleTabSwipe);
      case 'featured':
        // This case is handled in the main build method now for full screen
        return const SizedBox.shrink();
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

  Map<String, dynamic>? _rawDiscoveryPostById(String postId) {
    final repo = ref.read(appContentRepositoryProvider);
    final all = <Map<String, dynamic>>[
      ...repo.discoveryPhotoData,
      ...repo.discoveryVideoData,
      ...repo.discoveryArticleData,
      ...repo.discoveryMomentData,
    ];
    for (final item in all) {
      final itemId =
          item['postId']?.toString() ??
          item['_id']?.toString() ??
          item['id']?.toString() ??
          '';
      if (itemId == postId) {
        return item;
      }
    }
    return null;
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
        rawPostsById: <String, Map<String, dynamic>>{
          for (final item in viewerPosts)
            item.id: _rawDiscoveryPostById(item.id) ?? item.toMap(),
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
      ref.read(discoveryStateProvider).applyMediaViewerResult(result);
    }
  }

  bool _supportsUnifiedViewer(PostBaseDto post) {
    return post.supportsUnifiedViewer;
  }
}
