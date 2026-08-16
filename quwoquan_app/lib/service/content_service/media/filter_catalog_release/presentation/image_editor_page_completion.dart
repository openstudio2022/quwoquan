part of 'image_editor_page.dart';

extension _ImageEditorPageCompletion on _ImageEditorPageState {
  bool get _hasCommittedEdits {
    if (_stepStack.length > 0) return true;
    for (var i = 0; i < _paths.length && i < _initialPaths.length; i++) {
      if (_paths[i] != _initialPaths[i]) return true;
    }
    return _paths.length != _initialPaths.length;
  }

  /// 顶栏返回：有修改时确认放弃；无修改直接退出。放弃后返回 null（宿主不更新）。
  Future<void> _handleBack() async {
    if (!_hasCommittedEdits) {
      _exitWithoutResult();
      return;
    }
    final discard = await showAppActionSheet<bool>(
      context,
      title: MediaText.imageEditorDiscardTitle,
      message: MediaText.imageEditorDiscardMessage,
      sections: [
        AppActionSheetSection<bool>(
          items: [
            AppActionSheetItem<bool>(
              label: MediaText.imageEditorDiscardConfirm,
              value: true,
              isDestructive: true,
            ),
          ],
        ),
      ],
    );
    if (discard != true || !mounted) return;
    _exitWithoutResult();
  }

  void _exitWithoutResult() {
    if (widget.onBack != null) {
      widget.onBack!();
      return;
    }
    context.pop<Object>();
  }

  /// 顶栏完成 / 底部「下一步」：先做交付转码，再提交编辑结果。
  Future<void> _onDone({String action = 'backToPicker'}) async {
    if (_submittingDone) return;
    _submittingDone = true;
    try {
      final deliveryPaths = await _transcodeEditedPathsForDelivery(
        List<String>.of(_paths),
      );
      if (!mounted) return;
      _paths = deliveryPaths;
      _observability.recordPageState(
        pageName: _ImageEditorPageState._kPageName,
        phase: 'submit',
        surface: _ImageEditorPageState._kSurfaceId,
        itemCount: _stepStack.length,
      );
      final Object? result;
      if (_isMultiImage || action == 'continueToCreate') {
        result = ImageEditorMultiImageDoneResult(
          index: _currentIndex,
          path: _currentPath,
          paths: List<String>.from(_paths),
          action: action,
        );
      } else {
        result = _currentPath;
      }
      if (widget.onDone != null) {
        widget.onDone!(result);
      } else {
        context.pop<Object>(result);
      }
    } finally {
      _submittingDone = false;
    }
  }

  /// 编辑管线内部为 PNG 无损中间态；提交时把编辑器烘焙产物转码为交付
  /// JPEG（q92），把上传体积压回商用量级。未经编辑的原始路径原样返回。
  Future<List<String>> _transcodeEditedPathsForDelivery(
    List<String> paths,
  ) async {
    final results = List<String>.of(paths);
    for (var i = 0; i < results.length; i++) {
      final path = results[i];
      if (!ImageEditorExportEngine.isEditorBakedArtifactPath(path)) {
        continue;
      }
      final cached = _deliveryJpegCache[path];
      if (cached != null) {
        results[i] = cached;
        continue;
      }
      final delivered = await _transcodeOne(path);
      if (delivered != path) {
        _deliveryJpegCache[path] = delivered;
      }
      results[i] = delivered;
    }
    return results;
  }

  /// 转码是提交期的静默增强：失败时原 PNG 仍可提交，属于降级但达成，
  /// 因此返回可用路径而不是用 null 表达失败。降级经遥测上报，不静默吞掉。
  Future<String> _transcodeOne(String path) async {
    try {
      final bytes = await _loadImageBytes(path);
      if (bytes.isEmpty) return path;
      final image = await ImageEditorExportEngine.decodeConstrained(bytes);
      final Uint8List jpeg;
      try {
        jpeg = await ImageEditorExportEngine.encodeDeliveryJpeg(image);
      } finally {
        image.dispose();
      }
      return await writeAppTemporaryFileBytes(
        fileName: 'delivery_${DateTime.now().millisecondsSinceEpoch}.jpg',
        bytes: jpeg,
      );
    } catch (error, stackTrace) {
      unawaited(
        ref
            .read(exceptionTelemetryPortProvider)
            .recordHandledException(
              source: 'content.image_editor.delivery_transcode',
              error: error,
              stackTrace: stackTrace,
            ),
      );
      return path;
    }
  }

  void _showHistorySheet() {
    const isDark = true;
    final bg = SettingsSemanticConstants.conversationSheetPanelBackground(
      isDark,
    );
    final fg = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final steps = _stepStack.committed;
    showAppBottomModal<void>(
      context: context,
      builder: (context) {
        return AppBottomModalSurface(
          onDismiss: () => Navigator.of(context).pop(),
          backgroundColor: bg,
          maxHeightRatio: 0.65,
          contentPadding: EdgeInsets.all(
            SettingsSemanticConstants.conversationSheetOuterHorizontalPadding,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Padding(
                padding: EdgeInsets.only(bottom: AppSpacing.containerSm),
                child: Row(
                  children: [
                    Text(
                      MediaText.imageEditorHistory,
                      style: TextStyle(
                        color: fg,
                        fontSize: AppTypography.lg,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const Spacer(),
                    CupertinoButton(
                      padding: EdgeInsets.zero,
                      minimumSize: Size.square(AppSpacing.minInteractiveSize),
                      onPressed: () => Navigator.of(context).pop(),
                      child: Icon(CupertinoIcons.xmark, color: fgSecondary),
                    ),
                  ],
                ),
              ),
              Flexible(
                child: ListView.builder(
                  shrinkWrap: true,
                  itemCount: steps.length,
                  itemBuilder: (context, index) {
                    final step = steps[index];
                    return ListTile(
                      title: Text(step.label, style: TextStyle(color: fg)),
                      trailing: CupertinoButton(
                        padding: EdgeInsets.symmetric(
                          horizontal: AppSpacing.sm,
                        ),
                        minimumSize: Size.square(AppSpacing.minInteractiveSize),
                        onPressed: () {
                          Navigator.of(context).pop();
                          _revertToBeforeStep(index);
                        },
                        child: Text(
                          MediaText.imageEditorHistoryRevert,
                          style: TextStyle(
                            color: fgSecondary,
                            fontSize: AppTypography.sm,
                          ),
                        ),
                      ),
                    );
                  },
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}
