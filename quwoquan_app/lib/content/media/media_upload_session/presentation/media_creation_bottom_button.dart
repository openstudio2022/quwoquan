import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

enum MediaCreationBottomButtonVariant {
  partialPrimary,
  secondaryNeutral,
  fullWidthNeutral,
}

class MediaCreationBottomButton extends StatelessWidget {
  const MediaCreationBottomButton({
    super.key,
    required this.label,
    required this.variant,
    required this.onPressed,
    this.isLoading = false,
    this.height = AppSpacing.minInteractiveSize,
  });

  final String label;
  final MediaCreationBottomButtonVariant variant;
  final VoidCallback? onPressed;
  final bool isLoading;
  final double height;

  bool get _enabled => onPressed != null && !isLoading;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final foreground = _foregroundColor(isDark);
    final borderColor = _borderColor(isDark);
    final decoration = _decoration(isDark, borderColor);

    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: _enabled ? onPressed : null,
      child: AnimatedOpacity(
        duration: const Duration(milliseconds: 120),
        opacity: _enabled ? 1 : 0.48,
        child: Container(
          height: height,
          alignment: Alignment.center,
          decoration: decoration,
          child: isLoading
              ? CupertinoActivityIndicator(color: foreground)
              : Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: foreground,
                    fontSize: AppTypography.base,
                    fontWeight: AppTypography.semiBold,
                    height: AppTypography.lineHeightTight,
                  ),
                ),
        ),
      ),
    );
  }

  Color _foregroundColor(bool isDark) {
    if (variant == MediaCreationBottomButtonVariant.fullWidthNeutral) {
      return AppColors.white.withValues(alpha: _enabled ? 0.92 : 0.42);
    }
    if (!_enabled) {
      return AppColorsFunctional.getColor(isDark, ColorType.foregroundTertiary);
    }
    return AppColors.white;
  }

  Color _borderColor(bool isDark) {
    switch (variant) {
      case MediaCreationBottomButtonVariant.partialPrimary:
        return AppColors.primaryColorActive.withValues(alpha: 0.72);
      case MediaCreationBottomButtonVariant.secondaryNeutral:
      case MediaCreationBottomButtonVariant.fullWidthNeutral:
        return AppColors.white.withValues(alpha: isDark ? 0.16 : 0.22);
    }
  }

  BoxDecoration _decoration(bool isDark, Color borderColor) {
    final radius = BorderRadius.circular(AppSpacing.borderRadius);
    if (variant == MediaCreationBottomButtonVariant.partialPrimary) {
      return BoxDecoration(
        color: AppColors.primaryColor,
        borderRadius: radius,
        border: Border.all(color: borderColor, width: AppSpacing.hairline),
      );
    }

    final base = AppColorsFunctional.getColor(
      variant == MediaCreationBottomButtonVariant.fullWidthNeutral
          ? true
          : isDark,
      ColorType.surfaceElevated,
    );
    return BoxDecoration(
      color: base.withValues(alpha: _enabled ? 0.86 : 0.58),
      borderRadius: radius,
      border: Border.all(color: borderColor, width: AppSpacing.hairline),
    );
  }
}
