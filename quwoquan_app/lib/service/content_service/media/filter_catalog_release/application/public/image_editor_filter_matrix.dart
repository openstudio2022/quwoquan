import 'dart:math' as math;

import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/application/public/image_editor_filter_models.dart';

List<double> imageEditorIdentityColorMatrix() => const <double>[
  1,
  0,
  0,
  0,
  0,
  0,
  1,
  0,
  0,
  0,
  0,
  0,
  1,
  0,
  0,
  0,
  0,
  0,
  1,
  0,
];

List<double> multiplyImageEditorColorMatrices(List<double> a, List<double> b) {
  final out = List<double>.filled(20, 0);
  for (var row = 0; row < 4; row++) {
    final rowOffset = row * 5;
    for (var col = 0; col < 5; col++) {
      if (col == 4) {
        out[rowOffset + col] =
            a[rowOffset] * b[4] +
            a[rowOffset + 1] * b[9] +
            a[rowOffset + 2] * b[14] +
            a[rowOffset + 3] * b[19] +
            a[rowOffset + 4];
      } else {
        out[rowOffset + col] =
            a[rowOffset] * b[col] +
            a[rowOffset + 1] * b[col + 5] +
            a[rowOffset + 2] * b[col + 10] +
            a[rowOffset + 3] * b[col + 15];
      }
    }
  }
  return out;
}

List<double> _brightnessMatrix(double value) {
  final offset = value / 100 * 255;
  return <double>[
    1,
    0,
    0,
    0,
    offset,
    0,
    1,
    0,
    0,
    offset,
    0,
    0,
    1,
    0,
    offset,
    0,
    0,
    0,
    1,
    0,
  ];
}

List<double> _contrastMatrix(double value) {
  final factor = (1 + value / 100).clamp(0.0, 3.0);
  final translate = 128 * (1 - factor);
  return <double>[
    factor,
    0,
    0,
    0,
    translate,
    0,
    factor,
    0,
    0,
    translate,
    0,
    0,
    factor,
    0,
    translate,
    0,
    0,
    0,
    1,
    0,
  ];
}

List<double> _saturationMatrix(double value) {
  final s = (1 + value / 100).clamp(0.0, 3.0);
  const lR = 0.2126;
  const lG = 0.7152;
  const lB = 0.0722;
  return <double>[
    lR * (1 - s) + s,
    lG * (1 - s),
    lB * (1 - s),
    0,
    0,
    lR * (1 - s),
    lG * (1 - s) + s,
    lB * (1 - s),
    0,
    0,
    lR * (1 - s),
    lG * (1 - s),
    lB * (1 - s) + s,
    0,
    0,
    0,
    0,
    0,
    1,
    0,
  ];
}

List<double> _temperatureMatrix(double value) {
  final t = (value / 100).clamp(-1.0, 1.0);
  final redScale = (1 + t * 0.18).clamp(0.7, 1.3);
  final blueScale = (1 - t * 0.18).clamp(0.7, 1.3);
  return <double>[
    redScale,
    0,
    0,
    0,
    0,
    0,
    1,
    0,
    0,
    0,
    0,
    0,
    blueScale,
    0,
    0,
    0,
    0,
    0,
    1,
    0,
  ];
}

List<double> _tintMatrix(double value) {
  final t = (value / 100).clamp(-1.0, 1.0);
  final greenScale = (1 - t * 0.12).clamp(0.75, 1.25);
  final redBlueScale = (1 + t * 0.08).clamp(0.75, 1.25);
  return <double>[
    redBlueScale,
    0,
    0,
    0,
    0,
    0,
    greenScale,
    0,
    0,
    0,
    0,
    0,
    redBlueScale,
    0,
    0,
    0,
    0,
    0,
    1,
    0,
  ];
}

List<double> _exposureMatrix(double value) {
  final ev = (value / 100).clamp(-1.5, 1.5);
  final factor = math.pow(2, ev).toDouble();
  return <double>[
    factor,
    0,
    0,
    0,
    0,
    0,
    factor,
    0,
    0,
    0,
    0,
    0,
    factor,
    0,
    0,
    0,
    0,
    0,
    1,
    0,
  ];
}

/// 褪色（fade）满值的黑场抬升比例与去饱和比例。
///
/// 黑场抬升是精确线性重映射 `[0,255] -> [lift*255, 255]`（白点不动），
/// 由矩阵精确表达，非近似；语义显式声明为「黑场抬升 + 轻度去饱和」。
const double kImageEditorFadeMaxLift = 0.22;
const double kImageEditorFadeDesaturate = 0.18;

