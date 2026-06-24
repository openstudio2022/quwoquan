import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

class PublishConfirmSheetEntrance extends StatelessWidget {
  const PublishConfirmSheetEntrance({
    super.key,
    required this.child,
    required this.visible,
    this.beginOffsetY = 0.04,
    this.beginScale = 0.985,
  });

  final Widget child;
  final bool visible;
  final double beginOffsetY;
  final double beginScale;

  @override
  Widget build(BuildContext context) {
    return AnimatedSlide(
      offset: visible ? Offset.zero : Offset(0, beginOffsetY),
      duration: const Duration(milliseconds: 360),
      curve: Curves.easeOutCubic,
      child: AnimatedScale(
        scale: visible ? 1 : beginScale,
        duration: const Duration(milliseconds: 420),
        curve: Curves.easeOutCubic,
        child: AnimatedOpacity(
          opacity: visible ? 1 : 0,
          duration: const Duration(milliseconds: 240),
          curve: Curves.easeOutCubic,
          child: child,
        ),
      ),
    );
  }
}

class PublishConfirmSettingRow extends StatelessWidget {
  const PublishConfirmSettingRow({
    super.key,
    required this.title,
    required this.value,
    this.onTap,
    this.borderRadius = BorderRadius.zero,
  });

  final String title;
  final String value;
  final VoidCallback? onTap;
  final BorderRadius borderRadius;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    return IosSelectionOptionTile(
      title: Text(
        title,
        style: TextStyle(
          color: AppColors.iosLabel(context),
          fontSize: AppTypography.iosCallout,
          fontWeight: AppTypography.normal,
        ),
      ),
      additionalInfo: value,
      additionalInfoTextStyle: TextStyle(
        color: SettingsSemanticConstants.createSettingItemValueColor(isDark),
        fontSize: AppTypography.iosCallout,
        fontWeight: AppTypography.normal,
      ),
      showChevron: onTap != null,
      onTap: onTap,
      backgroundColor: AppColors.transparent,
      pressedColor: AppColors.iosSecondaryFill(context),
      borderRadius: borderRadius,
    );
  }
}
