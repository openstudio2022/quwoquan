import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/article_presentation_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_font_stack.dart';
import 'package:quwoquan_app/runtime/platform/platform_target.dart';
import 'package:quwoquan_app/design_system/typography/app_font_families.dart';

void main() {
  group('resolveArticleFontStack', () {
    test('web classic preset maps to bundled serif', () {
      final stack = resolveArticleFontStack(
        ArticleFontPreset.classic,
        AppPlatform.web,
      );
      expect(stack.fontFamily, BundledFontFamilies.notoSerifSc);
      expect(
        stack.fontFamilyFallback,
        everyElement(isIn(BundledFontFamilies.all)),
      );
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

    test('android keeps native article stack', () {
      final stack = resolveArticleFontStack(
        ArticleFontPreset.classic,
        AppPlatform.android,
      );
      expect(stack.fontFamily, 'Times New Roman');
      expect(stack.fontFamilyFallback, contains('Songti SC'));
    });
  });
}
