import 'package:flutter/material.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/presentation/image_editor_tool_constants.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/presentation/image_editor_tool_entry_chip.dart';
import 'package:quwoquan_app/design_system/media/media_creation_bottom_button.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';

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
        builder: (context, _) {
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
                  itemCount: kImageEditorToolEntries.length,
                  separatorBuilder: (context, index) => SizedBox(width: gap),
                  itemBuilder: (context, index) {
                    final entry = kImageEditorToolEntries[index];
                    return SizedBox(
                      width: itemWidth,
                      height: barHeight,
                      child: Center(
                        child: ImageEditorToolEntryChip(
                          icon: entry.icon,
                          semanticIconKey: entry.semanticIconKey,
                          label: entry.label,
                          isSelected: selectedToolIndex == entry.index,
                          onTap: () => onToolSelected(entry.index),
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
                    label: MediaText.mediaPickerNextStep,
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
