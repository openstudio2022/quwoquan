part of 'app_spacing.dart';

/// 宽屏壳层的响应式内容留白。
final class _AppSpacingWebLayout {
  const _AppSpacingWebLayout._();

  static EdgeInsets shellContentPadding(BuildContext context) {
    return EdgeInsets.symmetric(
      horizontal: AppSpacing.responsiveWideValue(
        context,
        compact: AppSpacing.containerXs,
        regular: AppSpacing.containerSm,
        expanded: AppSpacing.containerMd,
        wide: AppSpacing.containerLg,
      ),
    );
  }
}
