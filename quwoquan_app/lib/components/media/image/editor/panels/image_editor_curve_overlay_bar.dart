import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

class ImageEditorCurveOverlayBar extends StatelessWidget {
  const ImageEditorCurveOverlayBar({
    super.key,
    required this.backgroundColor,
    required this.foregroundColor,
    required this.foregroundSecondary,
    required this.brightness,
    required this.contrast,
    required this.onBrightnessChanged,
    required this.onContrastChanged,
    required this.onCancel,
    required this.onConfirm,
  });

  final Color backgroundColor;
  final Color foregroundColor;
  final Color foregroundSecondary;
  final double brightness;
  final double contrast;
  final ValueChanged<double> onBrightnessChanged;
  final ValueChanged<double> onContrastChanged;
  final VoidCallback onCancel;
  final VoidCallback onConfirm;

  @override
  Widget build(BuildContext context) {
    final borderColor = AppColorsFunctional.getColor(
      true,
      ColorType.borderPrimary,
    ).withValues(alpha: 0.3);
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.semantic[DesignSemanticConstants.container]
                ?[DesignSemanticConstants.sm] ??
            AppSpacing.containerSm,
        vertical: AppSpacing.sm,
      ),
      decoration: BoxDecoration(
        color: backgroundColor,
        border: Border(top: BorderSide(color: borderColor)),
      ),
      child: SafeArea(
        top: false,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              UITextConstants.imageEditorProCurve,
              style: TextStyle(
                color: foregroundColor,
                fontSize: AppTypography.sm,
                fontWeight: FontWeight.w600,
              ),
            ),
            SizedBox(height: AppSpacing.xs),
            Row(
              children: [
                Expanded(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        UITextConstants.imageEditorProBrightness,
                        style: TextStyle(
                          fontSize: AppTypography.xs,
                          color: foregroundSecondary,
                        ),
                      ),
                      SliderTheme(
                        data: SliderThemeData(
                          activeTrackColor: AppColors.primaryColor,
                          thumbColor: AppColors.primaryColor,
                        ),
                        child: Slider(
                          value: brightness,
                          onChanged: onBrightnessChanged,
                        ),
                      ),
                    ],
                  ),
                ),
                Expanded(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        UITextConstants.imageEditorProContrast,
                        style: TextStyle(
                          fontSize: AppTypography.xs,
                          color: foregroundSecondary,
                        ),
                      ),
                      SliderTheme(
                        data: SliderThemeData(
                          activeTrackColor: AppColors.primaryColor,
                          thumbColor: AppColors.primaryColor,
                        ),
                        child: Slider(
                          value: contrast,
                          onChanged: onContrastChanged,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                CupertinoButton(
                  padding: EdgeInsets.zero,
                  minimumSize: Size.square(AppSpacing.minInteractiveSize),
                  onPressed: onCancel,
                  child: Icon(
                    CupertinoIcons.xmark,
                    color: AppColors.white,
                    size: AppSpacing.iconMedium,
                  ),
                ),
                CupertinoButton(
                  padding: EdgeInsets.zero,
                  minimumSize: Size.square(AppSpacing.minInteractiveSize),
                  onPressed: onConfirm,
                  child: Icon(
                    CupertinoIcons.checkmark,
                    color: AppColors.white,
                    size: AppSpacing.iconMedium,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
