part of 'image_editor_page.dart';

extension _ImageEditorPageProAdjustments on _ImageEditorPageState {
  void _closePanel() {
    _setEditorState(() {
      _selectedToolIndex = null;
      _hslPickerActive = false;
      _wbPickerActive = false;
      _wbPickerPoint = null;
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
    _perspectiveSnapshotHorizontal = _perspectiveHorizontal;
    _perspectiveSnapshotVertical = _perspectiveVertical;
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
      _perspectiveHorizontal = _perspectiveSnapshotHorizontal;
      _perspectiveVertical = _perspectiveSnapshotVertical;
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
      _wbPickerActive = false;
      _wbPickerPoint = null;
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
    _disposeHslSessionResources();
    _disposeBasePreviewResources();
    _disposeLocalPreviewResources();
  }

  void _onProBaseValueChanged(String toolType, double value) {
    if (_selectedToolIndex == kImageEditorToolPro &&
        _selectedProCategory == kImageEditorProCategoryLocal &&
        _selectedLocalAnchor == null) {
      _showLocalHint(MediaText.imageEditorProAnchorSelectHint);
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
    if (_isEditingOverall) {
      _scheduleBasePreviewRecompute();
    }
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
      _showLocalHint(MediaText.imageEditorProAnchorLimitReached);
      return;
    }
    _setEditorState(() {
      _localAddMode = toEnable;
      _localShowAnchorMenu = false;
    });
    if (toEnable) {
      _showLocalHint(MediaText.imageEditorProAnchorScaleHint);
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
      _showLocalHint(MediaText.imageEditorProAnchorLimitReached);
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
      _showLocalHint(MediaText.imageEditorProAnchorLimitReached);
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
    _scheduleHslPreviewRecompute();
  }

  /// UI 8 通道值 → 引擎分带渲染参数（页面边界唯一映射）。
  List<ImageEditorHslBandSpec> _hslBandSpecs(
    Map<String, Map<String, double>> values,
  ) {
    return <ImageEditorHslBandSpec>[
      for (final channel in kImageEditorHslChannels)
        ImageEditorHslBandSpec(
          hueMin: channel.hueMin,
          hueMax: channel.hueMax,
          hueShift: values[channel.key]?[kHslAxisHue] ?? 0,
          saturation: values[channel.key]?[kHslAxisSaturation] ?? 0,
          luminance: values[channel.key]?[kHslAxisLuminance] ?? 0,
        ),
    ];
  }

  bool get _isEditingOverall {
    return _selectedToolIndex == kImageEditorToolPro &&
        _selectedProCategory == kImageEditorProCategoryOverall;
  }

  void _disposeLocalPreviewResources() {
    _localPreviewBase?.dispose();
    _localPreviewBase = null;
    _localPreviewBaseRgba = null;
    _localPreviewImage?.dispose();
    _localPreviewImage = null;
    _localPreviewDirty = false;
    _localPreviewComputing = false;
  }

  /// 进入局部面板：异步准备降采样底图供 CPU 局部预览。
  void _prepareLocalPreviewSession() {
    _disposeLocalPreviewResources();
    unawaited(_loadLocalPreviewBase());
  }

  Future<void> _loadLocalPreviewBase() async {
    try {
      final bytes = await _loadImageBytes(_currentPath);
      if (bytes.isEmpty || !mounted) return;
      final image = await ImageEditorExportEngine.decodeConstrained(
        bytes,
        maxDimension: ImageEditorExportEngine.kPreviewDecodeDimension,
      );
      final data = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
      if (!mounted) {
        image.dispose();
        return;
      }
      _setEditorState(() {
        _localPreviewBase = image;
        _localPreviewBaseRgba = data?.buffer.asUint8List();
      });
      _scheduleLocalPreviewRecompute();
    } catch (error) {
      _observability.recordPageState(
        pageName: _ImageEditorPageState._kPageName,
        phase: 'failure',
        surface: _ImageEditorPageState._kSurfaceId,
        copyKey: 'local_preview_load',
        error: error is Exception ? error : null,
      );
    }
  }

  void _scheduleLocalPreviewRecompute() {
    if (_localPreviewComputing) {
      _localPreviewDirty = true;
      return;
    }
    _localPreviewDirty = false;
    _localPreviewComputing = true;
    unawaited(_recomputeLocalPreview());
  }

  Future<void> _recomputeLocalPreview() async {
    try {
      final base = _localPreviewBase;
      final baseRgba = _localPreviewBaseRgba;
      if (base == null || baseRgba == null || !mounted) {
        return;
      }
      final specs = _buildLocalRenderSpecs();
      if (specs.isEmpty) {
        final old = _localPreviewImage;
        _setEditorState(() => _localPreviewImage = null);
        old?.dispose();
        return;
      }
      final pixels = Uint8List.fromList(baseRgba);
      ImageEditorExportEngine.applyLocalAdjustmentsToRgbaPixels(
        pixels,
        base.width,
        base.height,
        specs,
      );
      final buffer = await ui.ImmutableBuffer.fromUint8List(pixels);
      final descriptor = ui.ImageDescriptor.raw(
        buffer,
        width: base.width,
        height: base.height,
        pixelFormat: ui.PixelFormat.rgba8888,
      );
      final codec = await descriptor.instantiateCodec();
      final frame = await codec.getNextFrame();
      if (!mounted) {
        frame.image.dispose();
        return;
      }
      final old = _localPreviewImage;
      _setEditorState(() => _localPreviewImage = frame.image);
      if (!identical(old, frame.image)) {
        old?.dispose();
      }
    } finally {
      _localPreviewComputing = false;
      if (_localPreviewDirty && mounted) {
        _scheduleLocalPreviewRecompute();
      }
    }
  }

  void _disposeBasePreviewResources() {
    _basePreviewBase?.dispose();
    _basePreviewBase = null;
    _basePreviewBaseRgba = null;
    _basePreviewImage?.dispose();
    _basePreviewImage = null;
    _basePreviewDirty = false;
    _basePreviewComputing = false;
  }

  /// 进入整体面板：异步准备降采样底图供 CPU 组合预览。
  void _prepareBasePreviewSession() {
    _disposeBasePreviewResources();
    unawaited(_loadBasePreviewBase());
  }

  Future<void> _loadBasePreviewBase() async {
    try {
      final bytes = await _loadImageBytes(_currentPath);
      if (bytes.isEmpty || !mounted) return;
      final image = await ImageEditorExportEngine.decodeConstrained(
        bytes,
        maxDimension: ImageEditorExportEngine.kPreviewDecodeDimension,
      );
      final data = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
      if (!mounted) {
        image.dispose();
        return;
      }
      _setEditorState(() {
        _basePreviewBase = image;
        _basePreviewBaseRgba = data?.buffer.asUint8List();
      });
      _scheduleBasePreviewRecompute();
    } catch (error) {
      _observability.recordPageState(
        pageName: _ImageEditorPageState._kPageName,
        phase: 'failure',
        surface: _ImageEditorPageState._kSurfaceId,
        copyKey: 'base_preview_load',
        error: error is Exception ? error : null,
      );
    }
  }

  void _scheduleBasePreviewRecompute() {
    if (_basePreviewComputing) {
      _basePreviewDirty = true;
      return;
    }
    _basePreviewDirty = false;
    _basePreviewComputing = true;
    unawaited(_recomputeBasePreview());
  }

  Future<void> _recomputeBasePreview() async {
    try {
      final base = _basePreviewBase;
      final baseRgba = _basePreviewBaseRgba;
      if (base == null || baseRgba == null || !mounted) {
        return;
      }
      if (!_hasProBaseAdjustments) {
        final old = _basePreviewImage;
        _setEditorState(() => _basePreviewImage = null);
        old?.dispose();
        return;
      }
      final pixels = Uint8List.fromList(baseRgba);
      ImageEditorExportEngine.applyColorMatrixToRgbaPixels(
        pixels,
        _buildProBaseColorMatrix(),
      );
      ImageEditorExportEngine.applyDetailAdjustmentsToRgbaPixels(
        pixels,
        base.width,
        base.height,
        _buildProBaseDetailSpec(),
      );
      final buffer = await ui.ImmutableBuffer.fromUint8List(pixels);
      final descriptor = ui.ImageDescriptor.raw(
        buffer,
        width: base.width,
        height: base.height,
        pixelFormat: ui.PixelFormat.rgba8888,
      );
      final codec = await descriptor.instantiateCodec();
      final frame = await codec.getNextFrame();
      if (!mounted) {
        frame.image.dispose();
        return;
      }
      final old = _basePreviewImage;
      _setEditorState(() => _basePreviewImage = frame.image);
      if (!identical(old, frame.image)) {
        old?.dispose();
      }
    } finally {
      _basePreviewComputing = false;
      if (_basePreviewDirty && mounted) {
        _scheduleBasePreviewRecompute();
      }
    }
  }

  void _disposeHslSessionResources() {
    _hslPreviewBase?.dispose();
    _hslPreviewBase = null;
    _hslPreviewBaseRgba = null;
    _hslPreviewImage?.dispose();
    _hslPreviewImage = null;
    _hslPreviewDirty = false;
    _hslPreviewComputing = false;
  }

  /// 进入 HSL 面板：异步准备降采样底图供 CPU 分带预览。
  void _prepareHslPreviewSession() {
    _disposeHslSessionResources();
    unawaited(_loadHslPreviewBase());
  }

  Future<void> _loadHslPreviewBase() async {
    try {
      final bytes = await _loadImageBytes(_currentPath);
      if (bytes.isEmpty || !mounted) return;
      final image = await ImageEditorExportEngine.decodeConstrained(
        bytes,
        maxDimension: ImageEditorExportEngine.kPreviewDecodeDimension,
      );
      final data = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
      if (!mounted) {
        image.dispose();
        return;
      }
      _setEditorState(() {
        _hslPreviewBase = image;
        _hslPreviewBaseRgba = data?.buffer.asUint8List();
      });
      _scheduleHslPreviewRecompute();
    } catch (error) {
      _observability.recordPageState(
        pageName: _ImageEditorPageState._kPageName,
        phase: 'failure',
        surface: _ImageEditorPageState._kSurfaceId,
        copyKey: 'hsl_preview_load',
        error: error is Exception ? error : null,
      );
    }
  }

  void _scheduleHslPreviewRecompute() {
    if (_hslPreviewComputing) {
      _hslPreviewDirty = true;
      return;
    }
    _hslPreviewDirty = false;
    _hslPreviewComputing = true;
    unawaited(_recomputeHslPreview());
  }

  Future<void> _recomputeHslPreview() async {
    try {
      final base = _hslPreviewBase;
      final baseRgba = _hslPreviewBaseRgba;
      if (base == null || baseRgba == null || !mounted) {
        return;
      }
      if (!_hasProHslAdjustments) {
        final old = _hslPreviewImage;
        _setEditorState(() => _hslPreviewImage = null);
        old?.dispose();
        return;
      }
      final pixels = Uint8List.fromList(baseRgba);
      ImageEditorExportEngine.applyHslBandsToRgbaPixels(
        pixels,
        _hslBandSpecs(_proHslValues),
      );
      final buffer = await ui.ImmutableBuffer.fromUint8List(pixels);
      final descriptor = ui.ImageDescriptor.raw(
        buffer,
        width: base.width,
        height: base.height,
        pixelFormat: ui.PixelFormat.rgba8888,
      );
      final codec = await descriptor.instantiateCodec();
      final frame = await codec.getNextFrame();
      if (!mounted) {
        frame.image.dispose();
        return;
      }
      final old = _hslPreviewImage;
      _setEditorState(() => _hslPreviewImage = frame.image);
      if (!identical(old, frame.image)) {
        old?.dispose();
      }
    } finally {
      _hslPreviewComputing = false;
      if (_hslPreviewDirty && mounted) {
        _scheduleHslPreviewRecompute();
      }
    }
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
    // 所有局部锚点变更（值/增删/拖动）收口于此，统一驱动 CPU 预览重算。
    _scheduleLocalPreviewRecompute();
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
    final isPerspective =
        _selectedProCategory == kImageEditorProCategoryPerspective;

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
    } else if (isPerspective && _hasPerspectiveAdjustments) {
      payload = ImageEditorProPerspectiveStepPayload(
        horizontal: _perspectiveHorizontal,
        vertical: _perspectiveVertical,
      );
    }

    if (payload != null) {
      final bakedPayload = payload;
      final subType = bakedPayload.subType!;
      final beforePath = _currentPath;
      final applied = await _runBakeAction(
        title: MediaText.imageEditorProTools,
        source: 'content.image_editor.bake_pro_$subType',
        bake: () => _bakeProCategoryToCurrentImage(subType),
        onBaked: (afterPath) => _commitBakedStep(
          payload: bakedPayload,
          beforePath: beforePath,
          afterPath: afterPath,
        ),
      );
      if (!applied) return;
      _resetProSessionValuesAfterBake(subType);
    }
    if (!mounted) return;
    _setEditorState(() {
      _hslPickerActive = false;
      _wbPickerActive = false;
      _wbPickerPoint = null;
      _hslPickerPoint = null;
      _isComparingSessionBaseline = false;
      _selectedToolIndex = null;
      _showProToolbox = false;
    });
    _disposeCurveSessionResources();
    _disposeHslSessionResources();
    _disposeBasePreviewResources();
    _disposeLocalPreviewResources();
  }

  /// 按类别烘焙当前会话到文件；曲线走 LUT 引擎，其余走矩阵引擎。
  Future<String> _bakeProCategoryToCurrentImage(String subType) async {
    final bytes = await _requireCurrentImageBytes();
    final image = await ImageEditorExportEngine.decodeConstrained(bytes);
    try {
      ui.Image adjusted;
      if (subType == 'localAdjustments') {
        // 真局部管线：矩阵+细节逐像素，径向权重与预览同一分段渐变。
        adjusted = await ImageEditorExportEngine.applyLocalAdjustments(
          image,
          _buildLocalRenderSpecs(),
        );
      } else if (subType == 'curves') {
        adjusted = await ImageEditorExportEngine.applyCurves(
          image,
          _curvesState,
        );
      } else if (subType == 'hslAdjustments') {
        // 真 HSL 分带（与 CPU 预览同一算法），不再用取平均矩阵近似。
        adjusted = await ImageEditorExportEngine.applyHslBands(
          image,
          _hslBandSpecs(_proHslValues),
        );
      } else if (subType == 'baseAdjustments') {
        // 整体面板：纯色彩矩阵 + 细节/分区/颗粒逐像素，与 CPU 预览同管线。
        adjusted = await ImageEditorExportEngine.applyBaseAdjustments(
          image,
          colorMatrix: _buildProBaseColorMatrix(),
          detail: _buildProBaseDetailSpec(),
        );
      } else if (subType == 'perspectiveAdjustments') {
        // 透视：预览 Transform 与烘焙共用 PerspectiveGeometry 同一矩阵。
        adjusted = await ImageEditorExportEngine.applyPerspective(
          image,
          horizontalDegrees: _perspectiveDegrees(_perspectiveHorizontal),
          verticalDegrees: _perspectiveDegrees(_perspectiveVertical),
        );
      } else {
        final matrix = switch (subType) {
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
      return await _writeImageToTemp(adjusted, 'pro_$subType');
    } finally {
      image.dispose();
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
      case 'perspectiveAdjustments':
        _perspectiveHorizontal = 0;
        _perspectiveVertical = 0;
        _perspectiveSnapshotHorizontal = 0;
        _perspectiveSnapshotVertical = 0;
    }
  }

  bool get _hasPerspectiveAdjustments =>
      _perspectiveHorizontal.abs() > 0.001 || _perspectiveVertical.abs() > 0.001;

  bool get _isEditingPerspective =>
      _selectedToolIndex == kImageEditorToolPro &&
      _selectedProCategory == kImageEditorProCategoryPerspective;

  /// 滑杆值（-100..100）映射透视角度（±kMaxDegrees 度）。
  double _perspectiveDegrees(double sliderValue) =>
      sliderValue / 100 * PerspectiveGeometry.kMaxDegrees;
}
