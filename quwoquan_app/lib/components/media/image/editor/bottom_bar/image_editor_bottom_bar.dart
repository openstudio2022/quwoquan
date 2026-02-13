import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/components/media/image/editor/icons/image_editor_semantic_icon.dart';
import 'package:quwoquan_app/components/media/image/editor/tool_list/image_editor_tool_entry_chip.dart';

class ImageEditorBottomBar extends StatelessWidget {
  const ImageEditorBottomBar({
    super.key,
    required this.backgroundColor,
    required this.foregroundColor,
    required this.foregroundSecondary,
    required this.bottomPadding,
    required this.selectedToolIndex,
    required this.onToolSelected,
  });

  final Color backgroundColor;
  final Color foregroundColor;
  final Color foregroundSecondary;
  final double bottomPadding;
  final int? selectedToolIndex;
  final ValueChanged<int> onToolSelected;

  @override
  Widget build(BuildContext context) {
    const toolEntries = [
      (
        icon: Icons.circle_outlined,
        semanticIconKey: kEditorIconFilterRings,
        labelKey: UITextConstants.imageEditorFilter,
      ),
      (
        icon: Icons.crop,
        semanticIconKey: null,
        labelKey: UITextConstants.imageEditorCrop,
      ),
      (
        icon: Icons.rotate_right,
        semanticIconKey: null,
        labelKey: UITextConstants.imageEditorRotate,
      ),
      (
        icon: Icons.auto_fix_high,
        semanticIconKey: null,
        labelKey: UITextConstants.imageEditorProTools,
      ),
      (
        icon: Icons.crop_free,
        semanticIconKey: null,
        labelKey: UITextConstants.imageEditorFrame,
      ),
      (
        icon: Icons.text_fields,
        semanticIconKey: null,
        labelKey: UITextConstants.imageEditorText,
      ),
      (
        icon: Icons.grid_on,
        semanticIconKey: null,
        labelKey: UITextConstants.imageEditorMosaic,
      ),
    ];
    final barHeight = AppSpacing.bottomNavHeight;
    final borderColor = AppColorsFunctional.getColor(
      true,
      ColorType.borderPrimary,
    ).withValues(alpha: 0.3);

    return Container(
      height: bottomPadding + barHeight + AppSpacing.xs,
      padding: EdgeInsets.only(bottom: bottomPadding),
      decoration: BoxDecoration(
        color: backgroundColor,
        border: Border(top: BorderSide(color: borderColor)),
      ),
      child: LayoutBuilder(
        builder: (context, constraints) {
          final sidePadding = AppSpacing.containerSm;
          final gap = AppSpacing.interGroupSm;
          final itemWidth = AppSpacing.buttonHeight * 1.5;
          final contentHeight =
              (constraints.maxHeight - 2 * AppSpacing.xs)
                  .clamp(AppSpacing.minInteractiveSize, 84.0);
          return SizedBox(
            height: constraints.maxHeight,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              padding: EdgeInsets.symmetric(
                horizontal: sidePadding,
                vertical: AppSpacing.xs,
              ),
              itemCount: toolEntries.length,
              separatorBuilder: (context, index) => SizedBox(width: gap),
              itemBuilder: (context, index) {
                final entry = toolEntries[index];
                return SizedBox(
                  width: itemWidth,
                  height: contentHeight,
                  child: Center(
                    child: ImageEditorToolEntryChip(
                      icon: entry.icon,
                      semanticIconKey: entry.semanticIconKey,
                      label: entry.labelKey,
                      isSelected: selectedToolIndex == index,
                      onTap: () => onToolSelected(index),
                    ),
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
