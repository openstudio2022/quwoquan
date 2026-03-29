import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/components/media/image/editor/tool_list/image_editor_pro_tool_entries.dart';
import 'package:quwoquan_app/components/media/image/editor/tool_list/image_editor_tool_entry_chip.dart';

class ImageEditorProCategoryTabs extends StatelessWidget {
  const ImageEditorProCategoryTabs({
    super.key,
    required this.selectedCategory,
    required this.onCategoryTap,
  });

  final int selectedCategory;
  final ValueChanged<int> onCategoryTap;

  @override
  Widget build(BuildContext context) {
    final tabs = [
      UITextConstants.imageEditorProTabOverall,
      UITextConstants.imageEditorProTabLocal,
      UITextConstants.imageEditorProTabHsl,
      UITextConstants.imageEditorProTabCurve,
    ];
    return SizedBox(
      height: AppSpacing.subTabNavigationHeight,
      child: ListView.builder(
        scrollDirection: Axis.horizontal,
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.containerSm,
          vertical: AppSpacing.xs,
        ),
        itemCount: tabs.length,
        itemBuilder: (context, index) {
          return Padding(
            padding: EdgeInsets.only(right: AppSpacing.intraGroupSm),
            child: _panelChip(
              tabs[index],
              selectedCategory == index,
              onTap: () => onCategoryTap(index),
            ),
          );
        },
      ),
    );
  }

  Widget _panelChip(
    String label,
    bool selected, {
    VoidCallback? onTap,
  }) {
    const isDark = true;
    final fg = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    return CupertinoButton(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.sm,
        vertical: AppSpacing.xs,
      ),
      minimumSize: Size.zero,
      onPressed: onTap ?? () {},
      child: Column(
        mainAxisSize: MainAxisSize.min,
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Text(
            label,
            style: TextStyle(
              color: selected ? fg : fgSecondary.withValues(alpha: 0.75),
              fontSize: AppTypography.sm,
              fontWeight: selected ? FontWeight.w600 : FontWeight.normal,
            ),
          ),
          Container(
            margin: EdgeInsets.only(top: AppSpacing.xs / 2),
            height: AppSpacing.xs / 2,
            width: AppSpacing.iconSmall,
            decoration: BoxDecoration(
              color: selected ? fg : AppColors.transparent,
              borderRadius: BorderRadius.circular(AppSpacing.xs / 4),
            ),
          ),
        ],
      ),
    );
  }
}

class ImageEditorProToolList extends StatelessWidget {
  const ImageEditorProToolList({
    super.key,
    required this.selectedToolIndex,
    required this.scrollController,
    required this.onToolTap,
    required this.onScrollSync,
  });

  final int? selectedToolIndex;
  final ScrollController scrollController;
  final ValueChanged<int> onToolTap;
  final void Function(double viewportWidth, double itemWidth) onScrollSync;

  /// 与裁剪、调整面板、底部工具栏一致：containerSm 边距、intraGroupSm 项间距、buttonHeight*1.4 单项宽度
  static const _gap = AppSpacing.intraGroupSm;
  static const _itemWidth = AppSpacing.buttonHeight * 1.4;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: AppSpacing.bottomNavHeight,
      child: LayoutBuilder(
        builder: (context, constraints) {
          return NotificationListener<ScrollUpdateNotification>(
            onNotification: (_) {
              onScrollSync(constraints.maxWidth, _itemWidth);
              return false;
            },
            child: ListView.separated(
              controller: scrollController,
              scrollDirection: Axis.horizontal,
              padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
              itemCount: kImageEditorProToolEntries.length,
              separatorBuilder: (context, index) => SizedBox(width: _gap),
              itemBuilder: (context, index) {
                final entry = kImageEditorProToolEntries[index];
                return SizedBox(
                  width: _itemWidth,
                  child: ImageEditorToolEntryChip(
                    icon: entry.icon,
                    label: entry.label,
                    isSelected: selectedToolIndex == index,
                    onTap: () => onToolTap(index),
                  ),
                );
              },
            ),
          );
        },
      ),
    );
  }
}
