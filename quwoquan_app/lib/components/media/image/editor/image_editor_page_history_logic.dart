part of 'image_editor_page.dart';

/// 全局撤销/重做（文件快照语义）与历史回退。
extension _ImageEditorPageHistoryLogic on _ImageEditorPageState {
  void _pushStep(ImageEditorStep step) {
    _setEditorState(() => _stepStack.push(step));
    unawaited(
      _analytics.trackEvent(
        AnalyticsEvent(
          eventType: 'product',
          eventName: 'image_editor_tool_used',
          properties: <String, dynamic>{
            'pageName': _ImageEditorPageState._kPageName,
            'tool': step.toolType,
            if (step.subType != null) 'subType': step.subType,
            'source': widget.source,
          },
        ),
      ),
    );
  }

  /// 恢复指定步骤的文件快照到对应图片槽位。
  void _restoreSnapshotPath(ImageEditorStep step, {required bool toBefore}) {
    final targetPath = toBefore ? step.beforePath : step.afterPath;
    if (step.imageIndex < 0 || step.imageIndex >= _paths.length) {
      return;
    }
    _paths[step.imageIndex] = targetPath;
    if (step.imageIndex == _currentIndex) {
      _loadImageAspectRatio(targetPath);
      _clearFilterPreviewCache();
    }
  }

  void _undoLastStep() {
    final step = _stepStack.undo();
    if (step == null) return;
    _setEditorState(() => _restoreSnapshotPath(step, toBefore: true));
  }

  void _redoLastUndoneStep() {
    final step = _stepStack.redo();
    if (step == null) return;
    _setEditorState(() => _restoreSnapshotPath(step, toBefore: false));
  }

  /// 历史面板「回退到此步之前」：按时间倒序撤销到第 [index] 步之前。
  void _revertToBeforeStep(int index) {
    final popped = _stepStack.undoToBefore(index);
    if (popped.isEmpty) return;
    _setEditorState(() {
      for (final step in popped) {
        _restoreSnapshotPath(step, toBefore: true);
      }
    });
  }
}
