import 'package:quwoquan_app/components/media/image/editor/models/image_editor_step.dart';

/// 已提交步骤 + 撤销/重做栈（文件快照语义）。
///
/// 每个步骤记录烘焙前后的图片文件路径快照：
/// - undo：把对应图槽位恢复为 [ImageEditorStep.beforePath] 并把步骤移入重做栈；
/// - redo：恢复 [ImageEditorStep.afterPath] 并移回已提交栈；
/// - 新步骤提交时清空重做栈（标准编辑器语义）。
class ImageEditorStepStack {
  ImageEditorStepStack({this.maxSteps = 30});

  final int maxSteps;
  final List<ImageEditorStep> _committed = <ImageEditorStep>[];
  final List<ImageEditorStep> _redo = <ImageEditorStep>[];

  List<ImageEditorStep> get committed =>
      List<ImageEditorStep>.unmodifiable(_committed);

  bool get canUndo => _committed.isNotEmpty;
  bool get canRedo => _redo.isNotEmpty;
  int get length => _committed.length;

  void push(ImageEditorStep step) {
    _redo.clear();
    _committed.add(step);
    if (_committed.length > maxSteps) {
      _committed.removeAt(0);
    }
  }

  /// 撤销最后一步，返回被撤销的步骤（调用方负责恢复 beforePath 与状态）。
  ImageEditorStep? undo() {
    if (_committed.isEmpty) return null;
    final step = _committed.removeLast();
    _redo.add(step);
    return step;
  }

  /// 重做最近撤销的一步。
  ImageEditorStep? redo() {
    if (_redo.isEmpty) return null;
    final step = _redo.removeLast();
    _committed.add(step);
    return step;
  }

  /// 撤销到第 [index] 步之前（含第 index 步在内之后的步骤全部弹出，
  /// 按倒序进入重做栈）。返回被弹出的步骤（时间倒序，最后一步在前）。
  List<ImageEditorStep> undoToBefore(int index) {
    if (index < 0 || index >= _committed.length) {
      return const <ImageEditorStep>[];
    }
    final popped = <ImageEditorStep>[];
    while (_committed.length > index) {
      final step = _committed.removeLast();
      _redo.add(step);
      popped.add(step);
    }
    return popped;
  }

  void clear() {
    _committed.clear();
    _redo.clear();
  }
}
