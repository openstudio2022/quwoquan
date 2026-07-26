part of 'image_editor_page.dart';

extension _ImageEditorPageProAdjustments on _ImageEditorPageState {
  void _closePanel() {
    _setEditorState(() {
      _selectedToolIndex = null;
      _hslPickerActive = false;
      _hslPickerPoint = null;
      _localAddMode = false;
      _localShowAnchorMenu = false;
      _localMagnifierPoint = null;
      _draggingAnchorId = null;
      _draggingAnchorCenter = null;
      _draggingAnchorBaseRadius = null;
      _localRangeVisible = false;
      _isComparingSessionBaseline = false;
      _showProToolbox = false;
    });
  }

  void _prepareProPanelSnapshot() {
    _proCategorySnapshot = _selectedProCategory;
    _proBaseToolSnapshot = _selectedProBaseToolIndex;
    _proBaseSnapshotValues = Map<String, double>.from(_proBaseValues);
    _bwSnapshotWhiteLevel = _bwWhiteLevel;
    _bwSnapshotBlackLevel = _bwBlackLevel;
    _proHslSnapshotValues = cloneHslValues(_proHslValues);
    _localSnapshotAnchors = cloneLocalAnchors(_localAnchors);
    _curvesSnapshot = _curvesState;
    _wbSnapshotTemperature = _wbTemperature;
    _wbSnapshotTint = _wbTint;
    _resetHslSessionHistory();
    _resetBwSessionHistory();
    _resetLocalSessionHistory();
  }

  void _cancelProPanel() {
    _setEditorState(() {
      _selectedProCategory = _proCategorySnapshot;
      _selectedProBaseToolIndex = _proBaseToolSnapshot;
      _proBaseValues
        ..clear()
        ..addAll(_proBaseSnapshotValues);
      _bwWhiteLevel = _bwSnapshotWhiteLevel;
      _bwBlackLevel = _bwSnapshotBlackLevel;
      _proHslValues = cloneHslValues(_proHslSnapshotValues);
      _curvesState = _curvesSnapshot;
      _wbTemperature = _wbSnapshotTemperature;
      _wbTint = _wbSnapshotTint;
      _localAnchors
        ..clear()
        ..addAll(cloneLocalAnchors(_localSnapshotAnchors));
      if (_selectedLocalAnchorId != null &&
          _localAnchors.every(
            (anchor) => anchor.id != _selectedLocalAnchorId,
          )) {
        _selectedLocalAnchorId = _localAnchors.isNotEmpty
            ? _localAnchors.last.id
            : null;
      }
      _hslPickerActive = false;
      _hslPickerPoint = null;
      _localAddMode = false;
      _localShowAnchorMenu = false;
      _localMagnifierPoint = null;
      _draggingAnchorId = null;
      _draggingAnchorCenter = null;
      _draggingAnchorBaseRadius = null;
      _localRangeVisible = false;
      _isComparingSessionBaseline = false;
      _resetHslSessionHistory();
      _resetBwSessionHistory();
      _resetLocalSessionHistory();
      _selectedToolIndex = null;
      _showProToolbox = false;
    });
    _disposeCurveSessionResources();
  }

  void _onProBaseValueChanged(String toolType, double value) {
    if (_selectedToolIndex == kImageEditorToolPro &&
        _selectedProCategory == kImageEditorProCategoryLocal &&
        _selectedLocalAnchor == null) {
      _showLocalHint(UITextConstants.imageEditorProAnchorSelectHint);
      return;
    }
    final clamped = value.clamp(-100.0, 100.0);
    _setEditorState(() {
      if (_selectedToolIndex == kImageEditorToolPro &&
          _selectedProCategory == kImageEditorProCategoryLocal &&
          _selectedLocalAnchor != null) {
        final selected = _selectedLocalAnchor!;
        final index = _localAnchors.indexWhere(
          (anchor) => anchor.id == selected.id,
        );
        if (index >= 0) {
          final values = Map<String, double>.from(selected.values);
          values[toolType] = clamped;
          _localAnchors[index] = selected.copyWith(
            values: values,
            selectedParam: toolType,
          );
          _recordLocalSessionStep();
          return;
        }
      }
      _proBaseValues[toolType] = clamped;
    });
  }

  void _showLocalHint(String message) {
    if (!mounted) return;
    AppToast.show(
      context,
      message,
      duration: const Duration(milliseconds: 1400),
    );
  }

