import 'package:quwoquan_app/content/media/filter_catalog_release/presentation/image_editor_step_payload.dart';

/// 图片编辑器单步操作数据模型（步骤栈用）
///
/// 每步持有强类型工具参数 [payload]、烘焙前后的文件快照路径与所属图片槽位，
/// 支撑全局撤销/重做（文件快照语义，见 ImageEditorStepStack）。
class ImageEditorStep {
  const ImageEditorStep({
    required this.payload,
    required this.imageIndex,
    required this.beforePath,
    required this.afterPath,
  });

  final ImageEditorStepPayload payload;

  /// 多图会话中该步骤作用的图片槽位。
  final int imageIndex;

  /// 烘焙前的图片文件路径（undo 恢复目标）。
  final String beforePath;

  /// 烘焙后的图片文件路径（redo 恢复目标）。
  final String afterPath;

  String get toolType => payload.toolType;

  String? get subType => payload.subType;

  String get label => payload.label;

  ImageEditorStep copyWith({
    ImageEditorStepPayload? payload,
    int? imageIndex,
    String? beforePath,
    String? afterPath,
  }) {
    return ImageEditorStep(
      payload: payload ?? this.payload,
      imageIndex: imageIndex ?? this.imageIndex,
      beforePath: beforePath ?? this.beforePath,
      afterPath: afterPath ?? this.afterPath,
    );
  }
}
