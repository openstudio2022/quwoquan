import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/platform/app_font_families.dart';
import 'package:quwoquan_app/core/platform/platform_target.dart';
import 'package:quwoquan_app/content/content/post/domain/article_presentation_models.dart';

void main() {
  group('resolveAppThemeFontFallbacks', () {
    test('web uses bundled families only', () {
      final fallbacks = resolveAppThemeFontFallbacks(AppPlatform.web);
      expect(fallbacks, contains(BundledFontFamilies.notoSansSc));
      expect(fallbacks, contains(BundledFontFamilies.roboto));
      expect(fallbacks, contains(BundledFontFamilies.notoColorEmoji));
      expect(fallbacks, isNot(contains('PingFang SC')));
      expect(fallbacks, isNot(contains('.SF Pro Text')));
    });

    test('ios theme fallback includes emoji-capable family', () {
      final fallbacks = resolveAppThemeFontFallbacks(AppPlatform.ios);
      expect(fallbacks, contains('.SF Pro Text'));
      expect(fallbacks, contains(BundledFontFamilies.notoColorEmoji));
    });
  });

  group('resolveArticleFontStack', () {
    test('web classic preset maps to bundled serif', () {
      final stack = resolveArticleFontStack(
        ArticleFontPreset.classic,
        AppPlatform.web,
      );
      expect(stack.fontFamily, BundledFontFamilies.notoSerifSc);
      expect(stack.fontFamilyFallback, everyElement(isIn(BundledFontFamilies.all)));
      expect(stack.fontFamilyFallback, isNot(contains('Songti SC')));
    });

    test('web mono preset maps to bundled mono', () {
      final stack = resolveArticleFontStack(
        ArticleFontPreset.mono,
        AppPlatform.web,
      );
      expect(stack.fontFamily, BundledFontFamilies.notoSansMono);
      expect(stack.fontFamilyFallback, isNot(contains('Menlo')));
    });

    test('ios keeps native article stack', () {
      final stack = resolveArticleFontStack(
        ArticleFontPreset.clean,
        AppPlatform.ios,
      );
      expect(stack.fontFamily, isNull);
      expect(stack.fontFamilyFallback, contains('PingFang SC'));
    });
  });
}
