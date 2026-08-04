import 'dart:math' as math;
import 'dart:typed_data';

/// 曲线通道：RGB 主曲线 + 单通道曲线。
enum ImageEditorCurveChannel { rgb, red, green, blue }

/// 单条曲线的控制点（x/y 均为 0..1 归一化，x 单调递增）。
class ImageEditorCurvePoint {
  const ImageEditorCurvePoint(this.x, this.y);

  final double x;
  final double y;

  ImageEditorCurvePoint clamped() {
    return ImageEditorCurvePoint(x.clamp(0.0, 1.0), y.clamp(0.0, 1.0));
  }

  Map<String, double> toWire() => <String, double>{'x': x, 'y': y};

  static ImageEditorCurvePoint fromWire(Map<Object?, Object?> map) {
    return ImageEditorCurvePoint(
      ((map['x'] as num?)?.toDouble() ?? 0).clamp(0.0, 1.0),
      ((map['y'] as num?)?.toDouble() ?? 0).clamp(0.0, 1.0),
    );
  }
}

/// 四通道曲线状态（不可变）。
class ImageEditorCurvesState {
  ImageEditorCurvesState({
    List<ImageEditorCurvePoint>? rgb,
    List<ImageEditorCurvePoint>? red,
    List<ImageEditorCurvePoint>? green,
    List<ImageEditorCurvePoint>? blue,
  }) : rgb = _sanitize(rgb),
       red = _sanitize(red),
       green = _sanitize(green),
       blue = _sanitize(blue);

  static const List<ImageEditorCurvePoint> identityPoints =
      <ImageEditorCurvePoint>[
        ImageEditorCurvePoint(0, 0),
        ImageEditorCurvePoint(1, 1),
      ];

  /// 单条曲线允许的最大控制点数（含两端）。
  static const int maxPointsPerChannel = 8;

  final List<ImageEditorCurvePoint> rgb;
  final List<ImageEditorCurvePoint> red;
  final List<ImageEditorCurvePoint> green;
  final List<ImageEditorCurvePoint> blue;

  static List<ImageEditorCurvePoint> _sanitize(
    List<ImageEditorCurvePoint>? source,
  ) {
    if (source == null || source.length < 2) {
      return List<ImageEditorCurvePoint>.of(identityPoints);
    }
    final sorted = source.map((p) => p.clamped()).toList()
      ..sort((a, b) => a.x.compareTo(b.x));
    if (sorted.length > maxPointsPerChannel) {
      sorted.removeRange(maxPointsPerChannel, sorted.length);
    }
    return List<ImageEditorCurvePoint>.unmodifiable(sorted);
  }

  List<ImageEditorCurvePoint> pointsForChannel(
    ImageEditorCurveChannel channel,
  ) {
    switch (channel) {
      case ImageEditorCurveChannel.rgb:
        return rgb;
      case ImageEditorCurveChannel.red:
        return red;
      case ImageEditorCurveChannel.green:
        return green;
      case ImageEditorCurveChannel.blue:
        return blue;
    }
  }

  ImageEditorCurvesState withChannelPoints(
    ImageEditorCurveChannel channel,
    List<ImageEditorCurvePoint> points,
  ) {
    return ImageEditorCurvesState(
      rgb: channel == ImageEditorCurveChannel.rgb ? points : rgb,
      red: channel == ImageEditorCurveChannel.red ? points : red,
      green: channel == ImageEditorCurveChannel.green ? points : green,
      blue: channel == ImageEditorCurveChannel.blue ? points : blue,
    );
  }

  bool get isIdentity {
    return _isIdentityChannel(rgb) &&
        _isIdentityChannel(red) &&
        _isIdentityChannel(green) &&
        _isIdentityChannel(blue);
  }

  bool channelIsIdentity(ImageEditorCurveChannel channel) {
    return _isIdentityChannel(pointsForChannel(channel));
  }

  static bool _isIdentityChannel(List<ImageEditorCurvePoint> points) {
    if (points.length != 2) return false;
    return (points.first.x).abs() < 0.0005 &&
        (points.first.y).abs() < 0.0005 &&
        (points.last.x - 1).abs() < 0.0005 &&
        (points.last.y - 1).abs() < 0.0005;
  }

  /// 生成 256 级 LUT（monotone cubic Hermite / Fritsch–Carlson，保证无过冲）。
  Uint8List lutForChannel(ImageEditorCurveChannel channel) {
    return buildCurveLut(pointsForChannel(channel));
  }

