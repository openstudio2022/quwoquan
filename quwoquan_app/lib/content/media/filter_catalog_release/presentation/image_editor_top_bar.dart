import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';

class ImageEditorTopBar extends StatelessWidget {
  const ImageEditorTopBar({
    super.key,
    required this.backgroundColor,
    required this.foregroundColor,
    required this.foregroundSecondary,
    required this.topPadding,
    required this.positionText,
    required this.onBack,
    required this.canUndo,
    required this.canRedo,
    required this.onUndo,
    required this.onRedo,
    required this.onHistory,
    required this.historyEnabled,
    required this.onDone,
  });

  final Color backgroundColor;
  final Color foregroundColor;
  final Color foregroundSecondary;
  final double topPadding;
  final String positionText;
  final VoidCallback onBack;
  final bool canUndo;
  final bool canRedo;
  final VoidCallback onUndo;
  final VoidCallback onRedo;
  final VoidCallback onHistory;
  final bool historyEnabled;
  final VoidCallback onDone;

  @override
  Widget build(BuildContext context) {
    final topBarHeight = AppSpacing.appChromeNavigationBarHeight;
    final effectiveTopPadding = AppSpacing.appChromeTopSafeInset(
      topPadding,
      context,
    );
    final disabledColor = foregroundSecondary.withValues(alpha: 0.35);
    return Container(
      height: effectiveTopPadding + topBarHeight,
      padding: EdgeInsets.only(top: effectiveTopPadding),
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
                    width: AppSpacing.appChromeActionButtonSize,
                    height: topBarHeight,
                    child: CupertinoButton(
                      padding: EdgeInsets.zero,
                      minimumSize: Size.square(
                        AppSpacing.appChromeActionButtonSize,
                      ),
                      onPressed: onBack,
                      child: Icon(
                        CupertinoIcons.back,
                        color: foregroundColor,
                        size: AppSpacing.appChromeActionIconSize,
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
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                _buildIconAction(
                  icon: CupertinoIcons.arrow_uturn_left,
                  enabled: canUndo,
                  onPressed: onUndo,
                  topBarHeight: topBarHeight,
                  enabledColor: foregroundColor,
                  disabledColor: disabledColor,
                ),
                _buildIconAction(
                  icon: CupertinoIcons.arrow_uturn_right,
                  enabled: canRedo,
                  onPressed: onRedo,
                  topBarHeight: topBarHeight,
                  enabledColor: foregroundColor,
                  disabledColor: disabledColor,
                ),
                _buildIconAction(
                  icon: CupertinoIcons.clock,
                  enabled: historyEnabled,
                  onPressed: onHistory,
                  topBarHeight: topBarHeight,
                  enabledColor: foregroundColor,
                  disabledColor: disabledColor,
                ),
              ],
            ),
          ),
          Align(
            alignment: Alignment.centerRight,
            child: Padding(
              padding: EdgeInsets.only(right: AppSpacing.containerSm),
              child: SizedBox(
                height: topBarHeight,
                child: CupertinoButton(
                  padding: EdgeInsets.symmetric(horizontal: AppSpacing.sm),
                  minimumSize: Size.square(
                    AppSpacing.appChromeActionButtonSize,
                  ),
                  onPressed: onDone,
                  child: Text(
                    MediaText.imageEditDone,
                    style: TextStyle(
                      color: foregroundColor,
                      fontSize: AppTypography.base,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildIconAction({
    required IconData icon,
    required bool enabled,
    required VoidCallback onPressed,
    required double topBarHeight,
    required Color enabledColor,
    required Color disabledColor,
  }) {
    return SizedBox(
      width: AppSpacing.appChromeActionButtonSize,
      height: topBarHeight,
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        minimumSize: Size.square(AppSpacing.appChromeActionButtonSize),
        onPressed: enabled ? onPressed : null,
        child: Icon(
          icon,
          color: enabled ? enabledColor : disabledColor,
          size: AppSpacing.appChromeActionIconSize,
        ),
      ),
    );
  }
}
