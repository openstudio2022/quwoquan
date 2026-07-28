part of 'app_error_states.dart';

Color _toneAccentColor(BuildContext context, UiErrorTone tone) {
  return switch (tone) {
    UiErrorTone.info => AppColors.iosAccent(context),
    UiErrorTone.caution => CupertinoDynamicColor.resolve(
      CupertinoColors.systemOrange,
      context,
    ),
    UiErrorTone.critical => AppColors.iosDestructive(context),
    UiErrorTone.neutral => AppColors.iosSecondaryLabel(context),
  };
}

Widget _wrapWithErrorAppearance(
  BuildContext context,
  UiErrorSemantic semantic,
  Widget child,
) {
  final brightness = semantic.appearanceMode.brightness;
  if (brightness == null) {
    return child;
  }
  return CupertinoTheme(
    data: CupertinoTheme.of(context).copyWith(brightness: brightness),
    child: child,
  );
}
