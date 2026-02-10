import 'package:flutter/material.dart';
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
      UITextConstants.imageEditorProTabExposure,
      UITextConstants.imageEditorProTabColor,
      UITextConstants.imageEditorProTabLight,
      UITextConstants.imageEditorProTabTexture,
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
    final fgSecondary =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap ?? () {},
        borderRadius: BorderRadius.circular(AppSpacing.smallBorderRadius),
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.sm,
            vertical: AppSpacing.xs,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(
                label,
                style: TextStyle(
                  color: selected ? AppColors.primaryColor : fgSecondary,
                  fontSize: AppTypography.sm,
                  fontWeight: selected ? FontWeight.w600 : FontWeight.normal,
                ),
              ),
              if (selected)
                Container(
                  margin: EdgeInsets.only(top: AppSpacing.xs / 2),
                  height: AppSpacing.xs / 2,
                  width: AppSpacing.iconSmall,
                  color: AppColors.primaryColor,
                ),
            ],
          ),
        ),
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

  @override
  Widget build(BuildContext context) {
    final itemWidth = AppSpacing.buttonHeight + AppSpacing.sm;
    return SizedBox(
      height: AppSpacing.bottomNavHeight,
      child: LayoutBuilder(
        builder: (context, constraints) {
          return NotificationListener<ScrollUpdateNotification>(
            onNotification: (notification) {
              onScrollSync(constraints.maxWidth, itemWidth);
              return false;
            },
            child: ListView.builder(
              controller: scrollController,
              scrollDirection: Axis.horizontal,
              padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
              itemCount: kImageEditorProToolEntries.length,
              itemBuilder: (context, index) {
                final entry = kImageEditorProToolEntries[index];
                return SizedBox(
                  width: itemWidth,
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
