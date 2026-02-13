import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:quwoquan_app/core/quwoquan_core.dart';

// ignore_for_file: unused_local_variable

/// Tab 项定义
class TabItem {
  final String id;
  final String label;

  const TabItem({required this.id, required this.label});
}

enum TabNavigationMode {
  compactPill,
  mixedScrollable,
}

class TabNavigationWidget extends ConsumerWidget {
  final String activeTab;
  final Function(String) onTabChange;
  final bool? isDark;
  /// 可选：自定义 Tab 列表。不传则使用默认（发现页：推荐/图片/视频/文章）
  final List<TabItem>? tabs;
  final TabNavigationMode? mode;
  final List<String> fixedTabIds;
  final GestureDragEndCallback? onHorizontalDragEnd;
  final List<Widget> trailingActions;

  const TabNavigationWidget({
    super.key,
    required this.activeTab,
    required this.onTabChange,
    this.isDark,
    this.tabs,
    this.mode,
    this.fixedTabIds = const <String>['following', 'recommended'],
    this.onHorizontalDragEnd,
    this.trailingActions = const <Widget>[],
  });

  static const List<TabItem> discoveryTabs = [
    TabItem(id: 'recommended', label: '推荐'),
    TabItem(id: 'images', label: '图片'),
    TabItem(id: 'video', label: '视频'),
    TabItem(id: 'articles', label: '文章'),
  ];

  static const List<TabItem> defaultTabs = [
    TabItem(id: 'following', label: '关注'),
    TabItem(id: 'recommended', label: '推荐'),
    TabItem(id: 'images', label: '图片'),
    TabItem(id: 'video', label: '视频'),
    TabItem(id: 'articles', label: '文章'),
    TabItem(id: 'moments', label: '动态'),
  ];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final currentIsDark = (isDark ?? ref.watch(effectiveIsDarkProvider))!;
    final tabList = tabs ?? defaultTabs;
    final resolvedMode = mode ??
        (tabList.length <= 4
            ? TabNavigationMode.compactPill
            : TabNavigationMode.mixedScrollable);
    final bg = AppColorsFunctional.getColor(
      currentIsDark,
      ColorType.backgroundPrimary,
    );
    final fg = AppColorsFunctional.getColor(
      currentIsDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      currentIsDark,
      ColorType.foregroundSecondary,
    );
    final horizontalPadding = AppSpacing.responsiveValue(
      context,
      compact: AppSpacing.intraGroupSm,
      regular: AppSpacing.containerSm,
      expanded: AppSpacing.containerMd,
    );

    final borderColor = AppColorsFunctional.getColor(
      currentIsDark,
      ColorType.borderPrimary,
    );
    final navContent = resolvedMode == TabNavigationMode.compactPill
        ? _buildCompactPillNav(
            context,
            tabList,
            currentIsDark,
            fg,
            fgSecondary,
          )
        : _buildMixedScrollableNav(
            context,
            tabList,
            currentIsDark,
            fg,
            fgSecondary,
          );

    return Container(
      height: AppSpacing.tabNavigationHeight,
      decoration: BoxDecoration(
        color: bg,
        border: Border(
          bottom: BorderSide(
            color: borderColor.withValues(alpha: 0.3),
            width: 0.5,
          ),
        ),
      ),
      padding: EdgeInsets.symmetric(horizontal: horizontalPadding),
      child: Row(
        children: [
          Expanded(
            child: GestureDetector(
              behavior: HitTestBehavior.translucent,
              onHorizontalDragEnd: onHorizontalDragEnd,
              child: navContent,
            ),
          ),
          if (trailingActions.isNotEmpty) ...[
            SizedBox(width: AppSpacing.intraGroupXs),
            ...trailingActions,
          ],
        ],
      ),
    );
  }

  Widget _buildCompactPillNav(
    BuildContext context,
    List<TabItem> tabList,
    bool isDark,
    Color fg,
    Color fgSecondary,
  ) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        for (var i = 0; i < tabList.length; i++)
          _buildTabChip(
            context: context,
            tab: tabList[i],
            selected: tabList[i].id == activeTab,
            isDark: isDark,
            fg: fg,
            fgSecondary: fgSecondary,
          ),
      ],
    );
  }

  Widget _buildMixedScrollableNav(
    BuildContext context,
    List<TabItem> tabList,
    bool isDark,
    Color fg,
    Color fgSecondary,
  ) {
    final fixedSet = fixedTabIds.toSet();
    final fixedTabs = <TabItem>[
      for (final id in fixedTabIds)
        ...tabList.where((tab) => tab.id == id),
    ];
    final scrollTabs = tabList
        .where((tab) => !fixedSet.contains(tab.id))
        .toList(growable: false);

    return Row(
      children: [
        for (final tab in fixedTabs)
          _buildTabChip(
            context: context,
            tab: tab,
            selected: tab.id == activeTab,
            isDark: isDark,
            fg: fg,
            fgSecondary: fgSecondary,
          ),
        Expanded(
          child: ListView.builder(
            scrollDirection: Axis.horizontal,
            itemCount: scrollTabs.length,
            itemBuilder: (context, index) => _buildTabChip(
              context: context,
              tab: scrollTabs[index],
              selected: scrollTabs[index].id == activeTab,
              isDark: isDark,
              fg: fg,
              fgSecondary: fgSecondary,
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildTabChip({
    required BuildContext context,
    required TabItem tab,
    required bool selected,
    required bool isDark,
    required Color fg,
    required Color fgSecondary,
  }) {
    final chipFontSize = AppTypography.responsive(
      context,
      compact: AppTypography.sm,
      regular: AppTypography.base,
      expanded: AppTypography.lg,
    );

    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: () => onTabChange(tab.id),
        borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.intraGroupMd,
          ),
          child: ConstrainedBox(
            constraints: BoxConstraints(
              minWidth: AppSpacing.minInteractiveSize,
              minHeight: AppSpacing.minInteractiveSize,
            ),
            child: IntrinsicWidth(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    tab.label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: chipFontSize,
                      fontWeight: selected
                          ? AppTypography.bold
                          : AppTypography.medium,
                      color: selected ? fg : fgSecondary,
                    ),
                  ),
                  SizedBox(height: AppSpacing.intraGroupXs),
                  AnimatedContainer(
                    duration: const Duration(milliseconds: 200),
                    height: AppSpacing.intraGroupXs / 2,
                    decoration: BoxDecoration(
                      color: selected ? fg : Colors.transparent,
                      borderRadius: BorderRadius.circular(
                        AppSpacing.intraGroupXs / 4,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}