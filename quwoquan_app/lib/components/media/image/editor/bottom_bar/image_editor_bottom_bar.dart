import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/components/media/image/editor/tool_list/image_editor_tool_entry_chip.dart';
import 'package:quwoquan_app/components/media/image/editor/tool_list/image_editor_tool_constants.dart';

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
      (icon: Icons.crop, labelKey: UITextConstants.imageEditorCrop),
      (icon: Icons.rotate_right, labelKey: UITextConstants.imageEditorRotate),
      (icon: Icons.filter, labelKey: UITextConstants.imageEditorFilter),
      (icon: Icons.auto_fix_high, labelKey: UITextConstants.imageEditorBeauty),
      (icon: Icons.text_fields, labelKey: UITextConstants.imageEditorText),
      (icon: Icons.grid_on, labelKey: UITextConstants.imageEditorMosaic),
      (icon: Icons.crop_free, labelKey: UITextConstants.imageEditorFrame),
      (icon: Icons.tune, labelKey: UITextConstants.imageEditorProTools),
    ];
    final barHeight = AppSpacing.bottomNavHeight;
    final borderColor = AppColorsFunctional.getColor(
      true,
      ColorType.borderPrimary,
    ).withValues(alpha: 0.3);

    return Container(
      height: bottomPadding + barHeight,
      padding: EdgeInsets.only(bottom: bottomPadding),
      decoration: BoxDecoration(
        color: backgroundColor,
        border: Border(top: BorderSide(color: borderColor)),
      ),
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.containerSm,
          vertical: AppSpacing.xs,
        ),
        itemCount: toolEntries.length,
        separatorBuilder: (_, __) => SizedBox(width: AppSpacing.intraGroupMd),
        itemBuilder: (context, index) {
          final entry = toolEntries[index];
          return ImageEditorToolEntryChip(
            icon: entry.icon,
            label: entry.labelKey,
            isSelected: selectedToolIndex == index,
            onTap: () => onToolSelected(index),
          );
        },
      ),
    );
  }
}
