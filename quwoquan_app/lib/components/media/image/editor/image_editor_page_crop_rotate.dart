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
    final ImageProvider provider = FileImage(File(path));
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
      final codec = await ui.instantiateImageCodec(bytes);
      final frame = await codec.getNextFrame();
      final ratio = frame.image.width / frame.image.height;
      frame.image.dispose();
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

  Future<String?> _applyCropToCurrentImage() async {
    if (_currentPath.isEmpty) return null;
    try {
      final bytes = await _loadImageBytes(_currentPath);
      if (bytes.isEmpty) return null;
      final codec = await ui.instantiateImageCodec(bytes);
      final frame = await codec.getNextFrame();
      final image = frame.image;
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
      final recorder = ui.PictureRecorder();
      final canvas = Canvas(recorder);
      final dstRect = Rect.fromLTWH(0, 0, srcRect.width, srcRect.height);
      canvas.drawImageRect(image, srcRect, dstRect, Paint());
      final croppedImage = await recorder.endRecording().toImage(
        srcRect.width.round(),
        srcRect.height.round(),
      );
      final data = await croppedImage.toByteData(
        format: ui.ImageByteFormat.png,
      );
      if (data == null) return null;
      final tempDir = await getTemporaryDirectory();
      final file = File(
        '${tempDir.path}/crop_${DateTime.now().millisecondsSinceEpoch}.png',
      );
      await file.writeAsBytes(data.buffer.asUint8List());
      return file.path;
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
      final codec = await ui.instantiateImageCodec(bytes);
      final frame = await codec.getNextFrame();
      final image = frame.image;
      final radians = totalDegrees * math.pi / 180;
      // 旋转确认时导出“范围框内”结果，而非整张旋转包围盒。
      // 这里保持输出分辨率与原图一致，仅变换并裁切可见范围。
      final scale = RotateGeometry.scaleToFill(
        image.width.toDouble(),
        image.height.toDouble(),
        radians,
      );
      final recorder = ui.PictureRecorder();
      final canvas = Canvas(recorder);
      final outputWidth = image.width.toDouble();
      final outputHeight = image.height.toDouble();
      canvas.translate(outputWidth / 2, outputHeight / 2);
      canvas.rotate(radians);
      canvas.scale(
        _flipHorizontal ? -scale : scale,
        _flipVertical ? -scale : scale,
      );
      canvas.translate(-image.width / 2, -image.height / 2);
      canvas.drawImage(image, Offset.zero, Paint());
      final rotatedImage = await recorder.endRecording().toImage(
        outputWidth.round(),
        outputHeight.round(),
      );
      final data = await rotatedImage.toByteData(
        format: ui.ImageByteFormat.png,
      );
      if (data == null) return null;
      final tempDir = await getTemporaryDirectory();
      final file = File(
        '${tempDir.path}/rotate_${DateTime.now().millisecondsSinceEpoch}.png',
      );
      await file.writeAsBytes(data.buffer.asUint8List());
      return file.path;
    } catch (e) {
      return null;
    }
  }

  Future<String?> _applyProAdjustmentsToCurrentImage() async {
    if (_currentPath.isEmpty ||
        (!_hasProBaseAdjustments &&
            !_hasProHslAdjustments &&
            !_hasBwLevelsAdjustments &&
            !_hasLocalAdjustments)) {
      return _currentPath;
    }
    try {
      final bytes = await _loadImageBytes(_currentPath);
      if (bytes.isEmpty) return null;
      final codec = await ui.instantiateImageCodec(bytes);
      final frame = await codec.getNextFrame();
      final image = frame.image;
      final recorder = ui.PictureRecorder();
      final canvas = Canvas(recorder);
      final dstRect = Rect.fromLTWH(
        0,
        0,
        image.width.toDouble(),
        image.height.toDouble(),
      );
      final paint = Paint()
        ..colorFilter = ColorFilter.matrix(_buildCombinedProColorMatrix());
      canvas.drawImageRect(image, dstRect, dstRect, paint);
      final adjusted = await recorder.endRecording().toImage(
        image.width,
        image.height,
      );
      final data = await adjusted.toByteData(format: ui.ImageByteFormat.png);
      if (data == null) return null;
      final tempDir = await getTemporaryDirectory();
      final file = File(
        '${tempDir.path}/pro_adjust_${DateTime.now().millisecondsSinceEpoch}.png',
      );
      await file.writeAsBytes(data.buffer.asUint8List());
      return file.path;
    } catch (_) {
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
      final codec = await ui.instantiateImageCodec(bytes);
      final frame = await codec.getNextFrame();
      final image = frame.image;
      final recorder = ui.PictureRecorder();
      final canvas = Canvas(recorder);
      final rect = Rect.fromLTWH(
        0,
        0,
        image.width.toDouble(),
        image.height.toDouble(),
      );
      final paint = Paint()
        ..colorFilter = ColorFilter.matrix(
          _buildFilterColorMatrix(preset, strength.toDouble()),
        );
      canvas.drawImageRect(image, rect, rect, paint);
      final adjusted = await recorder.endRecording().toImage(
        image.width,
        image.height,
      );
      final data = await adjusted.toByteData(format: ui.ImageByteFormat.png);
      if (data == null) return null;
      final tempDir = await getTemporaryDirectory();
      final file = File(
        '${tempDir.path}/filter_${DateTime.now().millisecondsSinceEpoch}.png',
      );
      await file.writeAsBytes(data.buffer.asUint8List());
      return file.path;
    } catch (_) {
      return null;
    }
  }

  Future<Uint8List> _loadImageBytes(String path) async {
    final isFile = path.startsWith('/') || (path.length > 1 && path[1] == ':');
    if (isFile) {
      final file = File(path);
      if (!file.existsSync()) return Uint8List(0);
      return file.readAsBytes();
    }
    final bundle = NetworkAssetBundle(Uri.parse(path));
    final data = await bundle.load(path);
    return data.buffer.asUint8List();
  }

  Future<void> _confirmToolPanel() async {
    if (_selectedToolIndex == null) return;
    final toolIndex = _selectedToolIndex!;
    final type = kImageEditorToolTypes[toolIndex];
    final params = imageEditorToolConfirmParamsBase(toolIndex);
    if (toolIndex == kImageEditorToolRotate) {
      if (!_isRotateEdited) {
        _setEditorState(() => _selectedToolIndex = null);
        return;
      }
      final rotatedPath = await _applyRotateToCurrentImage();
      if (rotatedPath != null) {
        _paths[_currentIndex] = rotatedPath;
        _loadImageAspectRatio(rotatedPath);
        _clearFilterPreviewCache();
        params['degrees'] = _rotateDegrees;
        params['fineDegrees'] = _rotateFineDegrees;
        params['flipHorizontal'] = _flipHorizontal;
        params['flipVertical'] = _flipVertical;
        params['path'] = rotatedPath;
        _resetRotateState();
      } else {
        await _showEditorActionFailure(title: '旋转未保存');
        return;
      }
    }
    if (toolIndex == kImageEditorToolCrop) {
      final croppedPath = await _applyCropToCurrentImage();
      if (croppedPath != null) {
        _paths[_currentIndex] = croppedPath;
        _loadImageAspectRatio(croppedPath);
        _clearFilterPreviewCache();
        _prepareCropSnapshot();
        params['ratio'] = _cropRatio;
        params['path'] = croppedPath;
      } else {
        await _showEditorActionFailure(title: '裁剪未保存');
        return;
      }
    }
    if (toolIndex == kImageEditorToolFilter) {
      final preset = _selectedFilterPreset;
      if (preset != null && _hasFilterAdjustments) {
        final filteredPath = await _applyFilterToCurrentImage();
        if (filteredPath == null) {
          await _showEditorActionFailure(title: '滤镜未保存');
          return;
        }
        _paths[_currentIndex] = filteredPath;
        _loadImageAspectRatio(filteredPath);
        _clearFilterPreviewCache();
        params['path'] = filteredPath;
        params['category'] = _filterCategoryIndex;
        params['presetId'] = preset.id;
        params['presetName'] = preset.name;
        params['intensity'] = _filterIntensity;
        await _filterRepository.savePresetUseStats(preset.id);
        await _rebuildFilterData();
      } else {
        params['category'] = _filterCategoryIndex;
        params['presetId'] = null;
        params['intensity'] = 0;
      }
    }
    if (toolIndex == kImageEditorToolMosaic) {
      params['type'] = _mosaicTypeIndex;
      params['size'] = _mosaicBrushSize;
    }
    if (toolIndex == kImageEditorToolFrame) {
      params['template'] = _frameTemplateIndex;
    }
    if (toolIndex == kImageEditorToolText) {
      params['style'] = _textStyleIndex;
      params['color'] = _textColorIndex;
    }
    _pushStep(ImageEditorStep(type: type, params: params));
    _setEditorState(() {
      if (toolIndex == kImageEditorToolFilter) {
        _selectedFilterPresetId = null;
        _filterIntensity = 100;
      }
      _selectedToolIndex = null;
    });
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
    final croppedPath = await _applyCropToCurrentImage();
    if (croppedPath == null) {
      await _showEditorActionFailure(title: '裁剪未保存');
      return;
    }
    _paths[_currentIndex] = croppedPath;
    _loadImageAspectRatio(croppedPath);
    _clearFilterPreviewCache();
    _prepareCropSnapshot();
    _pushStep(
      ImageEditorStep(
        type: 'crop',
        params: {'ratio': _cropRatio, 'path': croppedPath},
      ),
    );
    if (!mounted) return;
    _setEditorState(() => _selectedToolIndex = null);
  }

  /// 缩略图条拖拽重排：保持当前预览图不变，回写新顺序（[onDone] 会带出完整 _paths）。
  /// newIndex 为 Flutter 标准插入位（0..length）。
}
