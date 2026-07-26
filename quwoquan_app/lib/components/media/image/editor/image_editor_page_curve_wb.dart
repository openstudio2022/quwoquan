part of 'image_editor_page.dart';

/// 曲线与白平衡会话逻辑：
/// - 曲线：降采样底图 + CPU LUT 实时预览 + 亮度直方图；
/// - 白平衡：色温/色调矩阵预览 + 灰世界自动白平衡。
extension _ImageEditorPageCurveWb on _ImageEditorPageState {
  bool get _isEditingCurve {
    return _selectedToolIndex == kImageEditorToolPro &&
        _selectedProCategory == kImageEditorProCategoryCurve;
  }

  bool get _isEditingWhiteBalance {
    return _selectedToolIndex == kImageEditorToolPro &&
        _selectedProCategory == kImageEditorProCategoryWhiteBalance;
  }

  bool get _hasCurveAdjustments => !_curvesState.isIdentity;

  bool get _hasWhiteBalanceAdjustments {
    return _wbTemperature.abs() > 0.001 || _wbTint.abs() > 0.001;
  }

  void _disposeCurveSessionResources() {
    _curvePreviewBase?.dispose();
    _curvePreviewBase = null;
    _curvePreviewBaseRgba = null;
    _curvePreviewImage?.dispose();
    _curvePreviewImage = null;
    _curveHistogram = null;
    _curvePreviewDirty = false;
    _curvePreviewComputing = false;
  }

  /// 进入曲线面板：重置状态并异步准备降采样底图与直方图。
  void _prepareCurveSession() {
    _curvesState = ImageEditorCurvesState();
    _curvesSnapshot = ImageEditorCurvesState();
    _curveChannel = ImageEditorCurveChannel.rgb;
    _disposeCurveSessionResources();
    unawaited(_loadCurvePreviewBase());
  }

