import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Material, MaterialType;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/startup/app_startup_runtime.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/home_featured_immersive_page.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/home_primary_tab_strip.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/navigation/tab_swipe_switch_region.dart';
import 'package:quwoquan_app/design_system/semantics/settings_semantic_constants.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/user_profile_route_extra.dart';
import 'package:quwoquan_app/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/runtime/auth/auth_continuation.dart';
import 'package:quwoquan_app/runtime/auth/auth_gate.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart'
    show journeyEventTrackerProvider;
import 'package:quwoquan_app/runtime/di/app_providers_content_runtime.dart'
    show AppRemoteConfigNotifier, appRemoteConfigProvider, homeChannelsProvider;
import 'package:quwoquan_app/runtime/di/ops_event_dependencies.dart'
    show appTelemetryContextProvider;
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart'
    show runtimeFailureFromError;
import 'package:quwoquan_app/runtime/observability/trackers/journey_event_tracker.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/home_feed_post_open_action.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/discovery_feed_provider.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/home_multi_form_feed.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

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
    with AutomaticKeepAliveClientMixin, WidgetsBindingObserver {
  // 默认频道 = recommend（与 ContentUIConfig.homeChannels 首发推荐频道 id 对齐）。
  static const String _defaultChannelId = 'recommend';
  late String _activeChannelId;

  /// R20 · 页面级停留起点（进入首页时铸造），dispose 时上报停留时长。
  final DateTime _enteredAt = DateTime.now();

  /// R20 · 在 initState 捕获 tracker 实例，dispose 时复用，避免在 dispose 中
  /// 触碰 `ref`（Riverpod 在 widget 卸载阶段使用 ref 不安全）。
  late final JourneyEventTracker _journeyTracker;
  late final DiscoveryFeedMapNotifier _feedNotifier;
  late final AppRemoteConfigNotifier _remoteConfigNotifier;
  late final ProviderSubscription<Map<String, AsyncValue<DiscoveryFeedState>>>
  _feedStateSubscription;
  StreamSubscription<String>? _networkSubscription;
  final Map<String, Object> _automaticRecoveryConsumedErrors =
      <String, Object>{};
  final Set<String> _automaticRecoveryInFlightChannels = <String>{};
  bool _wasBackgrounded = false;
  int _activeChannelReconcileGeneration = 0;
  int _surfaceActivityGeneration = 0;
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
    _remoteConfigNotifier = ref.read(appRemoteConfigProvider.notifier);
    _feedStateSubscription = ref.listenManual(discoveryFeedMapProvider, (
      previous,
      next,
    ) {
      for (final channelId in _automaticRecoveryConsumedErrors.keys.toList()) {
        if (_automaticRecoveryInFlightChannels.contains(channelId)) {
          continue;
        }
        if (next[channelId]?.value?.blockingError == null) {
          _automaticRecoveryConsumedErrors.remove(channelId);
        }
      }
    }, fireImmediately: true);
    WidgetsBinding.instance.addObserver(this);
    _networkSubscription = ref
        .read(appTelemetryContextProvider)
        .networkChanges
        .listen((networkClass) {
          if (networkClass != 'none') {
            unawaited(_recoverActiveChannelOnce());
          }
        });
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
    WidgetsBinding.instance.removeObserver(this);
    _feedStateSubscription.close();
    unawaited(_networkSubscription?.cancel());
    _surfaceActivityGeneration += 1;
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
  void didChangeAppLifecycleState(AppLifecycleState state) {
    switch (state) {
      case AppLifecycleState.paused:
      case AppLifecycleState.hidden:
      case AppLifecycleState.detached:
        _wasBackgrounded = true;
        return;
      case AppLifecycleState.inactive:
        return;
      case AppLifecycleState.resumed:
        if (!_wasBackgrounded) {
          return;
        }
        _wasBackgrounded = false;
        unawaited(_recoverActiveChannelOnce());
        return;
    }
  }

  Future<void> _recoverActiveChannelOnce() async {
    if (!mounted || !widget.isStartupHomeActive) {
      return;
    }
    final channelId = _activeChannelId;
    final current = ref.read(discoveryFeedMapProvider)[channelId]?.value;
    final error = current?.items.isEmpty == true
        ? current?.blockingError
        : null;
    if (error == null || !_isAutomaticRecoveryCandidate(error)) {
      return;
    }
    if (identical(_automaticRecoveryConsumedErrors[channelId], error) ||
        !_automaticRecoveryInFlightChannels.add(channelId)) {
      return;
    }
    _automaticRecoveryConsumedErrors[channelId] = error;
    try {
      // 配置与 feed 在冷启动时可能同时失败。先重取幂等 GetAppConfig，再以最新
      // 频道路由重取 GetFeed；同一阻断态只消费一次自动恢复机会，失败后仍保留
      // 显式错误与手动重试，不因 connectivity 抖动形成轮询风暴。
      await _remoteConfigNotifier.refresh();
      if (!mounted ||
          !widget.isStartupHomeActive ||
          channelId != _activeChannelId) {
        return;
      }
      final result = await _feedNotifier.load(channelId, force: true);
      if (!mounted) {
        return;
      }
      if (result.terminal == DiscoveryFeedLoadTerminal.content ||
          result.terminal == DiscoveryFeedLoadTerminal.canonicalEmpty ||
          result.terminal == DiscoveryFeedLoadTerminal.retainedContent) {
        _automaticRecoveryConsumedErrors.remove(channelId);
      } else if (result.terminal == DiscoveryFeedLoadTerminal.stillBlocked) {
        final latestError = ref
            .read(discoveryFeedMapProvider)[channelId]
            ?.value
            ?.blockingError;
        if (latestError != null) {
          // 自动 retry 可能生成新的 request/trace/failure 对象；仍把它视为同一
          // 自动恢复尝试的终态，避免下一次 connectivity 抖动立即再次放大。
          _automaticRecoveryConsumedErrors[channelId] = latestError;
        }
      }
    } finally {
      _automaticRecoveryInFlightChannels.remove(channelId);
    }
  }

  bool _isAutomaticRecoveryCandidate(Object error) {
    final failure = runtimeFailureFromError(error);
    if (failure == null || failure.nature != RuntimeFailureNature.transient) {
      return false;
    }
    return failure.kind == RuntimeFailureKind.network ||
        failure.kind == RuntimeFailureKind.timeout ||
        failure.kind == RuntimeFailureKind.unavailable ||
        failure.kind == RuntimeFailureKind.rateLimited;
  }

  @override
  void didUpdateWidget(HomePage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.isStartupHomeActive != widget.isStartupHomeActive) {
      if (widget.isStartupHomeActive) {
        // 重新激活会废止尚未执行的离屏回收；首页正文由当前 frame 继续恢复。
        _surfaceActivityGeneration += 1;
      } else {
        _deactivateSurfaceAfterFrame();
      }
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

  void _deactivateSurfaceAfterFrame() {
    final channelId = _activeChannelId;
    final generation = ++_surfaceActivityGeneration;
    // 先同步撤销在途请求；此方法不发布 Provider 状态，可安全地在
    // IndexedStack 的 didUpdateWidget 阶段执行。
    _feedNotifier.cancelChannelRequests(channelId);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted ||
          generation != _surfaceActivityGeneration ||
          widget.isStartupHomeActive ||
          channelId != _activeChannelId) {
        return;
      }
      // 状态裁剪延后到 frame 结束，避免 Riverpod 在祖先 IndexedStack build
      // 期间触发 markNeedsBuild。
      _feedNotifier.deactivateChannel(channelId);
    });
  }

  String _initialTabForRoute(String? location) {
    return _routeDrivenTab(location) ?? _defaultChannelId;
  }

  String? _routeDrivenTab(String? location) {
    switch (location) {
      case AppRoutePaths.home:
        return _defaultChannelId;
      case homeFollowingChannelLocation:
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
    // 三处 overlay 字段只有「底色亮度」与「其上前景的反色」两种取值。各写一遍
    // isDark 三元会把同一个明暗判断摊成三处，调深浅时容易改一处漏两处。
    final barBrightness = isDark ? Brightness.dark : Brightness.light;
    final barForegroundBrightness = switch (barBrightness) {
      Brightness.dark => Brightness.light,
      Brightness.light => Brightness.dark,
    };
    final statusBarStyle = SystemUiOverlayStyle(
      statusBarColor: AppColors.transparent,
      statusBarIconBrightness: barForegroundBrightness,
      statusBarBrightness: barBrightness,
      systemNavigationBarColor: AppColors.transparent,
      systemNavigationBarIconBrightness: barForegroundBrightness,
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
                key: const ValueKey<String>('home-primary-tab-chrome'),
                height:
                    effectiveTopInset + AppSpacing.primaryTopBarHeight(context),
                padding: EdgeInsets.only(top: effectiveTopInset),
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
                  enabled:
                      effectiveActiveChannelId !=
                      HomePrimaryTabStrip.featuredChannelId,
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
    if (channel.id == HomePrimaryTabStrip.featuredChannelId) {
      return HomeFeaturedImmersivePage(
        key: const ValueKey<String>('home-featured-channel-body'),
        onExitToHome: () => _handleChannelChange(_defaultChannelId),
      );
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
        avatarUrl: avatarUrl,
        displayName: displayName,
        backgroundImage: backgroundUrl,
      ),
    );
  }

  Future<void> _openFeedPost(
    ContentPostViewData post,
    int mediaIndex, {
    List<ContentPostViewData>? feedPosts,
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
