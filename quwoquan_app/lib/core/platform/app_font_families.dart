import 'package:flutter/foundation.dart';

import 'package:quwoquan_app/core/platform/platform_target.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';

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

/// Resolved theme/article font stack for the current platform.
class ArticleFontStack {
  const ArticleFontStack({
    required this.fontFamily,
    required this.fontFamilyFallback,
  });

  final String? fontFamily;
  final List<String> fontFamilyFallback;
}

bool _usesAppleSystemFonts() {
  return !kIsWeb &&
      (defaultTargetPlatform == TargetPlatform.iOS ||
          defaultTargetPlatform == TargetPlatform.macOS);
}

String? resolveAppThemeFontFamily([AppPlatform? platform]) {
  if (_usesAppleSystemFonts()) {
    return null;
  }
  return BundledFontFamilies.notoSansSc;
}

List<String> resolveAppThemeFontFallbacks([AppPlatform? platform]) {
  if (_usesAppleSystemFonts()) {
    return const [
      '.SF Pro Text',
      'PingFang SC',
      'Helvetica Neue',
      BundledFontFamilies.notoSansSc,
    ];
  }
  final resolved = platform ?? currentAppPlatform;
  if (resolved == AppPlatform.web) {
    return const [
      BundledFontFamilies.notoSansSc,
      BundledFontFamilies.roboto,
      BundledFontFamilies.notoColorEmoji,
    ];
  }
  return const [
    BundledFontFamilies.notoSansSc,
    BundledFontFamilies.roboto,
    BundledFontFamilies.notoColorEmoji,
  ];
}

ArticleFontStack resolveArticleFontStack(
  ArticleFontPreset preset, [
  AppPlatform? platform,
]) {
  final resolved = platform ?? currentAppPlatform;
  if (resolved != AppPlatform.web) {
    return _nativeArticleFontStack(preset);
  }
  return _bundledArticleFontStack(preset);
}

ArticleFontStack _nativeArticleFontStack(ArticleFontPreset preset) {
  final fallback = switch (preset) {
    ArticleFontPreset.classic => const <String>[
      'Times New Roman',
      'STSong',
      'Songti SC',
    ],
    ArticleFontPreset.handwritten => const <String>['Kaiti SC', 'STKaiti'],
    ArticleFontPreset.rounded => const <String>[
      'PingFang SC',
      'SF Pro Rounded',
    ],
    ArticleFontPreset.mono => const <String>['Menlo', 'Monaco'],
    ArticleFontPreset.clean => const <String>['PingFang SC'],
  };
  final fontFamily = switch (preset) {
    ArticleFontPreset.classic => 'Times New Roman',
    ArticleFontPreset.handwritten => 'Kaiti SC',
    ArticleFontPreset.rounded => 'SF Pro Rounded',
    ArticleFontPreset.mono => 'Menlo',
    ArticleFontPreset.clean => null,
  };
  return ArticleFontStack(
    fontFamily: fontFamily,
    fontFamilyFallback: fallback,
  );
}

ArticleFontStack _bundledArticleFontStack(ArticleFontPreset preset) {
  return switch (preset) {
    ArticleFontPreset.classic => const ArticleFontStack(
      fontFamily: BundledFontFamilies.notoSerifSc,
      fontFamilyFallback: [
        BundledFontFamilies.notoSerifSc,
        BundledFontFamilies.notoSansSc,
      ],
    ),
    ArticleFontPreset.handwritten => const ArticleFontStack(
      fontFamily: BundledFontFamilies.notoSerifSc,
      fontFamilyFallback: [
        BundledFontFamilies.notoSerifSc,
        BundledFontFamilies.notoSansSc,
      ],
    ),
    ArticleFontPreset.rounded => const ArticleFontStack(
      fontFamily: BundledFontFamilies.notoSansSc,
      fontFamilyFallback: [
        BundledFontFamilies.notoSansSc,
        BundledFontFamilies.roboto,
      ],
    ),
    ArticleFontPreset.mono => const ArticleFontStack(
      fontFamily: BundledFontFamilies.notoSansMono,
      fontFamilyFallback: [
        BundledFontFamilies.notoSansMono,
        BundledFontFamilies.notoSansSc,
      ],
    ),
    ArticleFontPreset.clean => const ArticleFontStack(
      fontFamily: BundledFontFamilies.notoSansSc,
      fontFamilyFallback: [
        BundledFontFamilies.notoSansSc,
        BundledFontFamilies.roboto,
      ],
    ),
  };
}
