/// 非 `*_page.dart`：编辑器与宿主（创作页/选择器/相机）之间的 pop 结果协议。
///
/// 单图返回编辑后的路径字符串；多图/「下一步」返回包含 index/path/paths/action
/// 的载荷，宿主一次性回写顺序与编辑结果。
Map<String, dynamic> imageEditorMultiImageDonePopPayload({
  required int currentIndex,
  required String path,
  List<String>? paths,
  String action = 'backToPicker',
}) {
  return <String, dynamic>{
    'index': currentIndex,
    'path': path,
    'action': action,
    // 携带编辑器内的完整顺序（含缩略图条拖拽重排结果），供宿主一次性回写。
    if (paths != null) 'paths': List<String>.from(paths),
  };
}
