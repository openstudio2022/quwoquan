import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';

class VideoCallScreenShareStatus extends StatelessWidget {
  const VideoCallScreenShareStatus({
    super.key,
    required this.visible,
    required this.canStop,
    required this.onStop,
  });

  final bool visible;
  final bool canStop;
  final VoidCallback onStop;

  @override
  Widget build(BuildContext context) {
    if (!visible) return const SizedBox.shrink();
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final foreground = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final surface = AppColorsFunctional.getColor(
      isDark,
      ColorType.glassSurface,
    );
    return Positioned(
      key: const ValueKey('video-call-screen-share-status'),
      top: MediaQuery.paddingOf(context).top + AppSpacing.xl * 4,
      left: AppSpacing.md,
      right: AppSpacing.md,
      child: Align(
        alignment: Alignment.topCenter,
        child: Container(
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.md,
            vertical: AppSpacing.sm,
          ),
          decoration: BoxDecoration(
            color: surface.withValues(alpha: 0.92),
            borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                CupertinoIcons.device_desktop,
                color: foreground,
                size: AppSpacing.iconSmall,
              ),
              SizedBox(width: AppSpacing.xs),
              Text(
                UITextConstants.callScreenSharing,
                style: TextStyle(
                  color: foreground,
                  fontSize: AppTypography.sm,
                  fontWeight: AppTypography.medium,
                ),
              ),
              if (canStop) ...[
                SizedBox(width: AppSpacing.sm),
                GestureDetector(
                  key: const ValueKey('video-call-stop-screen-share'),
                  onTap: onStop,
                  child: ConstrainedBox(
                    constraints: BoxConstraints(
                      minWidth: AppSpacing.minInteractiveSize,
                      minHeight: AppSpacing.minInteractiveSize,
                    ),
                    child: Center(
                      child: Text(
                        UITextConstants.callStopScreenSharing,
                        style: TextStyle(
                          color: AppColors.error,
                          fontSize: AppTypography.sm,
                          fontWeight: AppTypography.semiBold,
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