  void _toggleLocalAddMode() {
    final toEnable = !_localAddMode;
    if (toEnable &&
        _localAnchors.length >= _ImageEditorPageState._kLocalAnchorMaxCount) {
      _showLocalHint(UITextConstants.imageEditorProAnchorLimitReached);
      return;
    }
    _setEditorState(() {
      _localAddMode = toEnable;
      _localShowAnchorMenu = false;
    });
    if (toEnable) {
      _showLocalHint(UITextConstants.imageEditorProAnchorScaleHint);
    }
  }

  LocalAnchor? get _selectedLocalAnchor {
    if (_selectedLocalAnchorId == null) return null;
    for (final anchor in _localAnchors) {
      if (anchor.id == _selectedLocalAnchorId) return anchor;
    }
    return null;
  }

  Map<String, double> get _selectedLocalValues {
    return _selectedLocalAnchor?.values ?? createDefaultLocalAnchorValues();
  }

  void _addLocalAnchorAt(Offset localPosition, Size imageSize) {
    if (_localAnchors.length >= _ImageEditorPageState._kLocalAnchorMaxCount) {
      _showLocalHint(UITextConstants.imageEditorProAnchorLimitReached);
      _setEditorState(() => _localAddMode = false);
      return;
    }
    final imageRect = _resolveImageRect(imageSize);
    if (!imageRect.contains(localPosition)) return;
    final nx = ((localPosition.dx - imageRect.left) / imageRect.width).clamp(
      0.0,
      1.0,
    );
    final ny = ((localPosition.dy - imageRect.top) / imageRect.height).clamp(
      0.0,
      1.0,
    );
    final safeIndex = _selectedProBaseToolIndex.clamp(
      0,
      kImageEditorProBaseEntries.length - 1,
    );
    final selectedParam = kImageEditorProBaseEntries[safeIndex].type;
    final nextId = ++_localAnchorIdSeed;
    final anchor = LocalAnchor(
      id: nextId,
      center: Offset(nx, ny),
      radius: 0.18,
      values: createDefaultLocalAnchorValues(),
      selectedParam: selectedParam,
    );
    _setEditorState(() {
      _localAnchors.add(anchor);
      _selectedLocalAnchorId = nextId;
      _localAddMode = false;
      _localShowAnchorMenu = false;
      _recordLocalSessionStep();
    });
  }

  void _updateLocalAnchorPosition(
    int anchorId,
    Offset localPosition,
    Rect imageRect,
  ) {
    final dx = ((localPosition.dx - imageRect.left) / imageRect.width).clamp(
      0.0,
      1.0,
    );
    final dy = ((localPosition.dy - imageRect.top) / imageRect.height).clamp(
      0.0,
      1.0,
    );
    final index = _localAnchors.indexWhere((anchor) => anchor.id == anchorId);
    if (index < 0) return;
    _setEditorState(() {
      _localAnchors[index] = _localAnchors[index].copyWith(
        center: Offset(dx, dy),
      );
      _selectedLocalAnchorId = anchorId;
      _localShowAnchorMenu = false;
    });
  }

  void _updateLocalAnchorRadius(int anchorId, double radius) {
    final index = _localAnchors.indexWhere((anchor) => anchor.id == anchorId);
    if (index < 0) return;
    final clamped = radius.clamp(0.06, 0.45);
    _setEditorState(() {
      _localAnchors[index] = _localAnchors[index].copyWith(radius: clamped);
      _selectedLocalAnchorId = anchorId;
      _localShowAnchorMenu = false;
    });
  }

  void _copySelectedLocalAnchor() {
    final selected = _selectedLocalAnchor;
    if (selected == null) return;
    if (_localAnchors.length >= _ImageEditorPageState._kLocalAnchorMaxCount) {
      _showLocalHint(UITextConstants.imageEditorProAnchorLimitReached);
      return;
    }
    final nextId = ++_localAnchorIdSeed;
    final copied = LocalAnchor(
      id: nextId,
      center: Offset(
        (selected.center.dx + 0.05).clamp(0.0, 1.0),
        (selected.center.dy + 0.05).clamp(0.0, 1.0),
      ),
      radius: selected.radius,
      values: Map<String, double>.from(selected.values),
      selectedParam: selected.selectedParam,
    );
    _setEditorState(() {
      _localAnchors.add(copied);
      _selectedLocalAnchorId = copied.id;
      _localShowAnchorMenu = false;
      _recordLocalSessionStep();
    });
  }

