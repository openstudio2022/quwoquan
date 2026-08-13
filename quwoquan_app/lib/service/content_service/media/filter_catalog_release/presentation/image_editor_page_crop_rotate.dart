part of 'image_editor_page.dart';

extension _ImageEditorPageCropRotate on _ImageEditorPageState {
  bool get _isRotateEdited {
    final normalized = _rotateDegrees % 360;
    return normalized != 0 ||
        _rotateFineDegrees.abs() > 0.001 ||
        _flipHorizontal ||
        _flipVertical;
  }

  void _applyRotateReset() {
    _rotateDegrees = 0;
    _rotateFineDegrees = 0;
    _flipHorizontal = false;
    _flipVertical = false;
  }

  void _resetRotateState() {
    _setEditorState(_applyRotateReset);
  }

  void _setRotateFineDegrees(double v) {
    final clamped = v.clamp(
      -RotateOverlayConstants.fineMaxDegrees,
      RotateOverlayConstants.fineMaxDegrees,
    );
    _setEditorState(() => _rotateFineDegrees = clamped);
  }

  void _prepareCropSnapshot() {
    _cropRatio = 'original';
    _cropInitialRatio = 'original';
    _cropRect = const Rect.fromLTWH(0, 0, 1, 1);
    _cropInitialRect = const Rect.fromLTWH(0, 0, 1, 1);
    _cropImageOffset = Offset.zero;
    _cropInitialImageOffset = Offset.zero;
    _cropEdited = false;
  }

