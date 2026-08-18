import 'package:quwoquan_app/runtime/observability/app_log_service.dart';

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/layout/app_terminal_viewport.dart';
import 'package:quwoquan_app/design_system/semantics/settings_semantic_constants.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/runtime/auth/auth_continuation.dart';
import 'package:quwoquan_app/runtime/auth/auth_gate.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers_app_state.dart';
import 'package:quwoquan_app/runtime/di/client_state_sync_dependencies.dart';
import 'package:quwoquan_app/runtime/errors/app_user_recovery.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_models.dart';
import 'package:quwoquan_app/runtime/transport/state_sync/client_state_sync.dart';
import 'package:quwoquan_app/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/runtime/di/ops_event_dependencies.dart';
import 'package:quwoquan_app/runtime/di/navigation/push_tap_navigation.dart';
import 'package:quwoquan_app/runtime/platform/platform_providers.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/main_tab_registry.dart';
import 'package:quwoquan_app/runtime/shell/navigation/page_access_log_util.dart';
import 'package:quwoquan_app/runtime/shell/shell_immersive_providers.dart';
import 'package:quwoquan_app/runtime/shell/bottom_navigation.dart';
import 'package:quwoquan_app/runtime/shell/web_app_install_banner.dart';
import 'package:quwoquan_app/runtime/shell/web_main_app_shell.dart';
import 'package:quwoquan_app/runtime/shell/actions/global_surface_actions.dart';
import 'package:quwoquan_app/runtime/di/main_app_shell_dependencies.dart';
import 'package:quwoquan_app/runtime/di/web_main_app_shell_dependencies.dart';
import 'package:quwoquan_app/runtime/observability/app_log_models.dart';
import 'package:quwoquan_app/runtime/observability/app_trace_context_store.dart';
import 'package:quwoquan_app/runtime/observability/generated/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_reporter.dart';
import 'package:quwoquan_app/runtime/di/runtime_observability_dependencies.dart';

/// 主 App 壳
///
/// 包含五个底部一级频道；小趣作为全局入口，不占底栏。
/// 使用 IndexedStack 保持各频道状态，底部导航切换频道。
class MainAppShell extends ConsumerStatefulWidget {
  final Widget child;
  final String currentLocation;

  const MainAppShell({
    super.key,
    required this.child,
    required this.currentLocation,
  });

  @override
  ConsumerState<MainAppShell> createState() => _MainAppShellState();
}

class _MainAppShellState extends ConsumerState<MainAppShell> {
  late MainTabDestination _currentDestination;
  late String _currentLocation;
  late String _currentPageVisitId;
  late DateTime _currentPageEnterAt;
  late final Set<MainTabDestination> _initializedTabDestinations;

  /// 供 [dispose] 使用；卸载时 [ref] 不可用，须在每帧 build 后刷新。
  AppTelemetryRecorder? _pageAccessTelemetryReporter;
  bool _pageAccessDependenciesRefreshScheduled = false;

  /// 全局来电协调器当前绑定的登录用户；空串表示未启动。
  /// 用作幂等守卫，避免重复 start / 漏 stop。
  String _incomingCallBoundUserId = '';

  /// 设备推送 tap 直达路由；平台能力不可用时 start 为一致降级 no-op。
  PushTapNavigator? _pushTapNavigator;

  /// 依据登录态唯一地启动/停止全局来电协调器。
  /// 登录用户切换时先停旧再启新；登出时停止并解绑。
  void _syncIncomingCallCoordinator() {
    final auth = ref.read(authSessionControllerProvider);
    final userId = auth.isAuthenticated ? ref.read(currentUserIdProvider) : '';
    _incomingCallBoundUserId = ref
        .read(mainAppShellBindingsProvider)
        .synchronizeIncomingCall(
          boundUserId: _incomingCallBoundUserId,
          nextUserId: userId,
        );
  }

  void _returnToActiveCall() {
    final bindings = ref.read(mainAppShellBindingsProvider);
    final call = bindings.activeCallRoute;
    if (call == null) {
      return;
    }
    bindings.exitPipMode();
    final path = call.isVideo
        ? AppRoutePaths.rtcVideo(callId: call.callId)
        : AppRoutePaths.rtcVoice(callId: call.callId);
    context.push(path);
  }

  Future<void> _hangupActiveCall() async {
    await ref.read(mainAppShellBindingsProvider).hangupActiveCall();
  }

