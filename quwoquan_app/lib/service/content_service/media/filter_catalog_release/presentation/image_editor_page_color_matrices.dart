part of 'image_editor_page.dart';

extension _ImageEditorPageColorMatrices on _ImageEditorPageState {
  List<double> _multiplyColorMatrices(List<double> a, List<double> b) {
    final out = List<double>.filled(20, 0);
    for (var row = 0; row < 4; row++) {
      final rowOffset = row * 5;
      for (var col = 0; col < 5; col++) {
        if (col == 4) {
          out[rowOffset + col] =
              a[rowOffset] * b[4] +
              a[rowOffset + 1] * b[9] +
              a[rowOffset + 2] * b[14] +
              a[rowOffset + 3] * b[19] +
              a[rowOffset + 4];
        } else {
          out[rowOffset + col] =
              a[rowOffset] * b[col] +
              a[rowOffset + 1] * b[col + 5] +
              a[rowOffset + 2] * b[col + 10] +
              a[rowOffset + 3] * b[col + 15];
        }
      }
    }
    return out;
  }

  List<double> _temperatureMatrix(double value) {
    final t = (value / 100).clamp(-1.0, 1.0);
    final redScale = (1 + t * 0.18).clamp(0.7, 1.3);
    final blueScale = (1 - t * 0.18).clamp(0.7, 1.3);
    return <double>[
      redScale,
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
      blueScale,
      0,
      0,
      0,
      0,
      0,
      1,
      0,
    ];
  }

  List<double> _tintMatrix(double value) {
    final t = (value / 100).clamp(-1.0, 1.0);
    final greenScale = (1 - t * 0.12).clamp(0.75, 1.25);
    final redBlueScale = (1 + t * 0.08).clamp(0.75, 1.25);
    return <double>[
      redBlueScale,
      0,
      0,
      0,
      0,
      0,
      greenScale,
      0,
      0,
      0,
      0,
      0,
      redBlueScale,
      0,
      0,
      0,
      0,
      0,
      1,
      0,
    ];
  }

  List<double> _bwLevelsMatrix({
    required double whiteLevel,
    required double blackLevel,
  }) {
    final inBlack = ((blackLevel + 100) / 200 * 120).clamp(0.0, 200.0);
    final inWhite = (255 - ((whiteLevel + 100) / 200 * 120)).clamp(55.0, 255.0);
    final safeWhite = math.max(inWhite.toDouble(), inBlack.toDouble() + 1.0);
    final scale = 255.0 / (safeWhite - inBlack);
    final offset = -inBlack * scale;
    return <double>[
      scale,
      0,
      0,
      0,
      offset,
      0,
      scale,
      0,
      0,
      offset,
      0,
      0,
      scale,
      0,
      offset,
      0,
      0,
      0,
      1,
      0,
    ];
  }

  /// 整体面板的纯色彩矩阵：只承载真正可用矩阵表达的项。
  ///
  /// 细节类（sharpen/texture/structure）、分区类（highlight/shadow）与
  /// 颗粒（grain）不再折算为对比度/亮度系数冒充效果——它们由
  /// [ImageEditorExportEngine.applyDetailAdjustmentsToRgbaPixels] 逐像素实现，
  /// 预览与烘焙同源（REQ-005）。
  /// 纯色彩矩阵（与滤镜链共用同一真相源 buildImageEditorBaseColorMatrix）：
  /// fade 为显式声明的「黑场抬升 + 轻度去饱和」精确线性实现；lightSense
  /// 不再折算进矩阵，由 detail 管线的 ambiance 真算法承载。
  List<double> _buildBaseColorMatrixFromValues(Map<String, double> values) {
    return buildImageEditorBaseColorMatrix(values);
  }

  /// values → 细节类像素参数（整体面板、局部锚点、滤镜链共用同一映射）。
  ImageEditorDetailSpec _detailSpecFromValues(Map<String, double> values) {
    return ImageEditorDetailSpec(
      sharpen: values['sharpen'] ?? 0,
      texture: values['texture'] ?? 0,
      structure: values['structure'] ?? 0,
      highlights: values['highlight'] ?? 0,
      shadows: values['shadow'] ?? 0,
      vibrance: values['vibrance'] ?? 0,
      denoise: math.max(0, values['denoise'] ?? 0),
      ambiance: values['lightSense'] ?? 0,
      vignette: values['vignette'] ?? 0,
      grain: math.max(0, values['grain'] ?? 0),
    );
  }

  /// 局部锚点的细节类像素参数（与整体面板同一映射与管线，真算法）。
  ImageEditorDetailSpec _buildLocalAnchorDetailSpec(
    Map<String, double> values,
  ) => _detailSpecFromValues(values);