  void _deleteSelectedLocalAnchor() {
    final selected = _selectedLocalAnchor;
    if (selected == null) return;
    _setEditorState(() {
      _localAnchors.removeWhere((anchor) => anchor.id == selected.id);
      _selectedLocalAnchorId = _localAnchors.isNotEmpty
          ? _localAnchors.last.id
          : null;
      _localShowAnchorMenu = false;
      _recordLocalSessionStep();
    });
  }

  bool get _isEditingHsl {
    return _selectedToolIndex == kImageEditorToolPro &&
        _selectedProCategory == kImageEditorProCategoryHsl;
  }

  bool get _isEditingBwLevels {
    return _selectedToolIndex == kImageEditorToolPro &&
        _selectedProCategory == kImageEditorProCategoryBwLevels;
  }

  bool get _isEditingLocal {
    return _selectedToolIndex == kImageEditorToolPro &&
        _selectedProCategory == kImageEditorProCategoryLocal;
  }

  bool get _hasProBaseAdjustments {
    for (final value in _proBaseValues.values) {
      if (value.abs() > 0.001) return true;
    }
    return false;
  }

  bool get _hasProHslAdjustments {
    for (final channelValues in _proHslValues.values) {
      for (final value in channelValues.values) {
        if (value.abs() > 0.001) return true;
      }
    }
    return false;
  }

  bool get _hasBwLevelsAdjustments {
    return _bwWhiteLevel.abs() > 0.001 || _bwBlackLevel.abs() > 0.001;
  }

  bool get _hasLocalAdjustments {
    for (final anchor in _localAnchors) {
      for (final value in anchor.values.values) {
        if (value.abs() > 0.001) return true;
      }
    }
    return false;
  }

  List<double> _identityColorMatrix() => const <double>[
    1,
    0,
    0,
    0,
    0,
    0,
    1,
    0,
    0,
    0,
    0,
    0,
    1,
    0,
    0,
    0,
    0,
    0,
    1,
    0,
  ];

  void _resetHslSessionHistory() {
    _hslSessionStack
      ..clear()
      ..add(cloneHslValues(_proHslValues));
    _hslSessionCursor = 0;
    _hslSessionBaselineValues = cloneHslValues(_proHslValues);
    _isComparingSessionBaseline = false;
  }

  void _resetBwSessionHistory() {
    _bwSessionBaselineWhiteLevel = _bwWhiteLevel;
    _bwSessionBaselineBlackLevel = _bwBlackLevel;
    _bwSessionStack
      ..clear()
      ..add(<String, double>{'white': _bwWhiteLevel, 'black': _bwBlackLevel});
    _bwSessionCursor = 0;
    _isComparingSessionBaseline = false;
  }

  void _recordHslSessionStep() {
    final snapshot = cloneHslValues(_proHslValues);
    if (_hslSessionCursor >= 0 &&
        _hslSessionCursor < _hslSessionStack.length &&
        _hslSessionStack[_hslSessionCursor].toString() == snapshot.toString()) {
      return;
    }
    if (_hslSessionCursor < _hslSessionStack.length - 1) {
      _hslSessionStack.removeRange(
        _hslSessionCursor + 1,
        _hslSessionStack.length,
      );
    }
    _hslSessionStack.add(snapshot);
    _hslSessionCursor = _hslSessionStack.length - 1;
  }

  void _onProHslValueChanged(String axis, double value) {
    final clamped = value.clamp(-100.0, 100.0);
    _setEditorState(() {
      _proHslValues[_selectedHslChannel] ??= {
        kHslAxisHue: 0,
        kHslAxisSaturation: 0,
        kHslAxisLuminance: 0,
      };
      _proHslValues[_selectedHslChannel]![axis] = clamped;
      _recordHslSessionStep();
    });
  }

  void _onBwLevelChanged({required bool isWhite, required double value}) {
    final clamped = value.clamp(-100.0, 100.0);
    _setEditorState(() {
      if (isWhite) {
        _bwWhiteLevel = clamped;
      } else {
        _bwBlackLevel = clamped;
      }
      _recordBwSessionStep();
    });
  }

  void _recordBwSessionStep() {
    final snapshot = <String, double>{
      'white': _bwWhiteLevel,
      'black': _bwBlackLevel,
    };
    if (_bwSessionCursor >= 0 &&
        _bwSessionCursor < _bwSessionStack.length &&
        _bwSessionStack[_bwSessionCursor].toString() == snapshot.toString()) {
      return;
    }
    if (_bwSessionCursor < _bwSessionStack.length - 1) {
      _bwSessionStack.removeRange(_bwSessionCursor + 1, _bwSessionStack.length);
    }
    _bwSessionStack.add(snapshot);
    _bwSessionCursor = _bwSessionStack.length - 1;
  }

