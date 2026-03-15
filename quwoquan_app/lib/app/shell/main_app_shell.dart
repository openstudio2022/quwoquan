import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/app/shell/bottom_navigation.dart';
import 'package:quwoquan_app/ui/discovery/pages/home_page.dart';
import 'package:quwoquan_app/ui/circle/pages/circles_page.dart';
import 'package:quwoquan_app/ui/chat/pages/chat_page.dart';
import 'package:quwoquan_app/ui/user/pages/my_profile_page.dart';
import 'package:quwoquan_app/ui/assistant/pages/assistant_tab_page.dart';
import 'package:quwoquan_app/assistant/infrastructure/infrastructure.dart';

/// 主 App 壳
///
/// 包含五大频道容器与底部导航，与原型 App.tsx 的主框架结构一致。
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
  late int _currentIndex;
  late String _currentLocation;
  late String _currentPageVisitId;
  late DateTime _currentPageEnterAt;

  @override
  void initState() {
    super.initState();
    _currentIndex = _getIndexFromLocation(widget.currentLocation);
    _currentLocation = widget.currentLocation;
    _currentPageVisitId = AppTraceContextStore.instance.newPageVisitId();
    _currentPageEnterAt = DateTime.now();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _logPageOpen(
        location: _currentLocation,
        pageVisitId: _currentPageVisitId,
      );
    });
  }

  @override
  void didUpdateWidget(MainAppShell oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.currentLocation != widget.currentLocation) {
      _currentIndex = _getIndexFromLocation(widget.currentLocation);
      _logPageReturn(
        location: _currentLocation,
        pageVisitId: _currentPageVisitId,
        enterAt: _currentPageEnterAt,
      );
      _currentLocation = widget.currentLocation;
      _currentPageVisitId = AppTraceContextStore.instance.newPageVisitId();
      _currentPageEnterAt = DateTime.now();
      _logPageOpen(
        location: _currentLocation,
        pageVisitId: _currentPageVisitId,
      );
    }
  }

  @override
  void dispose() {
    _logPageReturn(
      location: _currentLocation,
      pageVisitId: _currentPageVisitId,
      enterAt: _currentPageEnterAt,
    );
    super.dispose();
  }

  int _getIndexFromLocation(String location) {
    if (location == '/') {
      return 0; // 首页
    } else if (location == '/circles') {
      return 1; // 圈子
    } else if (location == '/assistant') {
      return 2; // 私主
    } else if (location.startsWith('/chat')) {
      return 3; // 趣信
    } else if (location == '/profile') {
      return 4; // 我的
    }
    return 0;
  }

  @override
  Widget build(BuildContext context) {
    final themeDark = ref.watch(isDarkProvider);
    final forceDark = ref.watch(videoForceDarkProvider).forceDark;
    final isDark = themeDark || forceDark;
    final shellBackground = forceDark
        ? AppColors.worksBackground
        : AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary);
    final bottomNavHidden = ref.watch(bottomNavHiddenProvider).hidden;

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
      child: Scaffold(
        backgroundColor: shellBackground,
        body: Stack(
          children: [
            // 主内容区域 - 使用 IndexedStack 保持各频道状态
            IndexedStack(
              index: _currentIndex,
              children: const [
                HomePage(), // 0: 首页
                CirclesPage(), // 1: 圈子
                AssistantTabPage(), // 2: 私主
                ChatPage(), // 3: 趣聊
                MyProfilePage(), // 4: 我的
              ],
            ),
            // 底部导航（视频全屏沉浸时隐藏）
            if (!bottomNavHidden)
              Positioned(
                left: 0,
                right: 0,
                bottom: 0,
                // Use viewPadding.bottom (physical safe-area, never consumed by
                // parent Scaffold) so the background fill always reaches the
                // very bottom of the screen regardless of nested Scaffold state.
                child: Container(
                  color: shellBackground,
                  padding: EdgeInsets.only(
                    bottom: MediaQuery.viewPaddingOf(context).bottom,
                  ),
                  child: BottomNavigationWidget(
                    currentIndex: _currentIndex,
                    onTap: _handleBottomNavTap,
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }

  void _handleBottomNavTap(int index) {
    final previousIndex = _currentIndex;
    _logBrowseEvent(
      action: 'bottom_nav_tap',
      meta: <String, dynamic>{'fromIndex': previousIndex, 'toIndex': index},
    );
    setState(() {
      _currentIndex = index;
    });

    switch (index) {
      case 0:
        ref.read(lastMainTabBeforeAssistantProvider.notifier).set(null);
        ref.read(bottomNavHiddenProvider.notifier).setHidden(false);
        context.go(AppRoutePaths.home);
        break;
      case 1:
        ref.read(lastMainTabBeforeAssistantProvider.notifier).set(null);
        ref.read(bottomNavHiddenProvider.notifier).setHidden(false);
        context.go(AppRoutePaths.circles);
        break;
      case 2:
        if (previousIndex != 2) {
          ref.read(
            lastMainTabBeforeAssistantProvider.notifier,
          ).set(previousIndex);
        }
        // 进入找小趣时立即隐藏底部导航，避免首帧漏出。
        ref.read(bottomNavHiddenProvider.notifier).setHidden(true);
        context.go(AppRoutePaths.assistant);
        break;
      case 3:
        ref.read(lastMainTabBeforeAssistantProvider.notifier).set(null);
        ref.read(bottomNavHiddenProvider.notifier).setHidden(false);
        context.go(AppRoutePaths.chat);
        break;
      case 4:
        ref.read(lastMainTabBeforeAssistantProvider.notifier).set(null);
        ref.read(bottomNavHiddenProvider.notifier).setHidden(false);
        context.go(AppRoutePaths.profile);
        break;
    }
  }

  String _routeNameFromLocation(String location) {
    switch (location) {
      case '/':
        return 'home';
      case '/circles':
        return 'circles';
      case '/assistant':
        return 'assistant';
      case '/chat':
        return 'chat';
      case '/profile':
        return 'profile';
      default:
        return 'route_unknown';
    }
  }

  Future<void> _logPageOpen({
    required String location,
    required String pageVisitId,
  }) async {
    final trace = AppTraceContextStore.instance;
    await AppLogService.instance.writeEvent(
      logType: AppLogType.pageAccess,
      level: AppLogLevel.info,
      context: AppLogContext(
        sessionId: trace.sessionId,
        journeyId: trace.journeyId,
        pageVisitId: pageVisitId,
      ),
      payload: <String, dynamic>{
        'event': 'open',
        'route': location,
        'pageName': _routeNameFromLocation(location),
      },
      summaryPayload: <String, dynamic>{'event': 'open', 'route': location},
    );
    await AppLogService.instance.writeEvent(
      logType: AppLogType.perf,
      level: AppLogLevel.info,
      context: AppLogContext(
        sessionId: trace.sessionId,
        journeyId: trace.journeyId,
        pageVisitId: pageVisitId,
      ),
      payload: AppPerfProbe.snapshot(event: 'page_open', route: location),
      summaryPayload: <String, dynamic>{
        'event': 'page_open',
        'route': location,
      },
    );
  }

  Future<void> _logPageReturn({
    required String location,
    required String pageVisitId,
    required DateTime enterAt,
  }) async {
    final trace = AppTraceContextStore.instance;
    final durationMs = DateTime.now().difference(enterAt).inMilliseconds;
    await AppLogService.instance.writeEvent(
      logType: AppLogType.pageAccess,
      level: AppLogLevel.info,
      context: AppLogContext(
        sessionId: trace.sessionId,
        journeyId: trace.journeyId,
        pageVisitId: pageVisitId,
      ),
      payload: <String, dynamic>{
        'event': 'return',
        'route': location,
        'pageName': _routeNameFromLocation(location),
        'durationMs': durationMs,
      },
      summaryPayload: <String, dynamic>{
        'event': 'return',
        'route': location,
        'durationMs': durationMs,
      },
    );
    await AppLogService.instance.writeEvent(
      logType: AppLogType.perf,
      level: AppLogLevel.info,
      context: AppLogContext(
        sessionId: trace.sessionId,
        journeyId: trace.journeyId,
        pageVisitId: pageVisitId,
      ),
      payload: AppPerfProbe.snapshot(
        event: 'page_return',
        route: location,
        latencyMs: durationMs,
      ),
      summaryPayload: <String, dynamic>{
        'event': 'page_return',
        'route': location,
        'latencyMs': durationMs,
      },
    );
  }

  Future<void> _logBrowseEvent({
    required String action,
    required Map<String, dynamic> meta,
  }) async {
    final trace = AppTraceContextStore.instance;
    await AppLogService.instance.writeEvent(
      logType: AppLogType.pageAccess,
      level: AppLogLevel.debug,
      context: AppLogContext(
        sessionId: trace.sessionId,
        journeyId: trace.journeyId,
        pageVisitId: _currentPageVisitId,
      ),
      payload: <String, dynamic>{
        'event': 'browse',
        'route': _currentLocation,
        'pageName': _routeNameFromLocation(_currentLocation),
        'action': action,
        'actionMeta': meta,
      },
      summaryPayload: <String, dynamic>{
        'event': 'browse',
        'route': _currentLocation,
        'action': action,
      },
    );
  }
}
