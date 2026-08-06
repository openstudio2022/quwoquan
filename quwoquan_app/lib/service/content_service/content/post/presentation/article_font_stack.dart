import 'package:quwoquan_app/service/content_service/content/post/domain/article_presentation_models.dart';
import 'package:quwoquan_app/runtime/platform/app_font_platform.dart';
import 'package:quwoquan_app/runtime/platform/platform_target.dart';
import 'package:quwoquan_app/design_system/typography/app_font_families.dart';

/// Resolved article font stack for the current platform.
class ArticleFontStack {
  const ArticleFontStack({
    required this.fontFamily,
    required this.fontFamilyFallback,
  });

  final String? fontFamily;
  final List<String> fontFamilyFallback;
}

/// 把阅读预设映射成实际字体栈。
///
/// 原生端可以直接引用系统字体族；Web 没有系统中文字体保证，只能回落到随包
/// 分发的字体族。
ArticleFontStack resolveArticleFontStack(
  ArticleFontPreset preset, [
  AppPlatform? platform,
]) {
  if (resolveAppFontPlatform(platform) == AppFontPlatform.web) {
    return _bundledArticleFontStack(preset);
  }
  return _nativeArticleFontStack(preset);
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
  return ArticleFontStack(fontFamily: fontFamily, fontFamilyFallback: fallback);
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
