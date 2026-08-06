part of 'app_spacing.dart';

double _appSpacingPrimaryTopBarSafeTopInset(
  double safeTop,
  BuildContext context,
) {
  if (safeTop <= AppSpacing.zero) {
    return AppSpacing.zero;
  }
  final labelTopPadding =
      (AppSpacing.primaryTopBarHeight(context) -
          AppSpacing._primaryTabFontSize) /
      2;
  return (safeTop - labelTopPadding + AppSpacing.xs).clamp(
    AppSpacing.zero,
    safeTop,
  );
}

double _appSpacingBottomNavContentSideInset(
  BuildContext context,
  double bottomSafeInset,
) {
  final baseInset = AppSpacing.bottomNavSideInset(context);
  if (bottomSafeInset <= AppSpacing.zero) {
    return baseInset;
  }
  return baseInset +
      AppSpacing.responsiveValue(
        context,
        compact: AppSpacing.containerXs,
        regular: AppSpacing.containerSm,
        expanded: AppSpacing.containerMd,
      );
}

double _appSpacingBottomNavBarItemIconSize(BuildContext context) =>
    AppSpacing.responsiveWideValue(
      context,
      compact: AppSpacing.iconMedium,
      regular: AppSpacing.twentyEight,
      expanded: AppSpacing.iconLarge,
      wide: AppSpacing.forty,
    );

double _appSpacingWebInstallBannerHeight(BuildContext context) =>
    AppSpacing.responsiveWideValue(
      context,
      compact: AppSpacing.webInstallBannerCompactHeight,
      regular: AppSpacing.webInstallBannerCompactHeight,
      expanded: AppSpacing.webInstallBannerCompactHeight,
      wide: AppSpacing.webInstallBannerWideHeight,
    );
