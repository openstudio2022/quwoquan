import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/platform/platform_target.dart';
import 'package:quwoquan_app/design_system/typography/app_font_families.dart';

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

  group('resolveAppThemeFontFamily', () {
    test('apple platform defers to system font', () {
      expect(resolveAppThemeFontFamily(AppPlatform.ios), isNull);
    });

    test('non-apple platform pins the bundled sans family', () {
      expect(
        resolveAppThemeFontFamily(AppPlatform.android),
        BundledFontFamilies.notoSansSc,
      );
    });
  });
}
