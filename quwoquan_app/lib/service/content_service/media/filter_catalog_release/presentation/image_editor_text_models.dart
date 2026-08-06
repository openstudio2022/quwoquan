import 'dart:ui' show Color, Offset;

import 'package:quwoquan_app/design_system/colors/app_colors.dart';

/// 文字样式：纯色 / 描边 / 背景条。
enum ImageEditorTextStyleKind { plain, outline, backgroundBar }

/// 可选文字颜色（语义色板，白黑 + 品牌与功能色）。
List<Color> imageEditorTextPalette() {
  return <Color>[
    AppColors.white,
    AppColors.black,
    AppColors.primaryColor,
    AppColors.error,
    AppColors.warning,
    AppColors.success,
    AppColors.info,
    AppColors.secondaryColor,
  ];
}

/// 图上文字项（中心点为图内归一化坐标；字号相对图片短边）。
class ImageEditorTextItem {
  const ImageEditorTextItem({
    required this.id,
    required this.text,
    required this.style,
    required this.colorIndex,
    required this.center,
    required this.fontSizeOnShortSide,
    required this.rotation,
  });

  final int id;
  final String text;
  final ImageEditorTextStyleKind style;
  final int colorIndex;
  final Offset center;

  /// 字号相对图片短边的比例。
  final double fontSizeOnShortSide;

  /// 旋转弧度。
  final double rotation;

  static const double defaultFontSizeOnShortSide = 0.06;
  static const double minFontSizeOnShortSide = 0.02;
  static const double maxFontSizeOnShortSide = 0.25;

  Color get color {
    final palette = imageEditorTextPalette();
    final index = colorIndex.clamp(0, palette.length - 1);
    return palette[index];
  }

  /// 描边色：亮色文字描黑边，暗色文字描白边。
  Color get outlineColor {
    return color.computeLuminance() > 0.5 ? AppColors.black : AppColors.white;
  }

  /// 背景条色：与文字色对比。
  Color get backgroundBarColor {
    return color.computeLuminance() > 0.5
        ? AppColors.black.withValues(alpha: 0.65)
        : AppColors.white.withValues(alpha: 0.85);
  }

  ImageEditorTextItem copyWith({
    String? text,
    ImageEditorTextStyleKind? style,
    int? colorIndex,
    Offset? center,
    double? fontSizeOnShortSide,
    double? rotation,
  }) {
    return ImageEditorTextItem(
      id: id,
      text: text ?? this.text,
      style: style ?? this.style,
      colorIndex: colorIndex ?? this.colorIndex,
      center: center ?? this.center,
      fontSizeOnShortSide: (fontSizeOnShortSide ?? this.fontSizeOnShortSide)
          .clamp(minFontSizeOnShortSide, maxFontSizeOnShortSide),
      rotation: rotation ?? this.rotation,
    );
  }

  Map<String, Object?> toWire() {
    return <String, Object?>{
      'id': id,
      'text': text,
      'style': style.name,
      'colorIndex': colorIndex,
      'x': center.dx,
      'y': center.dy,
      'fontSize': fontSizeOnShortSide,
      'rotation': rotation,
    };
  }

  static ImageEditorTextItem? fromWire(Map<Object?, Object?> map) {
    final text = (map['text'] as String?)?.trim();
    if (text == null || text.isEmpty) return null;
    final styleName = map['style'] as String?;
    final style = ImageEditorTextStyleKind.values
        .where((value) => value.name == styleName)
        .firstOrNull;
    return ImageEditorTextItem(
      id: (map['id'] as num?)?.toInt() ?? 0,
      text: text,
      style: style ?? ImageEditorTextStyleKind.plain,
      colorIndex: (map['colorIndex'] as num?)?.toInt() ?? 0,
      center: Offset(
        ((map['x'] as num?)?.toDouble() ?? 0.5).clamp(0.0, 1.0),
        ((map['y'] as num?)?.toDouble() ?? 0.5).clamp(0.0, 1.0),
      ),
      fontSizeOnShortSide:
          ((map['fontSize'] as num?)?.toDouble() ?? defaultFontSizeOnShortSide)
              .clamp(minFontSizeOnShortSide, maxFontSizeOnShortSide),
      rotation: (map['rotation'] as num?)?.toDouble() ?? 0,
    );
  }
}