  void _resetLocalSessionHistory() {
    _localSessionStack
      ..clear()
      ..add(cloneLocalAnchors(_localAnchors));
    _localSessionCursor = 0;
    _isComparingSessionBaseline = false;
  }

  void _recordLocalSessionStep() {
    final snapshot = cloneLocalAnchors(_localAnchors);
    if (_localSessionCursor >= 0 &&
        _localSessionCursor < _localSessionStack.length &&
        _localSessionStack[_localSessionCursor].toString() ==
            snapshot.toString()) {
      return;
    }
    if (_localSessionCursor < _localSessionStack.length - 1) {
      _localSessionStack.removeRange(
        _localSessionCursor + 1,
        _localSessionStack.length,
      );
    }
    _localSessionStack.add(snapshot);
    _localSessionCursor = _localSessionStack.length - 1;
  }

  bool _isProBaseSessionEdited() {
    for (final entry in kImageEditorProBaseEntries) {
      final current = _proBaseValues[entry.type] ?? 0;
      final initial = _proBaseSnapshotValues[entry.type] ?? 0;
      if ((current - initial).abs() > 0.001) {
        return true;
      }
    }
    return false;
  }

  bool _isProHslSessionEdited() {
    for (final channel in kImageEditorHslChannels) {
      final current = _proHslValues[channel.key] ?? const <String, double>{};
      final initial =
          _proHslSnapshotValues[channel.key] ?? const <String, double>{};
      for (final axis in const [
        kHslAxisHue,
        kHslAxisSaturation,
        kHslAxisLuminance,
      ]) {
        if (((current[axis] ?? 0) - (initial[axis] ?? 0)).abs() > 0.001) {
          return true;
        }
      }
    }
    return false;
  }

  bool _isProBwLevelsSessionEdited() {
    return (_bwWhiteLevel - _bwSnapshotWhiteLevel).abs() > 0.001 ||
        (_bwBlackLevel - _bwSnapshotBlackLevel).abs() > 0.001;
  }

  bool _isLocalSessionEdited() {
    if (_localAnchors.length != _localSnapshotAnchors.length) {
      return true;
    }
    for (var i = 0; i < _localAnchors.length; i++) {
      final current = _localAnchors[i];
      final initial = _localSnapshotAnchors[i];
      if (current.id != initial.id ||
          current.center != initial.center ||
          (current.radius - initial.radius).abs() > 0.001 ||
          current.selectedParam != initial.selectedParam) {
        return true;
      }
      for (final key in kLocalParamOrder) {
        if (((current.values[key] ?? 0) - (initial.values[key] ?? 0)).abs() >
            0.001) {
          return true;
        }
      }
    }
    return false;
  }

  /// 专业面板确认：确认即烘焙（与裁剪/滤镜/马赛克统一的一步一快照模型）。
  Future<void> _confirmProPanel() async {
    if (_selectedToolIndex != kImageEditorToolPro) return;
    final isOverall = _selectedProCategory == kImageEditorProCategoryOverall;
    final isLocal = _selectedProCategory == kImageEditorProCategoryLocal;
    final isHsl = _selectedProCategory == kImageEditorProCategoryHsl;
    final isBw = _selectedProCategory == kImageEditorProCategoryBwLevels;
    final isCurve = _selectedProCategory == kImageEditorProCategoryCurve;
    final isWb = _selectedProCategory == kImageEditorProCategoryWhiteBalance;

    ImageEditorStepPayload? payload;
    if (isOverall && _isProBaseSessionEdited() && _hasProBaseAdjustments) {
      payload = ImageEditorProBaseStepPayload(
        values: Map<String, double>.from(_proBaseValues),
      );
    } else if (isLocal && _isLocalSessionEdited() && _hasLocalAdjustments) {
      payload = ImageEditorProLocalStepPayload(
        anchors: cloneLocalAnchors(_localAnchors),
      );
    } else if (isHsl && _isProHslSessionEdited() && _hasProHslAdjustments) {
      payload = ImageEditorProHslStepPayload(
        values: cloneHslValues(_proHslValues),
      );
    } else if (isBw && _isProBwLevelsSessionEdited()) {
      payload = ImageEditorProBwLevelsStepPayload(
        whiteLevel: _bwWhiteLevel,
        blackLevel: _bwBlackLevel,
      );
    } else if (isCurve && _hasCurveAdjustments) {
      payload = ImageEditorProCurvesStepPayload(curves: _curvesState);
    } else if (isWb && _hasWhiteBalanceAdjustments) {
      payload = ImageEditorProWhiteBalanceStepPayload(
        temperature: _wbTemperature,
        tint: _wbTint,
      );
    }

    if (payload != null) {
      final subType = payload.subType!;
      final beforePath = _currentPath;
      final afterPath = await _bakeProCategoryToCurrentImage(subType);
      if (afterPath == null) {
        await _showEditorActionFailure(
          title: UITextConstants.imageEditorProTools,
        );
        return;
      }
      _commitBakedStep(
        payload: payload,
        beforePath: beforePath,
        afterPath: afterPath,
      );
      _resetProSessionValuesAfterBake(subType);
    }
    if (!mounted) return;
    _setEditorState(() {
      _hslPickerActive = false;
      _hslPickerPoint = null;
      _isComparingSessionBaseline = false;
      _selectedToolIndex = null;
      _showProToolbox = false;
    });
    _disposeCurveSessionResources();
  }

