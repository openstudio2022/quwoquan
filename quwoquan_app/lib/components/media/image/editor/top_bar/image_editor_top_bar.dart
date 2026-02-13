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
    required this.onHistory,
    required this.historyEnabled,
  });

  final Color backgroundColor;
  final Color foregroundColor;
  final Color foregroundSecondary;
  final double topPadding;
  final String positionText;
  final VoidCallback onBack;
  final VoidCallback onHistory;
  final bool historyEnabled;

  @override
  Widget build(BuildContext context) {
    final topBarHeight = AppSpacing.toolbarHeight;
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
                    width: AppSpacing.iconButtonMinSizeSm,
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
                        minimumSize: Size.square(AppSpacing.iconButtonMinSizeSm),
                      ),
                    ),
                  ),
                  SizedBox(width: AppSpacing.xs),
                  Text(
                    positionText,
                    style: TextStyle(
                      color: foregroundColor,
                      fontSize: AppTypography.base,
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
              width: AppSpacing.iconButtonMinSizeSm,
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
                  minimumSize: Size.square(AppSpacing.iconButtonMinSizeSm),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}













