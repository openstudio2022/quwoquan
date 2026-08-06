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

List<double> buildImageEditorBaseColorMatrix(Map<String, double> values) {
  final lightSense = values['lightSense'] ?? 0;
  final brightness = values['brightness'] ?? 0;
  final exposure = values['exposure'] ?? 0;
  final contrast = values['contrast'] ?? 0;
  final saturation = values['saturation'] ?? 0;
  final vibrance = values['vibrance'] ?? 0;
  final texture = values['texture'] ?? 0;
  final sharpen = values['sharpen'] ?? 0;
  final structure = values['structure'] ?? 0;
  final highlights = values['highlight'] ?? 0;
  final shadows = values['shadow'] ?? 0;
  final temperature = values['temperature'] ?? 0;
  final tint = values['tint'] ?? 0;
  final grain = values['grain'] ?? 0;
  final fade = values['fade'] ?? 0;
  final lightSenseBrightness = lightSense * 0.09;
  final lightSenseContrast = lightSense * 0.18;
  final vibranceSaturation = vibrance * 0.65;
  final textureContrast = texture * 0.14;
  final sharpenContrast = sharpen * 0.12;
  final structureContrast = structure * 0.24;
  final highlightBrightness = highlights * 0.20;
  final shadowBrightness = shadows * 0.25;
  final grainContrast = grain * 0.10;
  final fadeLift = fade * 0.22;

  var matrix = imageEditorIdentityColorMatrix();
  matrix = multiplyImageEditorColorMatrices(_exposureMatrix(exposure), matrix);
  matrix = multiplyImageEditorColorMatrices(
    _brightnessMatrix(
      brightness +
          lightSenseBrightness +
          highlightBrightness +
          shadowBrightness +
          fadeLift,
    ),
    matrix,
  );
  matrix = multiplyImageEditorColorMatrices(
    _contrastMatrix(
      contrast +
          lightSenseContrast +
          textureContrast +
          sharpenContrast +
          structureContrast +
          grainContrast +
          highlights * 0.10 -
          shadows * 0.10 -
          fade * 0.30,
    ),
    matrix,
  );
  matrix = multiplyImageEditorColorMatrices(
    _saturationMatrix(saturation + vibranceSaturation - fade * 0.18),
    matrix,
  );
  matrix = multiplyImageEditorColorMatrices(
    _temperatureMatrix(temperature),
    matrix,
  );
  matrix = multiplyImageEditorColorMatrices(_tintMatrix(tint), matrix);
  return matrix;
}

List<double> buildImageEditorFilterColorMatrix(
  ImageEditorFilterPreset preset,
  double strength,
) {
  final ratio = (strength / 100).clamp(0.0, 1.0);
  final scaledValues = <String, double>{
    for (final entry in preset.adjustments.entries)
      entry.key: _boostFilterParam(entry.key, entry.value) * ratio,
  };
  var matrix = buildImageEditorBaseColorMatrix(scaledValues);
  return matrix;
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