  /// 按类别烘焙当前会话到文件；曲线走 LUT 引擎，其余走矩阵引擎。
  Future<String?> _bakeProCategoryToCurrentImage(String subType) async {
    if (_currentPath.isEmpty) return null;
    try {
      final bytes = await _loadImageBytes(_currentPath);
      if (bytes.isEmpty) return null;
      final image = await ImageEditorExportEngine.decodeConstrained(bytes);
      ui.Image adjusted;
      if (subType == 'localAdjustments') {
        adjusted = await ImageEditorExportEngine.applyLocalAdjustments(
          image,
          <ImageEditorLocalRenderSpec>[
            for (final anchor in _localAnchors)
              if (anchor.values.values.any((value) => value.abs() > 0.001))
                ImageEditorLocalRenderSpec(
                  center: anchor.center,
                  radiusOnShortSide: anchor.radius,
                  colorMatrix: _buildLocalAnchorColorMatrix(anchor),
                ),
          ],
        );
      } else if (subType == 'curves') {
        adjusted = await ImageEditorExportEngine.applyCurves(
          image,
          _curvesState,
        );
      } else {
        final matrix = switch (subType) {
          'baseAdjustments' => _buildProBaseColorMatrix(),
          'hslAdjustments' => _buildProHslColorMatrix(_proHslValues),
          'bwLevelsAdjustments' => _bwLevelsMatrix(
            whiteLevel: _bwWhiteLevel,
            blackLevel: _bwBlackLevel,
          ),
          'whiteBalance' => _buildWhiteBalanceColorMatrix(),
          _ => _identityColorMatrix(),
        };
        adjusted = await ImageEditorExportEngine.applyColorMatrix(
          image,
          matrix,
        );
      }
      image.dispose();
      return _writeImageToTemp(adjusted, 'pro_$subType');
    } catch (_) {
      return null;
    }
  }

  /// 烘焙成功后清零对应会话值，避免预览与文件双重叠加。
  void _resetProSessionValuesAfterBake(String subType) {
    switch (subType) {
      case 'baseAdjustments':
        _proBaseValues.updateAll((key, value) => 0);
        _proBaseSnapshotValues.updateAll((key, value) => 0);
      case 'localAdjustments':
        _localAnchors.clear();
        _localSnapshotAnchors = <LocalAnchor>[];
        _selectedLocalAnchorId = null;
        _localSessionStack.clear();
        _localSessionCursor = -1;
      case 'hslAdjustments':
        _proHslValues = createDefaultHslValues();
        _proHslSnapshotValues = createDefaultHslValues();
        _hslSessionBaselineValues = createDefaultHslValues();
        _hslSessionStack.clear();
        _hslSessionCursor = -1;
      case 'bwLevelsAdjustments':
        _bwWhiteLevel = 0;
        _bwBlackLevel = 0;
        _bwSnapshotWhiteLevel = 0;
        _bwSnapshotBlackLevel = 0;
        _bwSessionBaselineWhiteLevel = 0;
        _bwSessionBaselineBlackLevel = 0;
        _bwSessionStack.clear();
        _bwSessionCursor = -1;
      case 'curves':
        _curvesState = ImageEditorCurvesState();
        _curvesSnapshot = ImageEditorCurvesState();
      case 'whiteBalance':
        _wbTemperature = 0;
        _wbTint = 0;
        _wbSnapshotTemperature = 0;
        _wbSnapshotTint = 0;
    }
  }
}
