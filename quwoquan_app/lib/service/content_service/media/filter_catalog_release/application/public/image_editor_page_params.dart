/// 非 `*_page.dart`：编辑器与宿主（创作页/选择器/相机）之间的 pop 结果协议。
///
/// 单图返回编辑后的路径字符串；多图/「下一步」返回本 typed 结果，
/// 宿主一次性回写顺序与编辑结果。
final class ImageEditorMultiImageDoneResult {
  const ImageEditorMultiImageDoneResult({
    required this.index,
    required this.path,
    this.paths,
    this.action = 'backToPicker',
  });

  /// 当前编辑图片在编辑器序列内的下标。
  final int index;

  /// 当前编辑图片的产物路径。
  final String path;

  /// 编辑器内的完整顺序（含缩略图条拖拽重排结果），供宿主一次性回写。
  final List<String>? paths;

  /// `backToPicker` 回到宿主；`continueToCreate` 直接进入创作页。
  final String action;

  bool get continueToCreate => action == 'continueToCreate';
}