  void _cachePageAccessDependencies() {
    if (_pageAccessDependenciesRefreshScheduled) {
      return;
    }
    _pageAccessDependenciesRefreshScheduled = true;
    // 部分 provider 在首次 read 时会完成异步状态水合。build 期间触发这类
    // 刷新会让 Riverpod 尝试标记 ProviderScope 脏状态，违反 Flutter 的 build
    // 阶段约束；将仅用于 dispose 页面访问事件的缓存延后到当前帧完成后。
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _pageAccessDependenciesRefreshScheduled = false;
      if (!mounted) {
        return;
      }
      _pageAccessTelemetryReporter = ref.read(appTelemetryReporterProvider);
    });
  }

  @override
  void initState() {
    super.initState();
    _currentDestination = mainTabFromLocation(widget.currentLocation);
    _initializedTabDestinations = <MainTabDestination>{_currentDestination};
    _currentLocation = widget.currentLocation;
    _currentPageVisitId = AppTraceContextStore.instance.newPageVisitId();
    _currentPageEnterAt = DateTime.now();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      writeAppPageAccessOpen(
        location: _currentLocation,
        pageVisitId: _currentPageVisitId,
        navigationStartedAt: _currentPageEnterAt,
        visitRecorder: ref.read(visitRecorderServiceProvider),
        telemetryReporter: ref.read(appTelemetryReporterProvider),
      );
      _syncIncomingCallCoordinator();
      final pushTapNavigator = PushTapNavigator(
        messagingClient: ref.read(pushTapMessagingClientProvider),
        push: (location) {
          if (mounted) {
            context.push(location);
          }
        },
      );
      _pushTapNavigator = pushTapNavigator;
      unawaited(pushTapNavigator.start());
    });
  }

  @override
  void didUpdateWidget(MainAppShell oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.currentLocation != widget.currentLocation) {
      _currentDestination = mainTabFromLocation(widget.currentLocation);
      _initializedTabDestinations.add(_currentDestination);
      writeAppPageAccessReturn(
        location: _currentLocation,
        pageVisitId: _currentPageVisitId,
        enterAt: _currentPageEnterAt,
        telemetryReporter: ref.read(appTelemetryReporterProvider),
      );
      _currentLocation = widget.currentLocation;
      _currentPageVisitId = AppTraceContextStore.instance.newPageVisitId();
      _currentPageEnterAt = DateTime.now();
      writeAppPageAccessOpen(
        location: _currentLocation,
        pageVisitId: _currentPageVisitId,
        navigationStartedAt: _currentPageEnterAt,
        visitRecorder: ref.read(visitRecorderServiceProvider),
        telemetryReporter: ref.read(appTelemetryReporterProvider),
      );
    }
  }

  @override
  void dispose() {
    writeAppPageAccessReturn(
      location: _currentLocation,
      pageVisitId: _currentPageVisitId,
      enterAt: _currentPageEnterAt,
      telemetryReporter: _pageAccessTelemetryReporter,
    );
    final pushTapNavigator = _pushTapNavigator;
    _pushTapNavigator = null;
    if (pushTapNavigator != null) {
      unawaited(pushTapNavigator.dispose());
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    _cachePageAccessDependencies();
    // 登录后续接：底栏加号里的具体动作被拦截时登记了
    // OpenSheetContinuation；登录成功（auth 翻转为已认证）时由始终在场的外壳
    // 自动续接打开对应面板，避免「登录回来动作丢失」。
    ref.listen<AuthSessionState>(authSessionControllerProvider, (
      AuthSessionState? previous,
      AuthSessionState next,
    ) {
      // Riverpod 的异步通知可能与 shell 卸载交错；此时 ConsumerState 的 ref
      // 已不可访问，不能为了同步来电协调器或 continuation 再读取任何 Provider。
      if (!mounted) {
        return;
      }
      // 登录态翻转时同步全局来电协调器：登录启动来电监听，登出停止解绑。
      _syncIncomingCallCoordinator();
      final justLoggedIn =
          next.isAuthenticated &&
          (previous == null || !previous.isAuthenticated);
      if (!justLoggedIn) {
        return;
      }
      final pending = ref
          .read(authContinuationProvider.notifier)
          .take<OpenSheetContinuation>();
      if (pending == null || !mounted) {
        return;
      }
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!context.mounted) {
          return;
        }
        unawaited(
          GlobalQuickActionSheet.resumeSheetContinuation(
            context,
            ref,
            pending.sheet,
          ),
        );
      });
    });
    // 点赞/关注 outbox 终态失败：乐观态已由 Notifier 回滚，这里以统一
    // 恢复语义的警示轻提示告知用户，消费后清空信号避免重复弹出。
    ref.listen<ClientStateSyncOutboxEntry?>(
      clientStateSyncTerminalFailureProvider,
      (ClientStateSyncOutboxEntry? previous, ClientStateSyncOutboxEntry? next) {
        if (next == null || !mounted) {
          return;
        }
        ref.read(clientStateSyncTerminalFailureProvider.notifier).consume();
        AppToast.showError(
          context,
          AppUserRecoveryContract.semanticFor(
            group: AppUserRecoveryGroup.serviceUnavailable,
            category: UiErrorCategory.backgroundAction,
            scope: UiErrorScope.global,
            sourceSurfaceId: next.sourceSurfaceId.isEmpty
                ? null
                : next.sourceSurfaceId,
          ),
        );
      },
    );
    final themeDark = ref.watch(isDarkProvider);
    final forceDark = ref.watch(videoForceDarkProvider).forceDark;
    final effectiveForceDark = forceDark;
    final isDark = themeDark || effectiveForceDark;
    final shellBackground = effectiveForceDark
        ? AppColors.worksBackground
        : SettingsSemanticConstants.conversationSheetCardSurface(isDark);
    final bottomNavHidden =
        ref.watch(bottomNavHiddenProvider).hidden ||
        !_currentDestination.isBottomNavDestination ||
        widget.currentLocation == AppRoutePaths.createEntry ||
        widget.currentLocation.startsWith(AppRoutePaths.createPathTemplate);
    final capabilities = ref.watch(platformCapabilitiesProvider);
    final useWebWideShell =
        capabilities.wideScreenLayout && AppSpacing.isWideLayout(context);
    final showInstallBanner = capabilities.promotesAppInstall;
    final shellBindings = ref.watch(mainAppShellBindingsProvider);
    final webShellDependencies = useWebWideShell
        ? ref.watch(webMainAppShellDependenciesProvider)
        : null;

    final statusBarStyle = SystemUiOverlayStyle(
      statusBarColor: Colors.transparent,
      statusBarIconBrightness: isDark ? Brightness.light : Brightness.dark,
      statusBarBrightness: isDark ? Brightness.dark : Brightness.light,
      systemNavigationBarColor: Colors.transparent,
      systemNavigationBarIconBrightness: isDark
          ? Brightness.light
          : Brightness.dark,
    );

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: statusBarStyle,
      child: Stack(
        children: [
          ColoredBox(
            color: shellBackground,
            child: Column(
              children: [
                if (showInstallBanner) const WebAppInstallBanner(),
                shellBindings.buildActiveCallBar(onTap: _returnToActiveCall),
                Expanded(
                  child: useWebWideShell
                      ? Stack(
                          children: [
                            WebMainAppShell(
                              dependencies: webShellDependencies!,
                              currentDestination: _currentDestination,
                              currentLocation: _currentLocation,
                              backgroundColor: shellBackground,
                              onPrimarySelected: _handleWebPrimaryTap,
                              onGuestAuthGateOpened:
                                  _resetWebPrimaryToHomeSafeState,
                            ),
                          ],
                        )
                      : _ShellContentFrame(
                          constrained: capabilities.wideScreenLayout,
                          bottomObstruction: bottomNavHidden
                              ? AppSpacing.zero
                              : AppSpacing.bottomNavBarHeight(context) +
                                    MediaQuery.viewPaddingOf(context).bottom,
                          child: Stack(
                            children: [
                              IndexedStack(
                                index:
                                    _currentDestination
                                        .isMobileShellStackDestination
                                    ? _currentDestination.mobileShellStackIndex
                                    : MainTabDestination
                                          .home
                                          .mobileShellStackIndex,
                                children: [
                                  _buildTabBody(
                                    destination: MainTabDestination.home,
                                    child: shellBindings.buildHome(
                                      routeLocation: _currentLocation,
                                      isStartupHomeActive:
                                          _currentDestination ==
                                          MainTabDestination.home,
                                    ),
                                  ),
                                  _buildTabBody(
                                    destination: MainTabDestination.actions,
                                    child: shellBindings
                                        .buildActionsDiscovery(),
                                  ),
                                  const SizedBox.shrink(),
                                  _buildTabBody(
                                    destination: MainTabDestination.chat,
                                    child: shellBindings.buildChat(),
                                  ),
                                  _buildTabBody(
                                    destination: MainTabDestination.profile,
                                    child: shellBindings.buildProfile(),
                                  ),
                                ],
                              ),
                              if (!_currentDestination
                                  .isMobileShellStackDestination)
                                Positioned.fill(child: widget.child),
                              if (!bottomNavHidden)
                                Positioned(
                                  left: 0,
                                  right: 0,
                                  bottom: 0,
                                  child: BottomNavigationWidget(
                                    currentIndex:
                                        _currentDestination.bottomNavIndex,
                                    onTap: _handleBottomNavTap,
                                  ),
                                ),
                            ],
                          ),
                        ),
                ),
              ],
            ),
          ),
          shellBindings.buildPipCallOverlay(
            onReturnToCall: _returnToActiveCall,
            onHangup: _hangupActiveCall,
          ),
        ],
      ),
    );
  }

  void _handleBottomNavTap(int index) {
    final previousIndex = _currentDestination.bottomNavIndex;
    final nextTab = mainTabFromBottomNavIndex(index);
    _logBrowseEvent(
      action: 'bottom_nav_tap',
      fromIndex: previousIndex,
      toIndex: index,
    );
    if (nextTab == MainTabDestination.create) {
      // 加号入口后置登录：先无条件打开动作面板，登录拦截下沉到具体动作
      // （写文章/发图片/发视频走 /create 路由门，添加联系人/群聊/建圈子在动作上拦截）。
      unawaited(GlobalQuickActionSheet.show(context, ref));
      return;
    }

    if (nextTab == MainTabDestination.chat &&
        !_ensureLoggedInFor(AuthGateReason.openChat, AppRoutePaths.chat)) {
      return;
    }

    // 「我的」tab 为强登录入口：游客切到「我」立即弹登录，登录成功进入 /profile，
    // 关闭则安全回首页（safeFallback）。这里在 tap 级（动作门）拦截，
    // 不把 /profile 接入路由级守卫，避免登录页关闭后原路回 /profile 再次命中守卫
    // 形成死循环；MyProfilePage 的游客占位仅作为深链兜底。
    if (nextTab == MainTabDestination.profile &&
        !_ensureLoggedInFor(AuthGateReason.profileTab, AppRoutePaths.profile)) {
      return;
    }

    _selectMainTab(nextTab);
  }

  void _handleWebPrimaryTap(MainTabDestination nextTab) {
    final previousIndex = _currentDestination.primaryNavigationIndex;
    _logBrowseEvent(
      action: 'web_primary_tap',
      fromIndex: previousIndex,
      toIndex: nextTab.primaryNavigationIndex,
    );

    if (nextTab == MainTabDestination.create) {
      // Web/宽屏 create 主入口与移动端加号一致：先进入创建工作台/动作面板，
      // 登录拦截下沉到具体写作、发图、发视频或草稿等账号态动作。
      _selectWebCreateTab();
      return;
    }

    if (nextTab == MainTabDestination.chat &&
        !_ensureLoggedInFor(AuthGateReason.openChat, AppRoutePaths.chat)) {
      return;
    }

    if (nextTab == MainTabDestination.profile &&
        !_ensureLoggedInFor(AuthGateReason.profileTab, AppRoutePaths.profile)) {
      return;
    }

    _selectMainTab(nextTab);
  }

  /// Web 壳的一级入口是内部 tab，不由路由表达：账号态动作弹出登录门后，必须把
  /// 壳先归位到首页安全态，否则关闭登录时的 `go(home)` 因 location 未变而不会
  /// 触发 `didUpdateWidget`，用户会原地回到触发面板（登录入口无死循环宪法）。
  /// 这里只改内部 tab，不做导航，避免把已压栈的登录页顶掉。
  void _resetWebPrimaryToHomeSafeState() {
    if (!mounted || _currentDestination == MainTabDestination.home) {
      return;
    }
    setState(() {
      _currentDestination = MainTabDestination.home;
      _initializedTabDestinations.add(_currentDestination);
    });
    ref.read(bottomNavHiddenProvider.notifier).setHidden(false);
  }

  void _selectWebCreateTab() {
    setState(() {
      _currentDestination = MainTabDestination.create;
    });
    ref.read(lastMainTabBeforeAssistantProvider.notifier).set(null);
    ref.read(bottomNavHiddenProvider.notifier).setHidden(true);
  }

  void _selectMainTab(MainTabDestination nextTab) {
    setState(() {
      _currentDestination = nextTab;
      _initializedTabDestinations.add(_currentDestination);
    });

    switch (nextTab) {
      case MainTabDestination.home:
        ref.read(lastMainTabBeforeAssistantProvider.notifier).set(null);
        ref.read(bottomNavHiddenProvider.notifier).setHidden(false);
        context.go(nextTab.routePath);
        break;
      case MainTabDestination.create:
        break;
      case MainTabDestination.actions:
        // 线下行动与发现：壳内存态 tab（无独立路由），保留底栏与常规明暗。
        ref.read(lastMainTabBeforeAssistantProvider.notifier).set(null);
        ref.read(bottomNavHiddenProvider.notifier).setHidden(false);
        break;
      case MainTabDestination.chat:
        ref.read(lastMainTabBeforeAssistantProvider.notifier).set(null);
        ref.read(bottomNavHiddenProvider.notifier).setHidden(false);
        context.go(nextTab.routePath);
        break;
      case MainTabDestination.interestMatch:
        // 同趣（兴趣配对）：游客可浏览，无登录门；移动端由加号面板进入，
        // Web 宽屏仍可作为主工作区 destination 承载。
        ref.read(lastMainTabBeforeAssistantProvider.notifier).set(null);
        ref.read(bottomNavHiddenProvider.notifier).setHidden(false);
        context.go(nextTab.routePath);
        break;
      case MainTabDestination.profile:
        ref.read(lastMainTabBeforeAssistantProvider.notifier).set(null);
        ref.read(bottomNavHiddenProvider.notifier).setHidden(false);
        context.go(nextTab.routePath);
        break;
    }
  }

  Widget _buildTabBody({
    required MainTabDestination destination,
    required Widget child,
  }) {
    if (_initializedTabDestinations.contains(destination) ||
        _currentDestination == destination) {
      _initializedTabDestinations.add(destination);
      return child;
    }
    return const SizedBox.shrink();
  }

  /// 强入口（底栏 创作/消息/我的）登录拦截：不展示中间提示，直接上推全屏登录页，
  /// 标题按入口对应的 [AuthGateReason] 变化，关闭后保留当前 tab。
  bool _ensureLoggedInFor(AuthGateReason reason, String redirect) {
    final auth = ref.read(authSessionControllerProvider);
    if (auth.isAuthenticated) {
      return true;
    }
    // 强入口未登录：先把底层归位到首页（底栏第一项），再上推全屏登录页。
    // 这样无论登录成功（按 redirect 跳目标）还是关闭 / 稍后登录（回首页或原路返回），
    // 都稳定回到首页，避免关闭登录后仍停留在受限入口。
    if (_currentDestination != MainTabDestination.home) {
      _selectMainTab(MainTabDestination.home);
    }
    openLoginPage(
      context,
      reasonName: reason.name,
      redirect: redirect,
      dismissFallback: AppRoutePaths.home,
      // 强入口已先归位首页：关闭只 go 首页，禁止 pop 回到 create/chat/profile
      // 这类受限路由再次触发守卫，从根上杜绝「关闭→又弹登录」死循环。
      dismissPolicy: LoginDismissPolicy.safeFallback,
    );
    return false;
  }

  Future<void> _logBrowseEvent({
    required String action,
    int? fromIndex,
    int? toIndex,
  }) async {
    final trace = AppTraceContextStore.instance;
    await ref
        .read(appEventLogPortProvider)
        .writeEvent(
          logType: AppLogType.pageAccess,
          level: AppLogLevel.debug,
          context: AppLogContext(
            sessionId: trace.sessionId,
            pageVisitId: _currentPageVisitId,
          ),
          payload: <String, Object?>{
            'event': 'browse',
            'route': _currentLocation,
            'pageName': pageNameFromRouteLocation(_currentLocation),
            'action': action,
            if (fromIndex != null && toIndex != null)
              'actionMeta': <String, int>{
                'fromIndex': fromIndex,
                'toIndex': toIndex,
              },
          },
          summaryPayload: <String, Object?>{
            'event': 'browse',
            'route': _currentLocation,
            'action': action,
          },
        );
    final pageName = pageNameFromRouteLocation(_currentLocation);
    if (pageName.isNotEmpty) {
      unawaited(
        ref
            .read(appTelemetryReporterProvider)
            .record(
              AppTelemetryPayload.productAction(
                journey: 'main_navigation',
                action: action,
              ),
              pageName: pageName,
            ),
      );
    }
  }
}

class _ShellContentFrame extends StatelessWidget {
  const _ShellContentFrame({
    required this.constrained,
    required this.bottomObstruction,
    required this.child,
  });

  final bool constrained;
  final double bottomObstruction;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final scopedChild = AppViewportObstructionScope(
      obstruction: EdgeInsets.only(bottom: bottomObstruction),
      child: child,
    );
    if (!constrained || !AppSpacing.isWideLayout(context)) {
      return scopedChild;
    }
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(
          maxWidth: AppSpacing.webContentMaxWidth,
        ),
        child: scopedChild,
      ),
    );
  }
}