  Map<String, Object?> toWire() {
    return <String, Object?>{
      'rgb': rgb.map((p) => p.toWire()).toList(growable: false),
      'red': red.map((p) => p.toWire()).toList(growable: false),
      'green': green.map((p) => p.toWire()).toList(growable: false),
      'blue': blue.map((p) => p.toWire()).toList(growable: false),
    };
  }

  static ImageEditorCurvesState fromWire(Map<Object?, Object?>? map) {
    if (map == null) {
      return ImageEditorCurvesState();
    }
    List<ImageEditorCurvePoint>? parse(Object? raw) {
      if (raw is! List) return null;
      final points = <ImageEditorCurvePoint>[];
      for (final entry in raw) {
        if (entry is Map) {
          points.add(
            ImageEditorCurvePoint.fromWire(Map<Object?, Object?>.from(entry)),
          );
        }
      }
      return points.isEmpty ? null : points;
    }

    return ImageEditorCurvesState(
      rgb: parse(map['rgb']),
      red: parse(map['red']),
      green: parse(map['green']),
      blue: parse(map['blue']),
    );
  }
}

/// 控制点 → 256 级查找表。
///
/// 使用 Fritsch–Carlson 单调三次插值：保证输出在控制点之间单调，无振铃/过冲，
/// 是 Photoshop/Lightroom 曲线的标准行为。
Uint8List buildCurveLut(List<ImageEditorCurvePoint> rawPoints) {
  final lut = Uint8List(256);
  final points = rawPoints.map((p) => p.clamped()).toList()
    ..sort((a, b) => a.x.compareTo(b.x));
  if (points.isEmpty) {
    for (var i = 0; i < 256; i++) {
      lut[i] = i;
    }
    return lut;
  }
  if (points.length == 1) {
    final value = (points.first.y * 255).round().clamp(0, 255);
    for (var i = 0; i < 256; i++) {
      lut[i] = value;
    }
    return lut;
  }
  // 去除 x 重复点（保留后者）。
  final xs = <double>[];
  final ys = <double>[];
  for (final point in points) {
    if (xs.isNotEmpty && (point.x - xs.last).abs() < 1e-6) {
      ys[ys.length - 1] = point.y;
      continue;
    }
    xs.add(point.x);
    ys.add(point.y);
  }
  final n = xs.length;
  if (n == 1) {
    final value = (ys.first * 255).round().clamp(0, 255);
    for (var i = 0; i < 256; i++) {
      lut[i] = value;
    }
    return lut;
  }
  final h = List<double>.generate(n - 1, (i) => xs[i + 1] - xs[i]);
  final delta = List<double>.generate(n - 1, (i) => (ys[i + 1] - ys[i]) / h[i]);
  final m = List<double>.filled(n, 0);
  m[0] = delta[0];
  m[n - 1] = delta[n - 2];
  for (var i = 1; i < n - 1; i++) {
    if (delta[i - 1] * delta[i] <= 0) {
      m[i] = 0;
    } else {
      m[i] = (delta[i - 1] + delta[i]) / 2;
    }
  }
  // Fritsch–Carlson 限幅，保证单调。
  for (var i = 0; i < n - 1; i++) {
    if (delta[i].abs() < 1e-9) {
      m[i] = 0;
      m[i + 1] = 0;
      continue;
    }
    final alpha = m[i] / delta[i];
    final beta = m[i + 1] / delta[i];
    final magnitude = math.sqrt(alpha * alpha + beta * beta);
    if (magnitude > 3) {
      final scale = 3 / magnitude;
      m[i] = scale * alpha * delta[i];
      m[i + 1] = scale * beta * delta[i];
    }
  }
  var segment = 0;
  for (var i = 0; i < 256; i++) {
    final x = i / 255;
    double y;
    if (x <= xs.first) {
      y = ys.first;
    } else if (x >= xs.last) {
      y = ys.last;
    } else {
      while (segment < n - 2 && x > xs[segment + 1]) {
        segment++;
      }
      final hSeg = h[segment];
      final t = (x - xs[segment]) / hSeg;
      final t2 = t * t;
      final t3 = t2 * t;
      final h00 = 2 * t3 - 3 * t2 + 1;
      final h10 = t3 - 2 * t2 + t;
      final h01 = -2 * t3 + 3 * t2;
      final h11 = t3 - t2;
      y =
          h00 * ys[segment] +
          h10 * hSeg * m[segment] +
          h01 * ys[segment + 1] +
          h11 * hSeg * m[segment + 1];
    }
    lut[i] = (y * 255).round().clamp(0, 255);
  }
  return lut;
}
