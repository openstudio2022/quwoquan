import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/main_tab_registry.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/components/navigation/centered_scrollable_tab_bar.dart';
import 'package:quwoquan_app/components/navigation/tab_navigation.dart';
import 'package:quwoquan_app/components/navigation/tab_swipe_switch_region.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/global_surface_actions.dart';
import 'package:quwoquan_app/ui/assistant/pages/assistant_conversation_page.dart';
import 'package:quwoquan_app/ui/assistant/pages/assistant_skill_center_page.dart';

class AssistantTabPage extends ConsumerStatefulWidget {
  const AssistantTabPage({super.key});

  @override
  ConsumerState<AssistantTabPage> createState() => _AssistantTabPageState();
}

class _AssistantTabPageState extends ConsumerState<AssistantTabPage>
    with AutomaticKeepAliveClientMixin {
  static const List<String> _tabOrder = <String>[
    'schedule',
    'dialog',
    'skills',
  ];
  String _activeTab = 'dialog';
  String? _lastInternalTab;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || _activeTab != 'dialog') return;
      ref.read(assistantInternalTabProvider.notifier).set(_activeTab);
      ref.read(bottomNavHiddenProvider.notifier).setHidden(true);
    });
  }

  @override
  void dispose() {
    super.dispose();
  }

  void _handleTabChange(String id) {
    if (_activeTab != id) {
      if (_activeTab != 'dialog') {
        _lastInternalTab = _activeTab;
      }
      setState(() => _activeTab = id);
      ref.read(assistantInternalTabProvider.notifier).set(id);
      // 仅「找小趣」走沉浸式体验，其余 tab 保持系统底部导航可见。
      ref.read(bottomNavHiddenProvider.notifier).setHidden(id == 'dialog');
    }
  }

  void _handleExit() {
    // 如果有内部历史且不是 dialog，返回内部历史
    if (_lastInternalTab != null && _lastInternalTab != 'dialog') {
      _handleTabChange(_lastInternalTab!);
      return;
    }

    // 否则退出 Assistant 页面
    final lastTab = ref.read(lastMainTabBeforeAssistantProvider);
    ref.read(lastMainTabBeforeAssistantProvider.notifier).set(null);

    // 恢复底部导航
    ref.read(bottomNavHiddenProvider.notifier).setHidden(false);

    if (lastTab != null) {
      context.go(lastTab.routePath);
    } else {
      context.go(AppRoutePaths.home);
    }
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

  Widget _buildBackAction(bool isDark) {
    final iconColor = AppNavigationSemanticConstants.barIconColor(isDark);
    return SizedBox(
      width: AppSpacing.iconButtonMinSizeSm,
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        minimumSize: Size.square(AppSpacing.iconButtonMinSizeSm),
        onPressed: _activeTab == 'dialog' ? _handleExit : null,
        child: Icon(
          CupertinoIcons.back,
          color: _activeTab == 'dialog'
              ? iconColor
              : iconColor.withValues(alpha: 0),
          size: AppNavigationSemanticConstants.barIconSize,
        ),
      ),
    );
  }

  Widget _buildSettingsAction(bool isDark) {
    final iconColor = AppNavigationSemanticConstants.barIconColor(isDark);
    return SizedBox(
      width: AppSpacing.iconButtonMinSizeSm,
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        minimumSize: Size.square(AppSpacing.iconButtonMinSizeSm),
        onPressed: () => context.push(AppRoutePaths.assistantManagement),
        child: Icon(
          CupertinoIcons.settings,
          size: AppNavigationSemanticConstants.barIconSize,
          color: iconColor,
        ),
      ),
    );
  }

  Widget _buildSearchAction(bool isDark) {
    final iconColor = AppNavigationSemanticConstants.barIconColor(isDark);
    return SizedBox(
      width: AppSpacing.iconButtonMinSizeSm,
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        minimumSize: Size.square(AppSpacing.iconButtonMinSizeSm),
        onPressed: () => GlobalSearchLauncher.open(
          context,
          launchContext: SearchLaunchContext(
            entrySurfaceId: AppRoutePaths.assistant,
            initialScope: SearchScope.all,
          ),
        ),
        child: Icon(
          CupertinoIcons.search,
          size: AppNavigationSemanticConstants.barIconSize,
          color: iconColor,
        ),
      ),
    );
  }

  double _embeddedBottomInset(BuildContext context) {
    return AppSpacing.bottomNavHeight +
        AppSpacing.xs +
        MediaQuery.viewPaddingOf(context).bottom;
  }

  Widget _buildBody(double embeddedBottomInset) {
    switch (_activeTab) {
      case 'schedule':
        return _AssistantScheduleView(bottomInset: embeddedBottomInset);
      case 'skills':
        return Padding(
          padding: EdgeInsets.only(bottom: embeddedBottomInset),
          child: AssistantSkillCenterPage(
            onBack: () {}, // Ignored in embedded mode
            embedded: true,
          ),
        );
      case 'dialog':
      default:
        return KeyedSubtree(
          key: TestKeys.assistantDialogPage,
          child: AssistantConversationPage(
            onBack: _handleExit,
            embedded: true,
          ),
        );
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final isDark = ref.watch(isDarkProvider);
    final bg = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final embeddedBottomInset = _embeddedBottomInset(context);

    final tabs = const <TabItem>[
      TabItem(
        id: 'schedule',
        label: UITextConstants.assistantTabSchedule,
        key: TestKeys.assistantScheduleTab,
      ),
      TabItem(
        id: 'dialog',
        label: UITextConstants.assistantEntryFind,
        key: TestKeys.assistantDialogTab,
      ),
      TabItem(
        id: 'skills',
        label: UITextConstants.assistantTabSkills,
        key: TestKeys.assistantSkillsTab,
      ),
    ];

    return AppScaffold(
      key: TestKeys.assistantTabPage,
      backgroundColor: bg,
      navigationBar: AppNavigationBar(
        backgroundColor: bg,
        automaticallyImplyLeading: false,
        border: Border(
          bottom: BorderSide(color: fgSecondary.withValues(alpha: 0.15)),
        ),
        middle: CenteredScrollableTabBar(
          tabs: tabs,
          activeTab: _activeTab,
          onTabChange: _handleTabChange,
          onHorizontalDragEnd: _handleTabSwipeDragEnd,
          leadingActions: [_buildBackAction(isDark)],
          trailingActions: [
            _buildSearchAction(isDark),
            _buildSettingsAction(isDark),
          ],
          transparentBackground: true,
        ),
      ),
      child: TabSwipeSwitchRegion(
        onSwipe: _handleTabSwipe,
        child: _buildBody(embeddedBottomInset),
      ),
    );
  }

  // Widget _buildBody() { ... } // Removed
}