  List<double> _buildProBaseColorMatrix() =>
      _buildBaseColorMatrixFromValues(_proBaseValues);

  /// 整体面板的细节/分区/颗粒像素参数（与 CPU 预览、烘焙同一映射）。
  ImageEditorDetailSpec _buildProBaseDetailSpec() =>
      _detailSpecFromValues(_proBaseValues);

  List<double> _buildCombinedProColorMatrix({
    bool useBwLevelsSessionBaseline = false,
    bool includeWhiteBalance = true,
  }) {
    // 整体面板（base）不再进组合矩阵：编辑会话由 CPU 组合预览层承载，
    // 烘焙走 applyBaseAdjustments，同一管线同源。
    var matrix = _identityColorMatrix();
    if (includeWhiteBalance && _hasWhiteBalanceAdjustments) {
      matrix = _multiplyColorMatrices(_buildWhiteBalanceColorMatrix(), matrix);
    }
    // HSL 分带不再进组合矩阵：编辑会话由 CPU 分带预览层承载
    // （_buildHslSessionImageLayer），导出走 applyHslBands，同一算法同源。
    if (_hasBwLevelsAdjustments || useBwLevelsSessionBaseline) {
      final white = useBwLevelsSessionBaseline
          ? _bwSessionBaselineWhiteLevel
          : _bwWhiteLevel;
      final black = useBwLevelsSessionBaseline
          ? _bwSessionBaselineBlackLevel
          : _bwBlackLevel;
      matrix = _multiplyColorMatrices(
        _bwLevelsMatrix(whiteLevel: white, blackLevel: black),
        matrix,
      );
    }
    return matrix;
  }

  ImageEditorFilterPreset? get _selectedFilterPreset {
    final id = _selectedFilterPresetId;
    if (id == null || id.isEmpty) return null;
    for (final preset in _filterPresets) {
      if (preset.id == id) return preset;
    }
    return null;
  }

  bool get _hasFilterAdjustments {
    final preset = _selectedFilterPreset;
    if (preset == null) return false;
    final strength = (_filterStrengthByPresetId[preset.id] ?? _filterIntensity)
        .clamp(0, 100)
        .toDouble();
    return strength > 0.001;
  }

  List<double> _buildFilterColorMatrix(
    ImageEditorFilterPreset preset,
    double strength,
  ) => buildImageEditorFilterColorMatrix(preset, strength);

  /// 滤镜的细节类像素参数（与整体面板同一映射，滤镜/面板同源）。
  ImageEditorDetailSpec _buildFilterDetailSpec(
    ImageEditorFilterPreset preset,
    double strength,
  ) => _detailSpecFromValues(
    buildImageEditorFilterDetailValues(preset, strength),
  );

  Widget _wrapWithFilterAdjustments(Widget imageWidget) {
    final preset = _selectedFilterPreset;
    if (preset == null) return imageWidget;
    final strength = (_filterStrengthByPresetId[preset.id] ?? _filterIntensity)
        .clamp(0, 100);
    if (strength <= 0.001) return imageWidget;
    // 含细节参数的滤镜：CPU 预览与烘焙同一管线（矩阵+细节逐像素）接管，
    // 纯色彩滤镜继续走 GPU 矩阵。
    final cpuPreview = _filterPreviewImage;
    if (cpuPreview != null && imageEditorFilterHasDetailParams(preset)) {
      return Center(
        child: RawImage(
          image: cpuPreview,
          fit: BoxFit.contain,
          filterQuality: FilterQuality.medium,
        ),
      );
    }
    return ColorFiltered(
      colorFilter: ColorFilter.matrix(
        _buildFilterColorMatrix(preset, strength.toDouble()),
      ),
      child: imageWidget,
    );
  }

  Widget _wrapWithProAdjustments(Widget imageWidget) {
    // HSL 分带与整体面板由各自 CPU 预览层承载（与烘焙同管线），不进矩阵。
    if (!_hasBwLevelsAdjustments && !_hasWhiteBalanceAdjustments) {
      return imageWidget;
    }
    final useBwBaseline = _isComparingSessionBaseline && _isEditingBwLevels;
    // 白平衡编辑中长按对比原图时不应用 wb 矩阵。
    final includeWhiteBalance =
        !(_isComparingSessionBaseline && _isEditingWhiteBalance);
    return ColorFiltered(
      colorFilter: ColorFilter.matrix(
        _buildCombinedProColorMatrix(
          useBwLevelsSessionBaseline: useBwBaseline,
          includeWhiteBalance: includeWhiteBalance,
        ),
      ),
      child: imageWidget,
    );
  }
}
