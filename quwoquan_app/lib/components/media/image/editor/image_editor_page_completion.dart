part of 'image_editor_page.dart';

extension _ImageEditorPageCompletion on _ImageEditorPageState {
  void _onDone({String action = 'backToPicker'}) async {
    if (_hasProBaseAdjustments ||
        _hasProHslAdjustments ||
        _hasBwLevelsAdjustments ||
        _hasLocalAdjustments) {
      final adjustedPath = await _applyProAdjustmentsToCurrentImage();
      if (adjustedPath == null) {
        await _showEditorActionFailure(title: '编辑未保存');
        return;
      }
      _paths[_currentIndex] = adjustedPath;
      _clearFilterPreviewCache();
      // 避免重复叠加导出
      _proBaseValues.updateAll((key, value) => 0);
      _proBaseSnapshotValues.updateAll((key, value) => 0);
      _proHslValues = createDefaultHslValues();
      _proHslSnapshotValues = createDefaultHslValues();
      _hslSessionBaselineValues = createDefaultHslValues();
      _resetHslSessionHistory();
      _bwWhiteLevel = 0;
      _bwBlackLevel = 0;
      _bwSnapshotWhiteLevel = 0;
      _bwSnapshotBlackLevel = 0;
      _bwSessionBaselineWhiteLevel = 0;
      _bwSessionBaselineBlackLevel = 0;
      _bwSessionStack.clear();
      _bwSessionCursor = -1;
      _localAnchors.clear();
      _localSnapshotAnchors = <LocalAnchor>[];
      _selectedLocalAnchorId = null;
      _localSessionStack.clear();
      _localSessionCursor = -1;
    }
    _selectedFilterPresetId = null;
    _filterTemplateIndex = -1;
    _filterIntensity = 100;
    final Object? result;
    if (_isMultiImage || action == 'continueToCreate') {
      result = imageEditorMultiImageDonePopPayload(
        currentIndex: _currentIndex,
        path: _currentPath,
        paths: List<String>.from(_paths),
        action: action,
      );
    } else {
      result = _currentPath;
    }
    if (!mounted) return;
    if (widget.onDone != null) {
      widget.onDone!(result);
    } else {
      context.pop<Object>(result);
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
                      UITextConstants.imageEditorHistory,
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
                  itemCount: _steps.length,
                  itemBuilder: (context, index) {
                    final step = _steps[index];
                    return ListTile(
                      title: Text(
                        imageEditorStepTypeLabel(step.type, step.params),
                        style: TextStyle(color: fg),
                      ),
                      trailing: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          CupertinoButton(
                            padding: EdgeInsets.zero,
                            minimumSize: Size.square(
                              AppSpacing.minInteractiveSize,
                            ),
                            onPressed: () {
                              Navigator.of(context).pop();
                              _redoStepAt(index);
                            },
                            child: Icon(
                              CupertinoIcons.refresh,
                              color: fgSecondary,
                              size: AppSpacing.iconSmall,
                            ),
                          ),
                          CupertinoButton(
                            padding: EdgeInsets.zero,
                            minimumSize: Size.square(
                              AppSpacing.minInteractiveSize,
                            ),
                            onPressed: () {
                              _removeStepAt(index);
                              Navigator.of(context).pop();
                            },
                            child: Icon(
                              CupertinoIcons.trash,
                              color: fgSecondary,
                              size: AppSpacing.iconSmall,
                            ),
                          ),
                        ],
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