List<double> _fadeMatrix(double fade) {
  final lift = (fade / 100).clamp(0.0, 1.0) * kImageEditorFadeMaxLift;
  final scale = 1 - lift;
  final offset = 255 * lift;
  return <double>[
    scale, 0, 0, 0, offset, //
    0, scale, 0, 0, offset, //
    0, 0, scale, 0, offset, //
    0, 0, 0, 1, 0, //
  ];
}

/// 细节类参数（走 `ImageEditorDetailSpec` 逐像素管线，禁止折算进矩阵）。
const Set<String> kImageEditorDetailParamKeys = <String>{
  'vibrance',
  'texture',
  'sharpen',
  'structure',
  'highlight',
  'shadow',
  'grain',
  'lightSense',
  'denoise',
  'vignette',
};

/// 纯色彩参数矩阵：只承载业界标准线性调节（曝光/亮度/对比/饱和/色温/色调）
/// 与显式声明的 fade 黑场抬升；细节类参数一律不进矩阵（由调用方经
/// `ImageEditorDetailSpec` 走逐像素管线），禁止系数折算冒充。
List<double> buildImageEditorBaseColorMatrix(Map<String, double> values) {
  final brightness = values['brightness'] ?? 0;
  final exposure = values['exposure'] ?? 0;
  final contrast = values['contrast'] ?? 0;
  final saturation = values['saturation'] ?? 0;
  final temperature = values['temperature'] ?? 0;
  final tint = values['tint'] ?? 0;
  final fade = values['fade'] ?? 0;

  var matrix = imageEditorIdentityColorMatrix();
  matrix = multiplyImageEditorColorMatrices(_exposureMatrix(exposure), matrix);
  matrix = multiplyImageEditorColorMatrices(
    _brightnessMatrix(brightness),
    matrix,
  );
  matrix = multiplyImageEditorColorMatrices(
    _contrastMatrix(contrast),
    matrix,
  );
  matrix = multiplyImageEditorColorMatrices(
    _saturationMatrix(
      saturation - fade.clamp(0.0, 100.0) * kImageEditorFadeDesaturate,
    ),
    matrix,
  );
  if (fade.abs() > 0.001) {
    matrix = multiplyImageEditorColorMatrices(_fadeMatrix(fade), matrix);
  }
  matrix = multiplyImageEditorColorMatrices(
    _temperatureMatrix(temperature),
    matrix,
  );
  matrix = multiplyImageEditorColorMatrices(_tintMatrix(tint), matrix);
  return matrix;
}

/// 滤镜预设按强度缩放后的全参数表（矩阵与细节共用同一缩放）。
Map<String, double> scaledImageEditorFilterValues(
  ImageEditorFilterPreset preset,
  double strength,
) {
  final ratio = (strength / 100).clamp(0.0, 1.0);
  return <String, double>{
    for (final entry in preset.adjustments.entries)
      entry.key: _boostFilterParam(entry.key, entry.value) * ratio,
  };
}

/// 滤镜纯色彩矩阵（细节类参数由 [buildImageEditorFilterDetailValues]
/// 承载，经逐像素管线应用，与整体面板同源）。
List<double> buildImageEditorFilterColorMatrix(
  ImageEditorFilterPreset preset,
  double strength,
) {
  return buildImageEditorBaseColorMatrix(
    scaledImageEditorFilterValues(preset, strength),
  );
}

/// 滤镜细节类参数（缩放后），供页面边界转 `ImageEditorDetailSpec`。
Map<String, double> buildImageEditorFilterDetailValues(
  ImageEditorFilterPreset preset,
  double strength,
) {
  final scaled = scaledImageEditorFilterValues(preset, strength);
  return <String, double>{
    for (final entry in scaled.entries)
      if (kImageEditorDetailParamKeys.contains(entry.key)) ...{
        entry.key: entry.value,
      },
  };
}

/// 滤镜是否含细节类参数（决定预览/烘焙是否需要逐像素管线）。
bool imageEditorFilterHasDetailParams(ImageEditorFilterPreset preset) {
  return preset.adjustments.entries.any(
    (entry) =>
        kImageEditorDetailParamKeys.contains(entry.key) &&
        entry.value.abs() > 0.001,
  );
}

double _boostFilterParam(String key, double value) {
  final abs = value.abs();
  double factor;
  switch (key) {
    case 'contrast':
    case 'saturation':
    case 'vibrance':
    case 'temperature':
    case 'tint':
    case 'hue':
      factor = 1.45;
      break;
    case 'fade':
    case 'grain':
    case 'structure':
    case 'sharpen':
    case 'texture':
      factor = 1.55;
      break;
    case 'highlight':
    case 'shadow':
    case 'lightSense':
    case 'brightness':
    case 'exposure':
    default:
      factor = 1.30;
      break;
  }
  if (abs >= 45) factor += 0.12;
  return (value * factor).clamp(-100.0, 100.0).toDouble();
}
