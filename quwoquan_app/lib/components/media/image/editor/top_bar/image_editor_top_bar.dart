import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

class ImageEditorTopBar extends StatelessWidget {
  const ImageEditorTopBar({
    super.key,
    required this.backgroundColor,
    required this.foregroundColor,
    required this.foregroundSecondary,
    required this.topPadding,
    required this.positionText,
    required this.onBack,
    required this.onDone,
    required this.doneEnabled,
    required this.onHistory,
    required this.historyEnabled,
  });

  final Color backgroundColor;
  final Color foregroundColor;
  final Color foregroundSecondary;
  final double topPadding;
  final String positionText;
  final VoidCallback onBack;
  final VoidCallback onDone;
  /// 有编辑时可点，样式为蓝底白字；无编辑时不可点，样式与重置按钮一致（灰底、同间距圆角字号字色）
  final bool doneEnabled;
  final VoidCallback onHistory;
  final bool historyEnabled;

  @override
  Widget build(BuildContext context) {
    final topBarHeight = AppSpacing.tabNavigationHeight;
    return Container(
      height: topPadding + topBarHeight,
      padding: EdgeInsets.only(top: topPadding),
      color: backgroundColor,
      child: Stack(
        alignment: Alignment.center,
        children: [
          Align(
            alignment: Alignment.centerLeft,
            child: Padding(
              padding: EdgeInsets.only(left: AppSpacing.containerSm),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  SizedBox(
                    width: AppSpacing.buttonHeight,
                    height: topBarHeight,
                    child: IconButton(
                      icon: Icon(
                        Icons.arrow_back_ios_new,
                        color: foregroundColor,
                        size: AppSpacing.iconMedium,
                      ),
                      onPressed: onBack,
                      style: IconButton.styleFrom(
                        padding: EdgeInsets.zero,
                        minimumSize: Size.zero,
                        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                      ),
                    ),
                  ),
                  SizedBox(width: AppSpacing.xs),
                  Text(
                    positionText,
                    style: TextStyle(
                      color: foregroundColor,
                      fontSize: AppTypography.md,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ],
              ),
            ),
          ),
          Align(
            alignment: Alignment.center,
            child: SizedBox(
              width: AppSpacing.buttonHeight,
              height: topBarHeight,
              child: IconButton(
                icon: Icon(
                  Icons.history,
                  color: foregroundColor,
                  size: AppSpacing.iconMedium,
                ),
                onPressed: historyEnabled ? onHistory : null,
                style: IconButton.styleFrom(
                  padding: EdgeInsets.zero,
                  minimumSize: Size.zero,
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                ),
              ),
            ),
          ),
          Align(
            alignment: Alignment.centerRight,
            child: Padding(
              padding: EdgeInsets.only(right: AppSpacing.containerSm),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  SizedBox(
                    height: AppSpacing.buttonHeightForSize(DesignSemanticConstants.md),
                    child: Material(
                      color: doneEnabled
                          ? AppColors.primaryColor
                          : foregroundSecondary.withValues(alpha: 0.12),
                      borderRadius: BorderRadius.circular(
                        AppSpacing.largeBorderRadius,
                      ),
                      child: InkWell(
                        onTap: doneEnabled ? onDone : null,
                        borderRadius: BorderRadius.circular(
                          AppSpacing.largeBorderRadius,
                        ),
                        child: Padding(
                          padding: AppSpacing.buttonPadding(
                            context,
                            DesignSemanticConstants.md,
                          ),
                          child: Center(
                            child: Text(
                              UITextConstants.imageEditDone,
                              style: TextStyle(
                                color: doneEnabled
                                    ? AppColors.white
                                    : foregroundColor,
                                fontSize: AppTypography.md,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