  Future<void> _loadCurvePreviewBase() async {
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
      final rgba = data?.buffer.asUint8List();
      _setEditorState(() {
        _curvePreviewBase = image;
        _curvePreviewBaseRgba = rgba;
        _curveHistogram = rgba == null ? null : _computeLumaHistogram(rgba);
      });
      _scheduleCurvePreviewRecompute();
    } catch (error) {
      _observability.recordPageState(
        pageName: _ImageEditorPageState._kPageName,
        phase: 'failure',
        surface: _ImageEditorPageState._kSurfaceId,
        copyKey: 'curve_preview_load',
        error: error is Exception ? error : null,
      );
    }
  }

  List<int> _computeLumaHistogram(Uint8List rgba) {
    final histogram = List<int>.filled(256, 0);
    // 采样步长 4 像素，直方图形状足够且降低成本。
    for (var i = 0; i + 3 < rgba.length; i += 16) {
      final luma =
          (0.2126 * rgba[i] + 0.7152 * rgba[i + 1] + 0.0722 * rgba[i + 2])
              .round()
              .clamp(0, 255);
      histogram[luma]++;
    }
    return histogram;
  }

  void _onCurvesChanged(ImageEditorCurvesState next) {
    _setEditorState(() => _curvesState = next);
    _scheduleCurvePreviewRecompute();
  }

  void _resetCurrentCurveChannel() {
    _setEditorState(() {
      _curvesState = _curvesState.withChannelPoints(
        _curveChannel,
        ImageEditorCurvesState.identityPoints,
      );
    });
    _scheduleCurvePreviewRecompute();
  }

  /// 预览重算（合并连续拖动：计算期间的变更只标记 dirty，算完再补一轮）。
  void _scheduleCurvePreviewRecompute() {
    if (_curvePreviewComputing) {
      _curvePreviewDirty = true;
      return;
    }
    _curvePreviewDirty = false;
    _curvePreviewComputing = true;
    unawaited(_recomputeCurvePreview());
  }

  Future<void> _recomputeCurvePreview() async {
    try {
      final base = _curvePreviewBase;
      final baseRgba = _curvePreviewBaseRgba;
      if (base == null || baseRgba == null || !mounted) {
        return;
      }
      if (_curvesState.isIdentity) {
        final old = _curvePreviewImage;
        _setEditorState(() => _curvePreviewImage = null);
        old?.dispose();
        return;
      }
      final pixels = Uint8List.fromList(baseRgba);
      ImageEditorExportEngine.applyCurvesToRgbaPixels(pixels, _curvesState);
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
      final old = _curvePreviewImage;
      _setEditorState(() => _curvePreviewImage = frame.image);
      if (!identical(old, frame.image)) {
        old?.dispose();
      }
    } finally {
      _curvePreviewComputing = false;
      if (_curvePreviewDirty && mounted) {
        _scheduleCurvePreviewRecompute();
      }
    }
  }

  /// 曲线编辑中的中部图层：LUT 预览图（无调整时回退原图）。
  Widget _buildCurveSessionImageLayer(Widget fallback) {
    final preview = _curvePreviewImage;
    final content = preview != null
        ? Center(
            child: RawImage(
              image: preview,
              fit: BoxFit.contain,
              filterQuality: FilterQuality.medium,
            ),
          )
        : fallback;
    return Stack(
      fit: StackFit.expand,
      children: [
        content,
        Align(
          alignment: Alignment.bottomCenter,
          child: SafeArea(
            top: false,
            bottom: true,
            child: EditorSessionOpsStrip(
              supportsCompare: true,
              isComparing: _isComparingSessionBaseline,
              onCompareStart: () =>
                  _setEditorState(() => _isComparingSessionBaseline = true),
              onCompareEnd: () =>
                  _setEditorState(() => _isComparingSessionBaseline = false),
            ),
          ),
        ),
      ],
    );
  }

  /// 白平衡矩阵（色温 + 色调），预览与导出共用。
  List<double> _buildWhiteBalanceColorMatrix() {
    var matrix = _identityColorMatrix();
    matrix = _multiplyColorMatrices(_temperatureMatrix(_wbTemperature), matrix);
    matrix = _multiplyColorMatrices(_tintMatrix(_wbTint), matrix);
    return matrix;
  }

  /// 灰世界自动白平衡：以降采样图 RGB 均值估计色偏，反向设置色温/色调。
  Future<void> _applyAutoWhiteBalance() async {
    try {
      final bytes = await _loadImageBytes(_currentPath);
      if (bytes.isEmpty || !mounted) return;
      final image = await ImageEditorExportEngine.decodeConstrained(
        bytes,
        maxDimension: 320,
      );
      final data = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
      image.dispose();
      final rgba = data?.buffer.asUint8List();
      if (rgba == null || rgba.isEmpty || !mounted) return;
      double sumR = 0;
      double sumG = 0;
      double sumB = 0;
      var count = 0;
      for (var i = 0; i + 3 < rgba.length; i += 4) {
        sumR += rgba[i];
        sumG += rgba[i + 1];
        sumB += rgba[i + 2];
        count++;
      }
      if (count == 0) return;
      final avgR = sumR / count;
      final avgG = sumG / count;
      final avgB = sumB / count;
      if (avgG <= 1) return;
      // temperature 矩阵按 ±0.18 缩放 R/B 通道，反解需要的增益。
      final temperature = (((avgG / math.max(avgR, 1)) - 1) / 0.18 * 100).clamp(
        -100.0,
        100.0,
      );
      final tint = (((avgR + avgB) / 2 / math.max(avgG, 1) - 1) / 0.12 * 100)
          .clamp(-100.0, 100.0);
      _setEditorState(() {
        _wbTemperature = temperature.toDouble();
        _wbTint = tint.toDouble();
      });
    } catch (error) {
      _observability.recordPageState(
        pageName: _ImageEditorPageState._kPageName,
        phase: 'failure',
        surface: _ImageEditorPageState._kSurfaceId,
        copyKey: 'white_balance_auto',
        error: error is Exception ? error : null,
      );
    }
  }
}
