import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/components/navigation/centered_scrollable_tab_bar.dart';
import 'package:quwoquan_app/components/navigation/tab_navigation.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/assistant/pages/assistant_skill_center_page.dart';
import 'package:quwoquan_app/ui/chat/pages/chat_detail_page.dart';

class AssistantTabPage extends ConsumerStatefulWidget {
  const AssistantTabPage({super.key});

  @override
  ConsumerState<AssistantTabPage> createState() => _AssistantTabPageState();
}

class _AssistantTabPageState extends ConsumerState<AssistantTabPage>
    with AutomaticKeepAliveClientMixin {
  String _activeTab = 'dialog';

  @override
  bool get wantKeepAlive => true;

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

    final tabs = const <TabItem>[
      TabItem(id: 'dialog', label: '对话'),
      TabItem(id: 'schedule', label: '日程'),
      TabItem(id: 'skills', label: '技能'),
    ];

    return Scaffold(
      backgroundColor: bg,
      body: SafeArea(
        bottom: false,
        child: Column(
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
                  Positioned.fill(
                    child: Center(
                      child: CenteredScrollableTabBar(
                        tabs: tabs,
                        activeTab: _activeTab,
                        onTabChange: (id) => setState(() => _activeTab = id),
                        leadingActions: const [],
                        trailingActions: const [],
                        transparentBackground: true,
                      ),
                    ),
                  ),
                  Positioned(
                    right: AppSpacing.feedContentHorizontal(context),
                    top: 0,
                    bottom: 0,
                    child: Center(
                      child: IconButton(
                        onPressed: () =>
                            context.push(AppRoutePaths.assistantManagement),
                        icon: Icon(
                          CupertinoIcons.settings,
                          size: AppSpacing.iconMedium,
                          color: fgSecondary,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
            Expanded(
              child: _buildBody(),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildBody() {
    switch (_activeTab) {
      case 'dialog':
        return ChatDetailPage(
          conversationId: AppConceptConstants.assistantConversationId,
          onBack: () {}, // Ignored in embedded mode
          embedded: true,
        );
      case 'schedule':
        return const _AssistantScheduleView();
      case 'skills':
        return AssistantSkillCenterPage(
          onBack: () {}, // Ignored in embedded mode
          embedded: true,
        );
      default:
        return const SizedBox.shrink();
    }
  }
}

class _AssistantScheduleView extends ConsumerWidget {
  const _AssistantScheduleView();

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
        padding: EdgeInsets.all(AppSpacing.containerMd),
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
          color: isDark ? Colors.transparent : Colors.black.withValues(alpha: 0.05),
        ),
        boxShadow: isDark ? [] : [
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
                  Icon(CupertinoIcons.left_chevron, size: 16, color: fgSecondary),
                  SizedBox(width: 16),
                  Icon(CupertinoIcons.right_chevron, size: 16, color: fgSecondary),
                ],
              ),
            ],
          ),
          SizedBox(height: AppSpacing.md),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: ['日', '一', '二', '三', '四', '五', '六']
                .map((d) => Text(
                      d,
                      style: TextStyle(
                        fontSize: AppTypography.sm,
                        color: fgSecondary,
                      ),
                    ))
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
                width: 32,
                height: 32,
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
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return Container(
      padding: EdgeInsets.all(AppSpacing.containerMd),
      decoration: BoxDecoration(
        color: isDark ? Colors.white.withValues(alpha: 0.05) : Colors.white,
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        border: Border.all(
          color: isDark ? Colors.transparent : Colors.black.withValues(alpha: 0.05),
        ),
        boxShadow: isDark ? [] : [
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
