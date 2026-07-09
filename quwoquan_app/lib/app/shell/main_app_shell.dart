import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/navigation/main_tab_registry.dart';
import 'package:quwoquan_app/app/navigation/page_access_log_util.dart';
import 'package:quwoquan_app/cloud/rtc/incoming_call_coordinator.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/services/active_call_service.dart';
import 'package:quwoquan_app/app/shell/bottom_navigation.dart';
import 'package:quwoquan_app/app/shell/web_app_install_banner.dart';
import 'package:quwoquan_app/app/shell/web_main_app_shell.dart';
import 'package:quwoquan_app/core/widgets/global_surface_actions.dart';
import 'package:quwoquan_app/ui/rtc/widgets/active_call_bar.dart';
import 'package:quwoquan_app/ui/rtc/widgets/pip_call_overlay.dart';
import 'package:quwoquan_app/ui/discovery/pages/home_page.dart';
import 'package:quwoquan_app/ui/chat/pages/chat_page.dart';
import 'package:quwoquan_app/ui/user/pages/my_profile_page.dart';
import 'package:quwoquan_app/assistant/infrastructure/infrastructure.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_log_bottom_nav_tap_meta.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_log_page_browse_payload.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_log_page_browse_summary.g.dart';
import 'package:quwoquan_app/cloud/services/ops/ops_event_repository.dart';

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

  /// 供 [dispose] 使用；卸载时 [ref] 不可用，须在 [build] 中刷新。
  OpsEventRepository? _pageAccessOpsRepository;
  String _pageAccessCurrentUserId = '';
  String _pageAccessExperimentBucket = '';

  /// 全局来电协调器当前绑定的登录用户；空串表示未启动。
  /// 用作幂等守卫，避免重复 start / 漏 stop。
  String _incomingCallBoundUserId = '';

  /// 依据登录态唯一地启动/停止全局来电协调器。
  /// 登录用户切换时先停旧再启新；登出时停止并解绑。
  void _syncIncomingCallCoordinator() {
    final auth = ref.read(authSessionControllerProvider);
    final userId = auth.isAuthenticated ? ref.read(currentUserIdProvider) : '';
    final decision = resolveIncomingCallSync(
      boundUserId: _incomingCallBoundUserId,
      nextUserId: userId,
    );
    if (!decision.shouldStop && !decision.shouldStart) {
      return;
    }
    final coordinator = ref.read(incomingCallCoordinatorProvider);
    if (decision.shouldStop) {
      coordinator.stop();
    }
    if (decision.shouldStart) {
      coordinator.start(userId);
    }
    _incomingCallBoundUserId = decision.boundUserId;
  }

  void _returnToActiveCall() {
    final call = ref.read(activeCallProvider);
    final callId = call.callId;
    if (callId == null || callId.isEmpty) {
      return;
    }
    ref.read(activeCallProvider.notifier).exitPipMode();
    final path = call.callType == 'video'
        ? AppRoutePaths.rtcVideo(callId: callId)
        : AppRoutePaths.rtcVoice(callId: callId);
    context.push(path);
  }

  void _hangupActiveCall() {
    ref.read(activeCallProvider.notifier).endCall();
  }

  void _cachePageAccessDependencies() {
    _pageAccessOpsRepository = ref.read(opsEventRepositoryProvider);
    _pageAccessCurrentUserId = ref.read(currentUserIdProvider);
    _pageAccessExperimentBucket = ref
        .read(contentRuntimeConfigProvider)
        .experimentBucket;
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
        visitRecorder: ref.read(visitRecorderServiceProvider),
        eventRepository: ref.read(opsEventRepositoryProvider),
        currentUserId: ref.read(currentUserIdProvider),
        experimentBucket: ref
            .read(contentRuntimeConfigProvider)
            .experimentBucket,
      );
      _syncIncomingCallCoordinator();
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
        eventRepository: ref.read(opsEventRepositoryProvider),
        currentUserId: ref.read(currentUserIdProvider),
        experimentBucket: ref
            .read(contentRuntimeConfigProvider)
            .experimentBucket,
      );
      _currentLocation = widget.currentLocation;
      _currentPageVisitId = AppTraceContextStore.instance.newPageVisitId();
      _currentPageEnterAt = DateTime.now();
      writeAppPageAccessOpen(
        location: _currentLocation,
        pageVisitId: _currentPageVisitId,
        visitRecorder: ref.read(visitRecorderServiceProvider),
        eventRepository: ref.read(opsEventRepositoryProvider),
        currentUserId: ref.read(currentUserIdProvider),
        experimentBucket: ref
            .read(contentRuntimeConfigProvider)
            .experimentBucket,
      );
    }
  }

  @override
  void dispose() {
    writeAppPageAccessReturn(
      location: _currentLocation,
      pageVisitId: _currentPageVisitId,
      enterAt: _currentPageEnterAt,
      eventRepository: _pageAccessOpsRepository,
      currentUserId: _pageAccessCurrentUserId,
      experimentBucket: _pageAccessExperimentBucket,
    );
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    _cachePageAccessDependencies();
    // 登录后续接：底栏加号里「添加联系人/发起群聊/建圈子」被拦截时登记了
    // OpenSheetContinuation；登录成功（auth 翻转为已认证）时由始终在场的外壳
    // 自动续接打开对应面板，避免「登录回来动作丢失」。
    ref.listen<AuthSessionState>(authSessionControllerProvider, (
      AuthSessionState? previous,
      AuthSessionState next,
    ) {
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
        GlobalQuickActionSheet.resumeSheetContinuation(context, pending.sheet);
      });
    });
    final themeDark = ref.watch(isDarkProvider);
    final isFeaturedActive = _currentDestination == MainTabDestination.featured;
    final forceDark = ref.watch(videoForceDarkProvider).forceDark;
    final effectiveForceDark = forceDark || isFeaturedActive;
    final isDark = themeDark || effectiveForceDark;
    final shellBackground = effectiveForceDark
        ? AppColors.worksBackground
        : SettingsSemanticConstants.conversationSheetCardSurface(isDark);
    final bottomNavHidden =
        ref.watch(bottomNavHiddenProvider).hidden ||
        isFeaturedActive ||
        !_currentDestination.isBottomNavDestination ||
        widget.currentLocation == AppRoutePaths.createEntry ||
        widget.currentLocation.startsWith(AppRoutePaths.createPathTemplate);
    final capabilities = ref.watch(platformCapabilitiesProvider);
    final useWebWideShell =
        capabilities.wideScreenLayout && AppSpacing.isWideLayout(context);
    final showInstallBanner =
        capabilities.promotesAppInstall && !useWebWideShell;

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
                ActiveCallBar(onTap: _returnToActiveCall),
                Expanded(
                  child: useWebWideShell
                      ? Stack(
                          children: [
                            WebMainAppShell(
                              currentDestination: _currentDestination,
                              currentLocation: _currentLocation,
                              backgroundColor: shellBackground,
                              onPrimarySelected: _handleWebPrimaryTap,
                            ),
                          ],
                        )
                      : _ShellContentFrame(
                          constrained: capabilities.wideScreenLayout,
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
                                    child: HomePage(
                                      routeLocation: _currentLocation,
                                    ),
                                  ),
                                  _buildTabBody(
                                    destination: MainTabDestination.featured,
                                    child: HomeFeaturedImmersivePage(
                                      onExitToHome: () => _selectMainTab(
                                        MainTabDestination.home,
                                      ),
                                    ),
                                  ),
                                  const SizedBox.shrink(),
                                  _buildTabBody(
                                    destination: MainTabDestination.chat,
                                    child: const ChatPage(),
                                  ),
                                  _buildTabBody(
                                    destination: MainTabDestination.profile,
                                    child: const MyProfilePage(),
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
          PipCallOverlay(
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
      bottomNavTap: AppLogBottomNavTapMeta(
        fromIndex: previousIndex,
        toIndex: index,
      ),
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
    // 关闭则安全回首页（allowGuestDismissPop=false）。这里在 tap 级（动作门）拦截，
    // 不把 /profile 接入路由级守卫，避免登录页关闭后原路回 /profile 再次命中守卫
    // 形成死循环；MyProfilePage 的游客占位仅作为深链兜底。
    if (nextTab == MainTabDestination.profile &&
        !_ensureLoggedInFor(AuthGateReason.profileTab, AppRoutePaths.profile)) {
      return;
    }

    if (nextTab == MainTabDestination.featured) {
      _selectMainTab(nextTab);
      return;
    }

    _selectMainTab(nextTab);
  }

  void _handleWebPrimaryTap(MainTabDestination nextTab) {
    final previousIndex = _currentDestination.primaryNavigationIndex;
    _logBrowseEvent(
      action: 'web_primary_tap',
      bottomNavTap: AppLogBottomNavTapMeta(
        fromIndex: previousIndex,
        toIndex: nextTab.primaryNavigationIndex,
      ),
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
      case MainTabDestination.featured:
        ref.read(lastMainTabBeforeAssistantProvider.notifier).set(null);
        ref.read(bottomNavHiddenProvider.notifier).setHidden(true);
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
    // 都稳定回到首页，避免从 premium/featured 等内存态 tab 进入后关闭仍停留在原 tab。
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
      allowGuestDismissPop: false,
    );
    return false;
  }

  Future<void> _logBrowseEvent({
    required String action,
    AppLogBottomNavTapMeta? bottomNavTap,
  }) async {
    final trace = AppTraceContextStore.instance;
    await AppLogService.instance.writeEvent(
      logType: AppLogType.pageAccess,
      level: AppLogLevel.debug,
      context: AppLogContext(
        sessionId: trace.sessionId,
        pageVisitId: _currentPageVisitId,
      ),
      payload: AppLogPageBrowsePayload(
        event: 'browse',
        route: _currentLocation,
        pageName: pageNameFromRouteLocation(_currentLocation),
        action: action,
        actionMeta: bottomNavTap?.toMap(),
      ).toMap(),
      summaryPayload: AppLogPageBrowseSummaryPayload(
        event: 'browse',
        route: _currentLocation,
        action: action,
      ).toMap(),
    );
  }
}

class _ShellContentFrame extends StatelessWidget {
  const _ShellContentFrame({required this.constrained, required this.child});

  final bool constrained;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    if (!constrained || !AppSpacing.isWideLayout(context)) {
      return child;
    }
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(
          maxWidth: AppSpacing.webContentMaxWidth,
        ),
        child: child,
      ),
    );
  }
}
