import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Material, MaterialType;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/app_startup_runtime.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/components/navigation/home_primary_tab_strip.dart';
import 'package:quwoquan_app/components/navigation/tab_swipe_switch_region.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/models/assistant_open_context.dart';
import 'package:quwoquan_app/core/models/user_profile_route_extra.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/trackers/journey_event_tracker.dart';
import 'package:quwoquan_app/core/widgets/global_surface_actions.dart';
import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/ui/assistant/widgets/assistant_half_sheet.dart';
import 'package:quwoquan_app/ui/discovery/services/home_feed_post_open_action.dart';
import 'package:quwoquan_app/ui/discovery/providers/discovery_feed_provider.dart';
import 'package:quwoquan_app/ui/discovery/widgets/home_multi_form_feed.dart';
import 'package:quwoquan_app/ui/discovery/widgets/works_immersive_viewer.dart';

class HomePage extends ConsumerStatefulWidget {
  const HomePage({
    super.key,
    this.routeLocation,
    this.isStartupHomeActive = true,
  });

  final String? routeLocation;
  final bool isStartupHomeActive;

  @override
  ConsumerState<HomePage> createState() => _HomePageState();
}

class _HomePageState extends ConsumerState<HomePage>
    with AutomaticKeepAliveClientMixin {
  // 默认频道 = recommend（与 ContentUIConfig.homeChannels 首发推荐频道 id 对齐）。
  static const String _defaultChannelId = 'recommend';
  late String _activeChannelId;

  /// R20 · 页面级停留起点（进入首页时铸造），dispose 时上报停留时长。
  final DateTime _enteredAt = DateTime.now();

  /// R20 · 在 initState 捕获 tracker 实例，dispose 时复用，避免在 dispose 中
  /// 触碰 `ref`（Riverpod 在 widget 卸载阶段使用 ref 不安全）。
  late final JourneyEventTracker _journeyTracker;
  late final DiscoveryFeedMapNotifier _feedNotifier;
  int _activeChannelReconcileGeneration = 0;
  String? _pendingActiveChannelFallbackId;

  /// 频道顺序真相源 = homeChannelsProvider（端默认 + 远程覆盖），用于左右滑动切频道。
  List<String> _channelOrder() =>
      ref.read(homeChannelsProvider).map((channel) => channel.id).toList();

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _activeChannelId = _initialTabForRoute(widget.routeLocation);
    _journeyTracker = ref.read(journeyEventTrackerProvider);
    _feedNotifier = ref.read(discoveryFeedMapProvider.notifier);
    // R20 · 页面级曝光：首页进入即上报一次 enter（页面级停留漏斗起点）。
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _journeyTracker.trackAction(
        journey: 'home',
        action: 'enter',
        pageName: 'HomePage',
        payload: <String, Object?>{'channelId': _activeChannelId},
      );
    });
  }

  @override
  void dispose() {
    _feedNotifier.cancelChannelRequests(_activeChannelId);
    // R20 · 页面级停留：离开首页时上报停留时长（含异常退出路径）。
    // 使用 initState 捕获的 tracker 实例，禁止在 dispose 中读取 `ref`。
    _journeyTracker.trackAction(
      journey: 'home',
      action: 'exit',
      pageName: 'HomePage',
      payload: <String, Object?>{
        'channelId': _activeChannelId,
        'durationMs': DateTime.now().difference(_enteredAt).inMilliseconds,
      },
    );
    super.dispose();
  }

  @override
  void didUpdateWidget(HomePage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.isStartupHomeActive && !widget.isStartupHomeActive) {
      // HomePage 位于 shell 的 IndexedStack，切到其它主 Tab 时不会 dispose。
      // 主动终止当前频道请求；build 随后卸载 feed surface，释放媒体资源，
      // provider 正文与 container-scoped 滚动锚点仍保留供返回时恢复。
      _feedNotifier.deactivateChannel(_activeChannelId);
    }
    if (oldWidget.routeLocation == widget.routeLocation) {
      return;
    }
    final routeTab = _routeDrivenTab(widget.routeLocation);
    if (routeTab == null || routeTab == _activeChannelId) {
      return;
    }
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _feedNotifier.deactivateChannel(_activeChannelId);
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

  /// 远端频道配置可在本页存活期间替换。build 只计算展示用 fallback，真正的
  /// lifecycle 状态必须在 frame 结束后同步，避免 build 期间 setState。
  ///
  /// callback 执行前重新读取频道真相源：若用户/路由已经切到合法频道，或配置
  /// 再次变化，则不覆盖更新后的选择；否则使用当下首频道并回收旧频道请求。
  void _scheduleActiveChannelReconciliation(String fallbackChannelId) {
    if (_activeChannelId == fallbackChannelId ||
        _pendingActiveChannelFallbackId == fallbackChannelId) {
      return;
    }
    _pendingActiveChannelFallbackId = fallbackChannelId;
    final generation = ++_activeChannelReconcileGeneration;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || generation != _activeChannelReconcileGeneration) {
        return;
      }
      _pendingActiveChannelFallbackId = null;
      final currentOrder = _channelOrder();
      if (currentOrder.isEmpty || currentOrder.contains(_activeChannelId)) {
        return;
      }
      final validatedFallbackChannelId = currentOrder.first;
      final removedChannelId = _activeChannelId;
      _feedNotifier.deactivateChannel(removedChannelId);
      setState(() {
        _activeChannelId = validatedFallbackChannelId;
      });
      _syncShellRouteForTab(validatedFallbackChannelId);
    });
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
      ref
          .read(authContinuationProvider.notifier)
          .set(
            const OpenHomeChannelContinuation(
              channelId: HomePrimaryTabStrip.followingChannelId,
            ),
          );
      unawaited(
        requireLogin(
          ref,
          context,
          AuthGateReason.followingFeed,
          redirect: AppRoutePaths.home,
          dismissFallback: AppRoutePaths.home,
          dismissPolicy: LoginDismissPolicy.safeFallback,
        ),
      );
      return;
    }
    _feedNotifier.deactivateChannel(_activeChannelId);
    setState(() => _activeChannelId = id);
    _syncShellRouteForTab(id);
  }

  void _resumeHomeChannelContinuation() {
    final pending = ref
        .read(authContinuationProvider.notifier)
        .take<OpenHomeChannelContinuation>();
    if (pending == null ||
        pending.channelId != HomePrimaryTabStrip.followingChannelId ||
        !mounted) {
      return;
    }
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      if (_activeChannelId != pending.channelId) {
        _feedNotifier.deactivateChannel(_activeChannelId);
        setState(() => _activeChannelId = pending.channelId);
      }
      _syncShellRouteForTab(pending.channelId);
    });
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
    ref.listen<AuthSessionState>(authSessionControllerProvider, (
      AuthSessionState? previous,
      AuthSessionState next,
    ) {
      final justLoggedIn =
          next.isAuthenticated &&
          (previous == null || !previous.isAuthenticated);
      if (justLoggedIn) {
        _resumeHomeChannelContinuation();
      }
    });
    if (ref.watch(authSessionControllerProvider).isAuthenticated) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) {
          _resumeHomeChannelContinuation();
        }
      });
    }
    final safeTop = MediaQuery.viewPaddingOf(context).top;
    final effectiveTopInset = safeTop + AppSpacing.intraGroupXs;

    final isDark = ref.watch(isDarkProvider);
    final channels = ref.watch(homeChannelsProvider);
    // 守护远程覆盖后当前频道可能被移除：回退到第一个频道，避免空白页。
    final effectiveActiveChannelId =
        channels.any((channel) => channel.id == _activeChannelId)
        ? _activeChannelId
        : (channels.isNotEmpty ? channels.first.id : _activeChannelId);
    if (effectiveActiveChannelId != _activeChannelId) {
      _scheduleActiveChannelReconciliation(effectiveActiveChannelId);
    }
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
                  child: widget.isStartupHomeActive
                      ? _buildBody(isDark, channels, effectiveActiveChannelId)
                      : const SizedBox.shrink(),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  /// 按频道 template 路由到 Feed 模板组件（去硬编码 switch）；
  /// channelId = channel.id（取数/气质文案/桶 key 真相源），template 驱动单列/多列/发现交集流。
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
    return HomeMultiFormFeed(
      key: ValueKey<String>('home-feed-${channel.id}'),
      isDark: isDark,
      channelId: channel.id,
      template: channel.template,
      onInitialContentPainted:
          activeChannelId == _defaultChannelId && widget.isStartupHomeActive
          ? _markStartupHomeFeedContentPainted
          : null,
      onUserTap: _openUserProfile,
      onPostTap: (post, index, {feedPosts}) {
        _openFeedPost(post, index, feedPosts: feedPosts);
      },
    );
  }

  void _markStartupHomeFeedContentPainted() {
    if (!mounted ||
        _activeChannelId != _defaultChannelId ||
        !widget.isStartupHomeActive) {
      return;
    }
    AppStartupRuntime.instance.markHomeFeedContentPainted();
  }

  void _openUserProfile(
    String userId, {
    String? avatarUrl,
    String? displayName,
    String? backgroundUrl,
  }) {
    context.push(
      AppRoutePaths.userProfile(userHandle: userId),
      extra: UserProfileRouteExtra(
        personaId: userId,
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
  }) {
    // post → 沉浸 viewer 的统一动作（移动端 / Web 壳共用），保证归因链与
    // MediaViewerExtra 构造同源。
    return openHomeFeedPost(
      context,
      ref,
      post: post,
      mediaIndex: mediaIndex,
      channelId: _activeChannelId,
      feedPosts: feedPosts,
    );
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
      AppRoutePaths.userProfile(userHandle: userId),
      extra: UserProfileRouteExtra(
        personaId: userId,
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
    unawaited(AssistantHalfSheet.show(context, ctx));
  }
}
