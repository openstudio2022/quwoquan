/// 图片编辑器单步操作数据模型（步骤栈用）
///
/// 每步包含类型、参数与可选缩略图引用；用于 Snapseed 式记录记录与重算。
class ImageEditorStep {
  const ImageEditorStep({
    required this.type,
    required this.params,
    this.thumbnailPath,
  });

  final String type;
  final Map<String, dynamic> params;
  final String? thumbnailPath;

  ImageEditorStep copyWith({
    String? type,
    Map<String, dynamic>? params,
    String? thumbnailPath,
  }) {
    return ImageEditorStep(
      type: type ?? this.type,
      params: params ?? Map<String, dynamic>.from(this.params),
      thumbnailPath: thumbnailPath ?? this.thumbnailPath,
    );
  }
}
