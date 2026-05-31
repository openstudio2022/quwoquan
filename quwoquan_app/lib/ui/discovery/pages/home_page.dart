import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Material, MaterialType;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/components/navigation/home_primary_tab_strip.dart';
import 'package:quwoquan_app/components/navigation/tab_swipe_switch_region.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/models/assistant_open_context.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/models/user_profile_route_extra.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/ui/discovery/services/home_feed_media_viewer_wiring.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/global_surface_actions.dart';
import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/ui/discovery/widgets/unified_object_card.dart';
import 'package:quwoquan_app/ui/assistant/widgets/assistant_half_sheet.dart';
import 'package:quwoquan_app/ui/content/media_viewer_interaction_bridge.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view_mapper.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart'
    show BehaviorAction, ReferralSource;
import 'package:quwoquan_app/core/providers/feed_session_provider.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
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
  // 默认频道 = recommend（与 ContentUIConfig.homeChannels 首发推荐频道 id 对齐）。
  static const String _defaultChannelId = 'recommend';
  late String _activeChannelId;

  /// 频道顺序真相源 = homeChannelsProvider（端默认 + 远程覆盖），用于左右滑动切频道。
  List<String> _channelOrder() =>
      ref.read(homeChannelsProvider).map((channel) => channel.id).toList();

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _activeChannelId = _initialTabForRoute(widget.routeLocation);
  }

  @override
  void didUpdateWidget(HomePage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.routeLocation == widget.routeLocation) {
      return;
    }
    final routeTab = _routeDrivenTab(widget.routeLocation);
    if (routeTab == null || routeTab == _activeChannelId) {
      return;
    }
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      setState(() {
        _activeChannelId = routeTab;
      });
    });
  }

  String _initialTabForRoute(String? location) {
    return _routeDrivenTab(location) ?? _defaultChannelId;
  }

  String? _routeDrivenTab(String? location) {
    switch (location) {
      case AppRoutePaths.home:
        return _defaultChannelId;
      case '/following':
        return HomePrimaryTabStrip.followingChannelId;
      default:
        return null;
    }
  }

  void _syncShellRouteForTab(String id) {
    final targetLocation = switch (id) {
      HomePrimaryTabStrip.followingChannelId => AppRoutePaths.home,
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

  void _handleChannelChange(String id) {
    if (_activeChannelId == id) return;
    // 关注频道展示「关注的人」的内容，游客需先登录；未登录时提示并引导登录，
    // 保持当前频道不变（不切到空白的关注流）。
    if (id == HomePrimaryTabStrip.followingChannelId &&
        !AuthGate.isAuthenticated(ref)) {
      unawaited(requireLogin(ref, context, AuthGateReason.followingFeed));
      return;
    }
    setState(() => _activeChannelId = id);
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
    final order = _channelOrder();
    final currentIndex = order.indexOf(_activeChannelId);
    if (currentIndex < 0) {
      return;
    }
    final nextIndex = currentIndex + direction.delta;
    if (nextIndex < 0 || nextIndex >= order.length) {
      return;
    }
    _handleChannelChange(order[nextIndex]);
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final safeTop = MediaQuery.viewPaddingOf(context).top;
    final effectiveTopInset = safeTop + AppSpacing.intraGroupXs;

    final isDark = ref.watch(isDarkProvider);
    final channels = ref.watch(homeChannelsProvider);
    // 守护远程覆盖后当前频道可能被移除：回退到第一个频道，避免空白页。
    final effectiveActiveChannelId =
        channels.any((channel) => channel.id == _activeChannelId)
        ? _activeChannelId
        : (channels.isNotEmpty ? channels.first.id : _activeChannelId);
    final bg = SettingsSemanticConstants.conversationSheetCardSurface(isDark);
    final searchChromeColor = isDark ? bg : AppColors.primaryColor;
    final searchChromeSurface = AppChromeSurface.immersive;
    final searchToTabGap = AppSpacing.intraGroupXs;
    final statusBarStyle = SystemUiOverlayStyle(
      statusBarColor: AppColors.transparent,
      statusBarIconBrightness: Brightness.light,
      statusBarBrightness: Brightness.dark,
      systemNavigationBarColor: AppColors.transparent,
      systemNavigationBarIconBrightness: isDark
          ? Brightness.light
          : Brightness.dark,
    );

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: statusBarStyle,
      child: CupertinoPageScaffold(
        backgroundColor: bg,
        child: Material(
          type: MaterialType.transparency,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Container(
                key: const ValueKey<String>('home-search-chrome'),
                height:
                    effectiveTopInset +
                    AppSpacing.globalSearchFieldHeight +
                    searchToTabGap,
                padding: EdgeInsets.only(top: effectiveTopInset),
                color: searchChromeColor,
                child: Align(
                  alignment: Alignment.topCenter,
                  child: Padding(
                    padding: EdgeInsets.symmetric(
                      horizontal: AppSpacing.feedContentHorizontal(context),
                    ),
                    child: GlobalXiaoquSearchBar(
                      initialSearchScope: GlobalSearchScope.content,
                      surface: searchChromeSurface,
                    ),
                  ),
                ),
              ),
              Container(
                key: const ValueKey<String>('home-primary-tab-chrome'),
                height: AppSpacing.primaryTopBarHeight(context),
                decoration: BoxDecoration(color: bg),
                child: SizedBox(
                  height: AppSpacing.primaryTopBarHeight(context),
                  child: Padding(
                    padding: EdgeInsets.symmetric(
                      horizontal: AppSpacing.feedContentHorizontal(context),
                    ),
                    child: HomePrimaryTabStrip(
                      activeChannelId: effectiveActiveChannelId,
                      onChannelChanged: _handleChannelChange,
                      onHorizontalDragEnd: _handleTabSwipeDragEnd,
                      isDark: isDark,
                      channels: channels,
                    ),
                  ),
                ),
              ),
              Expanded(
                child: TabSwipeSwitchRegion(
                  enabled: true,
                  onSwipe: _handleTabSwipe,
                  child: _buildBody(isDark, channels, effectiveActiveChannelId),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  /// 按频道 template 路由到 Feed 模板组件（去硬编码 switch）；
  /// channelId = channel.id（取数/气质文案/桶 key 真相源），template 驱动单列/多列/今日交集流。
  Widget _buildBody(
    bool isDark,
    List<HomeChannelConfig> channels,
    String activeChannelId,
  ) {
    HomeChannelConfig? channel;
    for (final candidate in channels) {
      if (candidate.id == activeChannelId) {
        channel = candidate;
        break;
      }
    }
    if (channel == null) {
      return const SizedBox.shrink();
    }
    return MomentSocialFeed(
      key: ValueKey<String>('home-feed-${channel.id}'),
      isDark: isDark,
      channelId: channel.id,
      template: channel.template,
      onUserTap: _openUserProfile,
      onPostTap: (post, index, {feedPosts}) {
        _openFeedPost(post, index, feedPosts: feedPosts);
      },
      onIntersectionObjectOpen: _openIntersectionObject,
      onIntersectionObjectAction: _handleIntersectionObjectAction,
    );
  }

  /// 今日交集对象卡行动按钮（关注/加入/加好友）：交集行动回流。
  /// 带 intersectionDimension + intersectionTagRefs，便于推荐归因还原交集来源。
  void _handleIntersectionObjectAction(IntersectionReason reason) {
    final targetId = reason.actionTargetId.trim();
    if (targetId.isEmpty) return;
    ref
        .read(contentBehaviorTrackerProvider)
        .trackFollow(
          targetId,
          referralSource: ReferralSource.organicFeed,
          feedRequestId: ref
              .read(feedSessionProvider.notifier)
              .currentFeedRequestId,
          intersectionDimension: reason.dimension,
          intersectionTagRefs: reason.tagRefs,
        );
    // 行动回流后跳到对象页，让用户完成实际关注/加入（关系写入归属对象页）。
    _openIntersectionObject(reason);
  }

  /// 今日交集对象卡跳转：按对象类型路由到对应对象/聚合页。
  /// 路由全部来自 metadata codegen（[AppRoutePaths]），不在此硬编码 path。
  void _openIntersectionObject(IntersectionReason reason) {
    final targetId = reason.actionTargetId.trim();
    if (targetId.isEmpty) return;
    final kind = UnifiedObjectKind.fromRelationKind(reason.relationKind);
    switch (kind) {
      case UnifiedObjectKind.person:
        context.push(AppRoutePaths.userProfile(username: targetId));
      case UnifiedObjectKind.circle:
        context.push(AppRoutePaths.circleDetail(id: targetId));
      case UnifiedObjectKind.place:
      case UnifiedObjectKind.org:
        context.push(AppRoutePaths.homepageDetail(id: targetId));
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
    // 入口 post 在 feed 中的位置（推荐归因；-1 → null 不上报）。
    final feedPosition = (feedPosts ?? const <PostBaseDto>[]).indexWhere(
      (item) => item.id == post.id,
    );
    ref
        .read(behaviorRepositoryProvider)
        .reportSingle(
          contentId: post.id,
          action: BehaviorAction.click,
          authorId: post.authorId,
          referralSource: ReferralSource.organicFeed,
          feedRequestId: navFeedRequestId,
          position: feedPosition >= 0 ? feedPosition : null,
        );

    final rawPostsById = homeFollowingMediaViewerRaws(
      content: ref.read(contentRepositoryProvider),
      viewerPosts: viewerPosts,
    );
    final postViews = viewerPosts
        .map(
          (dto) => ContentSurfaceViewMapper.fromDto(
            dto,
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
        position: feedPosition >= 0 ? feedPosition : null,
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
        child: WorksImmersiveViewer(
          showWorksToolbar: true,
          topChromeSafeInset: effectiveTopInset,
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
      tab: HomePrimaryTabStrip.featuredChannelId,
      visitTarget: target,
      experienceLevel: service.getExperience(target),
    );
    AssistantHalfSheet.show(context, ctx);
  }
}
