import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/navigation/main_tab_registry.dart';
import 'package:quwoquan_app/app/navigation/page_access_log_util.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/app/shell/bottom_navigation.dart';
import 'package:quwoquan_app/ui/discovery/pages/home_page.dart';
import 'package:quwoquan_app/ui/chat/pages/chat_page.dart';
import 'package:quwoquan_app/ui/user/pages/my_profile_page.dart';
import 'package:quwoquan_app/ui/assistant/pages/assistant_tab_page.dart';
import 'package:quwoquan_app/ui/circle/pages/circles_page.dart';
import 'package:quwoquan_app/assistant/infrastructure/infrastructure.dart';

/// 主 App 壳
///
/// 包含四个底部一级频道，圈子作为首页内一级 Tab 保留。
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
    _currentIndex = bottomNavIndexFromLocation(widget.currentLocation);
    _currentLocation = widget.currentLocation;
    _currentPageVisitId = AppTraceContextStore.instance.newPageVisitId();
    _currentPageEnterAt = DateTime.now();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      writeAppPageAccessOpen(
        location: _currentLocation,
        pageVisitId: _currentPageVisitId,
      );
    });
  }

  @override
  void didUpdateWidget(MainAppShell oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.currentLocation != widget.currentLocation) {
      _currentIndex = bottomNavIndexFromLocation(widget.currentLocation);
      writeAppPageAccessReturn(
        location: _currentLocation,
        pageVisitId: _currentPageVisitId,
        enterAt: _currentPageEnterAt,
      );
      _currentLocation = widget.currentLocation;
      _currentPageVisitId = AppTraceContextStore.instance.newPageVisitId();
      _currentPageEnterAt = DateTime.now();
      writeAppPageAccessOpen(
        location: _currentLocation,
        pageVisitId: _currentPageVisitId,
      );
    }
  }

  @override
  void dispose() {
    writeAppPageAccessReturn(
      location: _currentLocation,
      pageVisitId: _currentPageVisitId,
      enterAt: _currentPageEnterAt,
    );
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final themeDark = ref.watch(isDarkProvider);
    final forceDark = ref.watch(videoForceDarkProvider).forceDark;
    final isDark = themeDark || forceDark;
    final assistantInternalTab = ref.watch(assistantInternalTabProvider);
    final shellBackground = forceDark
        ? AppColors.worksBackground
        : AppColorsFunctional.getColor(isDark, ColorType.pageBackground);
    final assistantImmersive =
        widget.currentLocation == AppRoutePaths.assistant &&
        assistantInternalTab == 'dialog';
    final bottomNavHidden =
        ref.watch(bottomNavHiddenProvider).hidden ||
        assistantImmersive ||
        widget.currentLocation == AppRoutePaths.circles;

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
      child: ColoredBox(
        color: shellBackground,
        child: Stack(
          children: [
            IndexedStack(
              index: _currentIndex,
              children: [
                _buildPrimarySurface(),
                const AssistantTabPage(),
                const ChatPage(),
                const MyProfilePage(),
              ],
            ),
            if (!bottomNavHidden)
              Positioned(
                left: 0,
                right: 0,
                bottom: 0,
                child: BottomNavigationWidget(
                  currentIndex: bottomNavIndexFromLocation(_currentLocation),
                  onTap: _handleBottomNavTap,
                ),
              ),
          ],
        ),
      ),
    );
  }

  void _handleBottomNavTap(int index) {
    final previousIndex = _currentIndex;
    final nextTab = mainTabFromBottomNavIndex(index);
    _logBrowseEvent(
      action: 'bottom_nav_tap',
      meta: <String, dynamic>{'fromIndex': previousIndex, 'toIndex': index},
    );
    setState(() {
      _currentIndex = index;
    });

    switch (nextTab) {
      case MainTabDestination.home:
        ref.read(lastMainTabBeforeAssistantProvider.notifier).set(null);
        ref.read(bottomNavHiddenProvider.notifier).setHidden(false);
        context.go(nextTab.routePath);
        break;
      case MainTabDestination.assistant:
        if (previousIndex != MainTabDestination.assistant.bottomNavIndex) {
          final previousTab = mainTabFromLocation(_currentLocation);
          ref
              .read(lastMainTabBeforeAssistantProvider.notifier)
              .set(
                previousTab == MainTabDestination.assistant
                    ? null
                    : previousTab,
              );
        }
        // 助理入口根据当前内部 tab 决定是否走沉浸式，避免把日程/技能误判为全屏。
        ref
            .read(bottomNavHiddenProvider.notifier)
            .setHidden(ref.read(assistantInternalTabProvider) == 'dialog');
        context.go(nextTab.routePath);
        break;
      case MainTabDestination.chat:
        ref.read(lastMainTabBeforeAssistantProvider.notifier).set(null);
        ref.read(bottomNavHiddenProvider.notifier).setHidden(false);
        context.go(nextTab.routePath);
        break;
      case MainTabDestination.profile:
        ref.read(lastMainTabBeforeAssistantProvider.notifier).set(null);
        ref.read(bottomNavHiddenProvider.notifier).setHidden(false);
        context.go(nextTab.routePath);
        break;
      case MainTabDestination.circles:
        ref.read(lastMainTabBeforeAssistantProvider.notifier).set(null);
        ref.read(bottomNavHiddenProvider.notifier).setHidden(false);
        context.go(AppRoutePaths.circles);
        break;
    }
  }

  Widget _buildPrimarySurface() {
    if (_currentLocation == AppRoutePaths.circles) {
      return const CirclesPage();
    }
    return HomePage(routeLocation: _currentLocation);
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
        'pageName': pageNameFromRouteLocation(_currentLocation),
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
