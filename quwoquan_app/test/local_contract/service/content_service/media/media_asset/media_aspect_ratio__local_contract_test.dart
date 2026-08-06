import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/domain/media_aspect_ratio.dart';

void main() {
  group('clampDisplayAspectRatioValue', () {
    test('正常比例原样返回', () {
      expect(clampDisplayAspectRatioValue(1.0), 1.0);
      expect(clampDisplayAspectRatioValue(1.5), 1.5);
    });

    test('超宽横图收到上界', () {
      expect(clampDisplayAspectRatioValue(5.0), kDisplayMaxAspectRatio);
    });

    test('超长竖图收到下界', () {
      expect(clampDisplayAspectRatioValue(0.2), kDisplayMinAspectRatio);
    });

    test('非法比例回退到 fallback 并被 clamp', () {
      expect(clampDisplayAspectRatioValue(null), kDisplayFallbackAspectRatio);
      expect(clampDisplayAspectRatioValue(0), kDisplayFallbackAspectRatio);
      expect(
        clampDisplayAspectRatioValue(double.nan),
        kDisplayFallbackAspectRatio,
      );
      expect(
        clampDisplayAspectRatioValue(double.infinity),
        kDisplayFallbackAspectRatio,
      );
      expect(clampDisplayAspectRatioValue(-2.0), kDisplayFallbackAspectRatio);
    });

    test('支持自定义边界（文章封面更宽下界）', () {
      expect(
        clampDisplayAspectRatioValue(0.5, min: 9 / 16, max: 16 / 9),
        9 / 16,
      );
    });
  });

  group('clampDisplayAspectRatio (width/height)', () {
    test('由宽高计算并 clamp', () {
      expect(clampDisplayAspectRatio(width: 100, height: 100), 1.0);
      expect(
        clampDisplayAspectRatio(width: 1000, height: 100),
        kDisplayMaxAspectRatio,
      );
      expect(
        clampDisplayAspectRatio(width: 100, height: 1000),
        kDisplayMinAspectRatio,
      );
    });

    test('宽高缺失或非法回退 fallback', () {
      expect(clampDisplayAspectRatio(), kDisplayFallbackAspectRatio);
      expect(
        clampDisplayAspectRatio(width: 0, height: 100),
        kDisplayFallbackAspectRatio,
      );
      expect(
        clampDisplayAspectRatio(
          width: -10,
          height: 100,
          fallback: kDisplayVideoFallbackAspectRatio,
        ),
        kDisplayVideoFallbackAspectRatio,
      );
    });
  });
}
