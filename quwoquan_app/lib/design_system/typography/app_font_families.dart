import 'package:quwoquan_app/runtime/platform/app_font_platform.dart';
import 'package:quwoquan_app/runtime/platform/platform_target.dart';

/// Bundled font family names registered in [pubspec.yaml].
abstract final class BundledFontFamilies {
  static const String roboto = 'Roboto';
  static const String notoSansSc = 'Noto Sans SC';
  static const String notoSerifSc = 'Noto Serif SC';
  static const String notoSansMono = 'Noto Sans Mono';
  static const String notoColorEmoji = 'Noto Color Emoji';

  static const Set<String> all = {
    roboto,
    notoSansSc,
    notoSerifSc,
    notoSansMono,
    notoColorEmoji,
  };
}

String? resolveAppThemeFontFamily([AppPlatform? platform]) {
  if (resolveAppFontPlatform(platform) == AppFontPlatform.apple) {
    return null;
  }
  return BundledFontFamilies.notoSansSc;
}

List<String> resolveAppThemeFontFallbacks([AppPlatform? platform]) {
  if (resolveAppFontPlatform(platform) == AppFontPlatform.apple) {
    return const [
      '.SF Pro Text',
      'PingFang SC',
      'Helvetica Neue',
      BundledFontFamilies.notoSansSc,
      BundledFontFamilies.notoColorEmoji,
    ];
  }
  return const [
    BundledFontFamilies.notoSansSc,
    BundledFontFamilies.roboto,
    BundledFontFamilies.notoColorEmoji,
  ];
}