class _AssistantScheduleView extends ConsumerWidget {
  const _AssistantScheduleView({required this.bottomInset});

  final double bottomInset;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isDark = ref.watch(isDarkProvider);
    final bg = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    final fg = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final taskItems = ref.read(appContentRepositoryProvider).assistantTasksData;

    return Container(
      color: bg,
      child: ListView(
        padding: EdgeInsets.fromLTRB(
          AppSpacing.containerMd,
          AppSpacing.containerMd,
          AppSpacing.containerMd,
          AppSpacing.containerMd + bottomInset,
        ),
        children: [
          _buildCalendarWidget(isDark, fg, fgSecondary),
          SizedBox(height: AppSpacing.interGroupMd),
          Text(
            '待办事项',
            style: TextStyle(
              fontSize: AppTypography.lg,
              fontWeight: AppTypography.semiBold,
              color: fg,
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupSm),
          ...taskItems.map(
            (item) => Padding(
              padding: EdgeInsets.only(bottom: AppSpacing.intraGroupSm),
              child: _SectionCard(
                child: Row(
                  children: [
                    Container(
                      width: AppSpacing.iconLarge,
                      height: AppSpacing.iconLarge,
                      decoration: BoxDecoration(
                        color: AppColors.primaryColor.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(
                          AppSpacing.largeBorderRadius,
                        ),
                      ),
                      child: Icon(
                        CupertinoIcons.check_mark_circled,
                        size: AppSpacing.iconMedium,
                        color: AppColors.primaryColor,
                      ),
                    ),
                    SizedBox(width: AppSpacing.intraGroupSm),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            item['title']?.toString() ?? '',
                            style: TextStyle(
                              fontSize: AppTypography.base,
                              fontWeight: AppTypography.semiBold,
                              color: fg,
                            ),
                          ),
                          SizedBox(height: AppSpacing.intraGroupXs),
                          Text(
                            item['desc']?.toString() ?? '',
                            style: TextStyle(
                              fontSize: AppTypography.sm,
                              color: fgSecondary,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildCalendarWidget(bool isDark, Color fg, Color fgSecondary) {
    // Mock Calendar
    return Container(
      padding: EdgeInsets.all(AppSpacing.containerMd),
      decoration: BoxDecoration(
        color: isDark ? Colors.white.withValues(alpha: 0.05) : Colors.white,
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        border: Border.all(
          color: isDark
              ? Colors.transparent
              : Colors.black.withValues(alpha: 0.05),
        ),
        boxShadow: isDark
            ? []
            : [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.03),
                  blurRadius: 8,
                  offset: const Offset(0, 2),
                ),
              ],
      ),
      child: Column(
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                '2026年3月',
                style: TextStyle(
                  fontSize: AppTypography.lg,
                  fontWeight: AppTypography.semiBold,
                  color: fg,
                ),
              ),
              Row(
                children: [
                  Icon(
                    CupertinoIcons.chevron_left,
                    size: AppSpacing.iconSmall,
                    color: fgSecondary,
                  ),
                  SizedBox(width: AppSpacing.md),
                  Icon(
                    CupertinoIcons.chevron_forward,
                    size: AppSpacing.iconSmall,
                    color: fgSecondary,
                  ),
                ],
              ),
            ],
          ),
          SizedBox(height: AppSpacing.md),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: ['日', '一', '二', '三', '四', '五', '六']
                .map(
                  (d) => Text(
                    d,
                    style: TextStyle(
                      fontSize: AppTypography.sm,
                      color: fgSecondary,
                    ),
                  ),
                )
                .toList(),
          ),
          SizedBox(height: AppSpacing.sm),
          // Simple 1-week mock row
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: List.generate(7, (index) {
              final day = 12 + index;
              final isToday = index == 2; // Mock today is 14th
              return Container(
                width: AppSpacing.smallButtonSize,
                height: AppSpacing.smallButtonSize,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: isToday ? AppColors.primaryColor : Colors.transparent,
                  shape: BoxShape.circle,
                ),
                child: Text(
                  '$day',
                  style: TextStyle(
                    fontSize: AppTypography.base,
                    fontWeight: isToday ? FontWeight.bold : FontWeight.normal,
                    color: isToday ? Colors.white : fg,
                  ),
                ),
              );
            }),
          ),
        ],
      ),
    );
  }
}

class _SectionCard extends StatelessWidget {
  const _SectionCard({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    return Container(
      padding: EdgeInsets.all(AppSpacing.containerMd),
      decoration: BoxDecoration(
        color: isDark ? Colors.white.withValues(alpha: 0.05) : Colors.white,
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        border: Border.all(
          color: isDark
              ? Colors.transparent
              : Colors.black.withValues(alpha: 0.05),
        ),
        boxShadow: isDark
            ? []
            : [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.03),
                  blurRadius: 8,
                  offset: const Offset(0, 2),
                ),
              ],
      ),
      child: child,
    );
  }
}
