import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/components/media/image/editor/icons/image_editor_semantic_icon.dart';
import 'package:quwoquan_app/components/media/image/editor/tool_list/image_editor_tool_entry_chip.dart';
import 'package:quwoquan_app/components/media/shared/media_creation_bottom_button.dart';

class ImageEditorBottomBar extends StatelessWidget {
  const ImageEditorBottomBar({
    super.key,
    required this.backgroundColor,
    required this.foregroundColor,
    required this.foregroundSecondary,
    required this.bottomPadding,
    required this.selectedToolIndex,
    required this.onToolSelected,
    required this.onNextStep,
  });

  final Color backgroundColor;
  final Color foregroundColor;
  final Color foregroundSecondary;
  final double bottomPadding;
  final int? selectedToolIndex;
  final ValueChanged<int> onToolSelected;
  final VoidCallback onNextStep;

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
    final barHeight = AppSpacing.bottomNavHeight - AppSpacing.xs;
    final nextButtonHeight = AppSpacing.minInteractiveSize;
    final borderColor = AppColorsFunctional.getColor(
      true,
      ColorType.borderPrimary,
    ).withValues(alpha: 0.3);

    return Container(
      height:
          bottomPadding +
          barHeight +
          nextButtonHeight +
          AppSpacing.intraGroupSm,
      padding: EdgeInsets.only(bottom: bottomPadding),
      decoration: BoxDecoration(
        color: backgroundColor,
        border: Border(top: BorderSide(color: borderColor)),
      ),
      child: LayoutBuilder(
        builder: (context, constraints) {
          final sidePadding = AppSpacing.containerSm;
          final gap = AppSpacing.interGroupSm;
          final itemWidth = AppSpacing.buttonHeight * 1.32;
          return Column(
            children: [
              SizedBox(
                height: barHeight,
                child: ListView.separated(
                  scrollDirection: Axis.horizontal,
                  padding: EdgeInsets.symmetric(horizontal: sidePadding),
                  itemCount: toolEntries.length,
                  separatorBuilder: (context, index) => SizedBox(width: gap),
                  itemBuilder: (context, index) {
                    final entry = toolEntries[index];
                    return SizedBox(
                      width: itemWidth,
                      height: barHeight,
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
              ),
              Padding(
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.containerMd,
                ),
                child: SizedBox(
                  width: double.infinity,
                  child: MediaCreationBottomButton(
                    label: UITextConstants.mediaPickerNextStep,
                    variant: MediaCreationBottomButtonVariant.fullWidthNeutral,
                    height: nextButtonHeight,
                    onPressed: onNextStep,
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}
