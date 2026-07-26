part of 'global_search_page.dart';

class _SearchHistoryToolbar extends StatelessWidget {
  const _SearchHistoryToolbar({
    required this.expanded,
    required this.managing,
    required this.onToggleExpanded,
    required this.onStartManaging,
    required this.onClearAll,
    required this.onDone,
  });

  final bool expanded;
  final bool managing;
  final VoidCallback onToggleExpanded;
  final VoidCallback onStartManaging;
  final VoidCallback onClearAll;
  final VoidCallback onDone;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final fgTertiary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundTertiary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final divider = AppColorsFunctional.getColor(
      isDark,
      ColorType.separatorSubtle,
    );
    return Row(
      children: [
        Expanded(
          child: Text(
            UITextConstants.searchHistoryTitle,
            style: TextStyle(
              fontSize: _SearchTokens.toolbarSize,
              fontWeight: _SearchTokens.toolbarWeight,
              color: fgTertiary,
            ),
          ),
        ),
        if (managing) ...[
          CupertinoButton(
            key: TestKeys.searchHistoryClearButton,
            padding: EdgeInsets.zero,
            minimumSize: Size.zero,
            onPressed: onClearAll,
            child: Text(
              UITextConstants.searchHistoryDeleteAll,
              style: TextStyle(
                fontSize: _SearchTokens.toolbarSize,
                fontWeight: _SearchTokens.toolbarActionWeight,
                color: fgSecondary,
              ),
            ),
          ),
          SizedBox(width: AppSpacing.interGroupMd),
          CupertinoButton(
            key: TestKeys.searchHistoryDoneButton,
            padding: EdgeInsets.zero,
            minimumSize: Size.zero,
            onPressed: onDone,
            child: Text(
              UITextConstants.searchHistoryDone,
              style: TextStyle(
                fontSize: _SearchTokens.toolbarSize,
                fontWeight: _SearchTokens.toolbarActionWeight,
                color: fgSecondary,
              ),
            ),
          ),
        ] else ...[
          CupertinoButton(
            key: TestKeys.searchHistoryExpandButton,
            padding: EdgeInsets.zero,
            minimumSize: Size.zero,
            onPressed: onToggleExpanded,
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  expanded
                      ? UITextConstants.searchHistoryCollapse
                      : UITextConstants.searchHistoryExpand,
                  style: TextStyle(
                    fontSize: _SearchTokens.toolbarSize,
                    fontWeight: _SearchTokens.toolbarWeight,
                    color: fgTertiary,
                  ),
                ),
                SizedBox(width: AppSpacing.intraGroupXs),
                Icon(
                  expanded
                      ? CupertinoIcons.chevron_up
                      : CupertinoIcons.chevron_down,
                  size: AppSpacing.iconSmall,
                  color: fgTertiary,
                ),
              ],
            ),
          ),
          Padding(
            padding: EdgeInsets.symmetric(horizontal: AppSpacing.interGroupSm),
            child: SizedBox(
              width: AppSpacing.hairline,
              height: AppSpacing.iconMedium,
              child: DecoratedBox(decoration: BoxDecoration(color: divider)),
            ),
          ),
          CupertinoButton(
            key: TestKeys.searchHistoryManageButton,
            padding: EdgeInsets.zero,
            minimumSize: Size.square(AppSpacing.iconButtonMinSizeSm),
            onPressed: onStartManaging,
            child: Icon(
              CupertinoIcons.delete,
              size: AppSpacing.iconMedium,
              color: fgTertiary,
            ),
          ),
        ],
      ],
    );
  }
}

class _SearchHistoryGridItem extends StatelessWidget {
  const _SearchHistoryGridItem({
    required this.entry,
    required this.isDark,
    required this.managing,
    required this.onTap,
    required this.onRemove,
  });

  final RecentSearchEntryView entry;
  final bool isDark;
  final bool managing;
  final VoidCallback? onTap;
  final VoidCallback? onRemove;

  @override
  Widget build(BuildContext context) {
    final pres = RecentSearchReadPresentation.fromEntry(entry);
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgTertiary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundTertiary,
    );
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.zero,
      onPressed: managing ? () {} : onTap,
      child: Row(
        children: [
          Expanded(
            child: Text(
              pres.displayQuery,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: _SearchTokens.bodySize,
                fontWeight: _SearchTokens.bodyWeight,
                color: fgPrimary,
                height: AppTypography.lineHeightTight,
              ),
            ),
          ),
          if (managing && onRemove != null) ...[
            SizedBox(width: AppSpacing.intraGroupSm),
            GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: onRemove,
              child: SizedBox.square(
                dimension: AppSpacing.iconButtonMinSizeSm,
                child: Center(
                  child: Icon(
                    CupertinoIcons.xmark,
                    size: AppSpacing.iconSmall,
                    color: fgTertiary,
                  ),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _SearchSectionHeader extends StatelessWidget {
  const _SearchSectionHeader({required this.title});

  final String title;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    return Row(
      children: [
        Expanded(
          child: Text(
            title,
            style: TextStyle(
              fontSize: _SearchTokens.sectionTitleSize,
              fontWeight: _SearchTokens.sectionTitleWeight,
              color: fgPrimary,
            ),
          ),
        ),
      ],
    );
  }
}
