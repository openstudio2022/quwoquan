import 'dart:ui' show Offset;

/// 马赛克类型：像素化 / 高斯模糊。
enum ImageEditorMosaicType { pixelate, blur }

/// 单笔马赛克涂抹（坐标为图内归一化 0..1）。
class ImageEditorMosaicStroke {
  const ImageEditorMosaicStroke({
    required this.type,
    required this.brushRadiusOnShortSide,
    required this.points,
  });

  final ImageEditorMosaicType type;

  /// 笔刷半径，相对图片短边的比例（0..1）。
  final double brushRadiusOnShortSide;

  final List<Offset> points;

  ImageEditorMosaicStroke copyWithPoint(Offset point) {
    return ImageEditorMosaicStroke(
      type: type,
      brushRadiusOnShortSide: brushRadiusOnShortSide,
      points: List<Offset>.of(points)..add(point),
    );
  }

  Map<String, Object?> toWire() {
    return <String, Object?>{
      'type': type.name,
      'radius': brushRadiusOnShortSide,
      'points': points
          .map((p) => <String, double>{'x': p.dx, 'y': p.dy})
          .toList(growable: false),
    };
  }

  static ImageEditorMosaicStroke? fromWire(Map<Object?, Object?> map) {
    final typeName = map['type'] as String?;
    final type = ImageEditorMosaicType.values
        .where((value) => value.name == typeName)
        .firstOrNull;
    if (type == null) return null;
    final rawPoints = map['points'];
    final points = <Offset>[];
    if (rawPoints is List) {
      for (final entry in rawPoints) {
        if (entry is Map) {
          points.add(
            Offset(
              ((entry['x'] as num?)?.toDouble() ?? 0).clamp(0.0, 1.0),
              ((entry['y'] as num?)?.toDouble() ?? 0).clamp(0.0, 1.0),
            ),
          );
        }
      }
    }
    if (points.isEmpty) return null;
    return ImageEditorMosaicStroke(
      type: type,
      brushRadiusOnShortSide: ((map['radius'] as num?)?.toDouble() ?? 0.04)
          .clamp(0.01, 0.2),
      points: List<Offset>.unmodifiable(points),
    );
  }
}

/// 笔刷大小滑杆值（0..1）→ 相对短边半径。
double mosaicBrushRadiusFromSlider(double sliderValue) {
  return 0.015 + sliderValue.clamp(0.0, 1.0) * 0.075;
}