  void _resetCropPanel() {
    const initialRect = Rect.fromLTWH(0, 0, 1, 1);
    _setEditorState(() {
      _cropRatio = 'original';
      _cropInitialRatio = 'original';
      _cropRect = initialRect;
      _cropInitialRect = initialRect;
      _cropImageOffset = Offset.zero;
      _cropInitialImageOffset = Offset.zero;
      _cropEdited = false;
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_cropRatioScrollController.hasClients) {
        _cropRatioScrollController.animateTo(
          0,
          duration: const Duration(milliseconds: 200),
          curve: Curves.easeOut,
        );
      }
    });
  }

  void _onCropRatioChanged(String ratio) {
    if (ratio == _cropRatio) return;
    _setEditorState(() {
      _cropRatio = ratio;
      if (_cropRatio == 'free') {
        _cropImageOffset = Offset.zero;
      } else {
        _cropImageOffset = _clampCropOffset(_cropImageOffset);
      }
      _cropEdited = _isCropStateDirty();
    });
  }

  void _loadImageAspectRatio(String path) {
    if (path.isEmpty) return;
    final isFile = path.startsWith('/') || (path.length > 1 && path[1] == ':');
    if (!isFile) {
      _loadRemoteImageAspectRatio(path);
      return;
    }
    final ImageProvider<Object> provider = localFileImageProvider(path);
    final stream = provider.resolve(ImageConfiguration.empty);
    late final ImageStreamListener listener;
    listener = ImageStreamListener((info, _) {
      stream.removeListener(listener);
      if (!mounted) return;
      final ratio = info.image.width / info.image.height;
      _setEditorState(() => _imageAspectRatio = ratio);
    }, onError: (error, stackTrace) => stream.removeListener(listener));
    stream.addListener(listener);
  }

  Future<void> _loadRemoteImageAspectRatio(String path) async {
    try {
      final bytes = await _loadImageBytes(path);
      if (bytes.isEmpty) return;
      final image = await ImageEditorExportEngine.decodeConstrained(bytes);
      final ratio = image.width / image.height;
      image.dispose();
      if (!mounted) return;
      _setEditorState(() => _imageAspectRatio = ratio);
    } catch (_) {
      return;
    }
  }

  bool _rectEquals(Rect a, Rect b) {
    const tolerance = 0.0001;
    return (a.left - b.left).abs() <= tolerance &&
        (a.top - b.top).abs() <= tolerance &&
        (a.right - b.right).abs() <= tolerance &&
        (a.bottom - b.bottom).abs() <= tolerance;
  }

  bool _offsetEquals(Offset a, Offset b) {
    const tolerance = 0.5;
    return (a.dx - b.dx).abs() <= tolerance && (a.dy - b.dy).abs() <= tolerance;
  }

  bool _isCropStateDirty() {
    if (_cropRatio != _cropInitialRatio) return true;
    if (!_rectEquals(_cropRect, _cropInitialRect)) return true;
    if (!_offsetEquals(_cropImageOffset, _cropInitialImageOffset)) return true;
    return false;
  }

  Future<String?> _writeImageToTemp(ui.Image image, String prefix) async {
    try {
      final data = await ImageEditorExportEngine.encodePng(image);
      if (data == null) return null;
      return writeAppTemporaryFileBytes(
        fileName: '${prefix}_${DateTime.now().millisecondsSinceEpoch}.png',
        bytes: data,
      );
    } finally {
      image.dispose();
    }
  }

  Future<String?> _applyCropToCurrentImage() async {
    if (_currentPath.isEmpty) return null;
    try {
      final bytes = await _loadImageBytes(_currentPath);
      if (bytes.isEmpty) return null;
      final image = await ImageEditorExportEngine.decodeConstrained(bytes);
      final baseRect = _cropImageRect == Rect.zero
          ? _resolveImageRect(_cropLayoutSize)
          : _cropImageRect;
      final imageRect = baseRect.shift(_cropImageOffset);
      if (imageRect.isEmpty) return null;
      final cropRect = _resolveCropRect(imageRect).intersect(imageRect);
      if (cropRect.isEmpty) return null;
      final scaleX = image.width / imageRect.width;
      final scaleY = image.height / imageRect.height;
      final srcRect = Rect.fromLTWH(
        (cropRect.left - imageRect.left) * scaleX,
        (cropRect.top - imageRect.top) * scaleY,
        cropRect.width * scaleX,
        cropRect.height * scaleY,
      );
      final croppedImage = await ImageEditorExportEngine.cropImage(
        image,
        srcRect,
      );
      image.dispose();
      return _writeImageToTemp(croppedImage, 'crop');
    } catch (e) {
      return null;
    }
  }

  Future<String?> _applyRotateToCurrentImage() async {
    if (_currentPath.isEmpty) return null;
    try {
      final totalDegrees = _rotateDegrees + _rotateFineDegrees;
      if (totalDegrees == 0 && !_flipHorizontal && !_flipVertical) {
        return _currentPath;
      }
      final bytes = await _loadImageBytes(_currentPath);
      if (bytes.isEmpty) return null;
      final image = await ImageEditorExportEngine.decodeConstrained(bytes);
      // 旋转确认时导出“范围框内”结果，而非整张旋转包围盒。
      // 这里保持输出分辨率与原图一致，仅变换并裁切可见范围。
      final scale = RotateGeometry.scaleToFill(
        image.width.toDouble(),
        image.height.toDouble(),
        totalDegrees * math.pi / 180,
      );
      final rotatedImage = await ImageEditorExportEngine.rotateAndFlip(
        image,
        totalDegrees: totalDegrees,
        scaleToFill: scale,
        flipHorizontal: _flipHorizontal,
        flipVertical: _flipVertical,
      );
      image.dispose();
      return _writeImageToTemp(rotatedImage, 'rotate');
    } catch (e) {
      return null;
    }
  }

  Future<String?> _applyFilterToCurrentImage() async {
    final preset = _selectedFilterPreset;
    if (preset == null) return _currentPath;
    final strength = (_filterStrengthByPresetId[preset.id] ?? _filterIntensity)
        .clamp(0, 100);
    if (strength <= 0.001) return _currentPath;
    if (_currentPath.isEmpty) return null;
    try {
      final bytes = await _loadImageBytes(_currentPath);
      if (bytes.isEmpty) return null;
      final image = await ImageEditorExportEngine.decodeConstrained(bytes);
      // 滤镜与整体面板同源：纯色彩矩阵 + 细节类逐像素管线（GWT-009）。
      final adjusted = await ImageEditorExportEngine.applyBaseAdjustments(
        image,
        colorMatrix: _buildFilterColorMatrix(preset, strength.toDouble()),
        detail: _buildFilterDetailSpec(preset, strength.toDouble()),
      );
      image.dispose();
      return _writeImageToTemp(adjusted, 'filter');
    } catch (_) {
      return null;
    }
  }

  /// 马赛克烘焙：全尺寸合成笔画。
  Future<String?> _applyMosaicToCurrentImage() async {
    if (_currentPath.isEmpty || _mosaicStrokes.isEmpty) return _currentPath;
    try {
      final bytes = await _loadImageBytes(_currentPath);
      if (bytes.isEmpty) return null;
      final image = await ImageEditorExportEngine.decodeConstrained(bytes);
      final composed = await ImageEditorExportEngine.applyMosaicStrokes(
        image,
        List<ImageEditorMosaicStroke>.of(_mosaicStrokes),
      );
      image.dispose();
      return _writeImageToTemp(composed, 'mosaic');
    } catch (_) {
      return null;
    }
  }

  /// 文字烘焙：全尺寸合成文字项。
  Future<String?> _applyTextToCurrentImage() async {
    if (_currentPath.isEmpty || _textItems.isEmpty) return _currentPath;
    try {
      final bytes = await _loadImageBytes(_currentPath);
      if (bytes.isEmpty) return null;
      final image = await ImageEditorExportEngine.decodeConstrained(bytes);
      final composed = await ImageEditorExportEngine.applyTextItems(
        image,
        List<ImageEditorTextItem>.of(_textItems),
      );
      image.dispose();
      return _writeImageToTemp(composed, 'text');
    } catch (_) {
      return null;
    }
  }

  Future<Uint8List> _loadImageBytes(String path) async {
    final isFile = path.startsWith('/') || (path.length > 1 && path[1] == ':');
    if (isFile) {
      final fileStorage = ref.read(fileStorageGatewayProvider);
      if (!await fileStorage.exists(path)) return Uint8List(0);
      return Uint8List.fromList(await fileStorage.readAsBytes(path));
    }
    final bundle = NetworkAssetBundle(Uri.parse(path));
    final data = await bundle.load(path);
    return data.buffer.asUint8List();
  }

  /// 提交一个已烘焙步骤：写入路径槽位、记录快照、上报工具使用。
  void _commitBakedStep({
    required ImageEditorStepPayload payload,
    required String beforePath,
    required String afterPath,
  }) {
    _paths[_currentIndex] = afterPath;
    _loadImageAspectRatio(afterPath);
    _clearFilterPreviewCache();
    _pushStep(
      ImageEditorStep(
        payload: payload,
        imageIndex: _currentIndex,
        beforePath: beforePath,
        afterPath: afterPath,
      ),
    );
  }

  Future<void> _confirmToolPanel() async {
    if (_selectedToolIndex == null) return;
    final toolIndex = _selectedToolIndex!;
    final beforePath = _currentPath;
    if (toolIndex == kImageEditorToolRotate) {
      if (!_isRotateEdited) {
        _setEditorState(() => _selectedToolIndex = null);
        return;
      }
      final rotatedPath = await _applyRotateToCurrentImage();
      if (rotatedPath == null) {
        await _showEditorActionFailure(title: MediaText.imageEditorRotate);
        return;
      }
      _commitBakedStep(
        payload: ImageEditorRotateStepPayload(
          degrees: _rotateDegrees,
          fineDegrees: _rotateFineDegrees,
          flipHorizontal: _flipHorizontal,
          flipVertical: _flipVertical,
        ),
        beforePath: beforePath,
        afterPath: rotatedPath,
      );
      _resetRotateState();
    }
    if (toolIndex == kImageEditorToolCrop) {
      final croppedPath = await _applyCropToCurrentImage();
      if (croppedPath == null) {
        await _showEditorActionFailure(title: MediaText.imageEditorCrop);
        return;
      }
      _commitBakedStep(
        payload: ImageEditorCropStepPayload(ratio: _cropRatio),
        beforePath: beforePath,
        afterPath: croppedPath,
      );
      _prepareCropSnapshot();
    }
    if (toolIndex == kImageEditorToolFilter) {
      final preset = _selectedFilterPreset;
      if (preset != null && _hasFilterAdjustments) {
        final filteredPath = await _applyFilterToCurrentImage();
        if (filteredPath == null) {
          await _showEditorActionFailure(title: MediaText.imageEditorFilter);
          return;
        }
        _commitBakedStep(
          payload: ImageEditorFilterStepPayload(
            presetId: preset.id,
            presetName: preset.name,
            intensity: _filterIntensity,
          ),
          beforePath: beforePath,
          afterPath: filteredPath,
        );
        await _filterRepository.savePresetUseStats(preset.id);
        await _rebuildFilterData();
      }
    }
    if (toolIndex == kImageEditorToolMosaic) {
      if (_mosaicStrokes.isNotEmpty) {
        final mosaicPath = await _applyMosaicToCurrentImage();
        if (mosaicPath == null) {
          await _showEditorActionFailure(title: MediaText.imageEditorMosaic);
          return;
        }
        _commitBakedStep(
          payload: ImageEditorMosaicStepPayload(
            strokes: List<ImageEditorMosaicStroke>.of(_mosaicStrokes),
          ),
          beforePath: beforePath,
          afterPath: mosaicPath,
        );
      }
      _setEditorState(() {
        _mosaicStrokes.clear();
        _activeMosaicStroke = null;
      });
      _disposeMosaicSessionResources();
    }
    if (toolIndex == kImageEditorToolText) {
      if (_textItems.isNotEmpty) {
        final textPath = await _applyTextToCurrentImage();
        if (textPath == null) {
          await _showEditorActionFailure(title: MediaText.imageEditorText);
          return;
        }
        _commitBakedStep(
          payload: ImageEditorTextStepPayload(
            items: List<ImageEditorTextItem>.of(_textItems),
          ),
          beforePath: beforePath,
          afterPath: textPath,
        );
      }
      _setEditorState(() {
        _textItems.clear();
        _selectedTextItemId = null;
      });
    }
    if (!mounted) return;
    _setEditorState(() {
      if (toolIndex == kImageEditorToolFilter) {
        _selectedFilterPresetId = null;
        _filterIntensity = 100;
      }
      _selectedToolIndex = null;
    });
    if (toolIndex == kImageEditorToolFilter) {
      _disposeFilterPreviewResources();
    }
  }

  /// 剪裁底部 X：放弃剪裁，仅退出剪裁面板，返回图片编辑器。
  void _cancelCropAndExit() {
    _setEditorState(() => _selectedToolIndex = null);
  }

  /// 旋转底部 X：放弃旋转，仅退出旋转面板并恢复初始旋转状态。
  void _cancelRotateAndExit() {
    _setEditorState(() {
      _applyRotateReset();
      _selectedToolIndex = null;
    });
  }

  /// 剪裁顶栏完成 / 底部 ✓：应用剪裁并仅退出剪裁面板，返回图片编辑器（不退出整个编辑器）。
  Future<void> _confirmCropAndExit() async {
    if (_selectedToolIndex != kImageEditorToolCrop) return;
    final beforePath = _currentPath;
    final croppedPath = await _applyCropToCurrentImage();
    if (croppedPath == null) {
      await _showEditorActionFailure(title: MediaText.imageEditorCrop);
      return;
    }
    _commitBakedStep(
      payload: ImageEditorCropStepPayload(ratio: _cropRatio),
      beforePath: beforePath,
      afterPath: croppedPath,
    );
    _prepareCropSnapshot();
    if (!mounted) return;
    _setEditorState(() => _selectedToolIndex = null);
  }

  /// 缩略图条拖拽重排：保持当前预览图不变，回写新顺序（[onDone] 会带出完整 _paths）。
  /// newIndex 为 Flutter 标准插入位（0..length）。
}
