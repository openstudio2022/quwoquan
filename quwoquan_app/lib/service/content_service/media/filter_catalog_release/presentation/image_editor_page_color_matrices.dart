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

  List<double> _brightnessMatrix(double value) {
    final offset = value / 100 * 255;
    return <double>[
      1,
      0,
      0,
      0,
      offset,
      0,
      1,
      0,
      0,
      offset,
      0,
      0,
      1,
      0,
      offset,
      0,
      0,
      0,
      1,
      0,
    ];
  }

  List<double> _contrastMatrix(double value) {
    final factor = (1 + value / 100).clamp(0.0, 3.0);
    final translate = 128 * (1 - factor);
    return <double>[
      factor,
      0,
      0,
      0,
      translate,
      0,
      factor,
      0,
      0,
      translate,
      0,
      0,
      factor,
      0,
      translate,
      0,
      0,
      0,
      1,
      0,
    ];
  }

  List<double> _saturationMatrix(double value) {
    final s = (1 + value / 100).clamp(0.0, 3.0);
    const lR = 0.2126;
    const lG = 0.7152;
    const lB = 0.0722;
    return <double>[
      lR * (1 - s) + s,
      lG * (1 - s),
      lB * (1 - s),
      0,
      0,
      lR * (1 - s),
      lG * (1 - s) + s,
      lB * (1 - s),
      0,
      0,
      lR * (1 - s),
      lG * (1 - s),
      lB * (1 - s) + s,
      0,
      0,
      0,
      0,
      0,
      1,
      0,
    ];
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

  List<double> _exposureMatrix(double value) {
    final ev = (value / 100).clamp(-1.5, 1.5);
    final factor = math.pow(2, ev).toDouble();
    return <double>[
      factor,
      0,
      0,
      0,
      0,
      0,
      factor,
      0,
      0,
      0,
      0,
      0,
      factor,
      0,
      0,
      0,
      0,
      0,
      1,
      0,
    ];
  }

  List<double> _hueRotationMatrix(double value) {
    final angle = (value / 100) * (math.pi / 2);
    final cosA = math.cos(angle);
    final sinA = math.sin(angle);
    const lR = 0.213;
    const lG = 0.715;
    const lB = 0.072;
    return <double>[
      lR + cosA * (1 - lR) + sinA * (-lR),
      lG + cosA * (-lG) + sinA * (-lG),
      lB + cosA * (-lB) + sinA * (1 - lB),
      0,
      0,
      lR + cosA * (-lR) + sinA * 0.143,
      lG + cosA * (1 - lG) + sinA * 0.140,
      lB + cosA * (-lB) + sinA * (-0.283),
      0,
      0,
      lR + cosA * (-lR) + sinA * (-(1 - lR)),
      lG + cosA * (-lG) + sinA * lG,
      lB + cosA * (1 - lB) + sinA * lB,
      0,
      0,
      0,
      0,
      0,
      1,
      0,
    ];
  }

  List<double> _buildBaseColorMatrixFromValues(Map<String, double> values) {
    final lightSense = values['lightSense'] ?? 0;
    final brightness = values['brightness'] ?? 0;
    final exposure = values['exposure'] ?? 0;
    final contrast = values['contrast'] ?? 0;
    final saturation = values['saturation'] ?? 0;
    final vibrance = values['vibrance'] ?? 0;
    final texture = values['texture'] ?? 0;
    final sharpen = values['sharpen'] ?? 0;
    final structure = values['structure'] ?? 0;
    final highlights = values['highlight'] ?? 0;
    final shadows = values['shadow'] ?? 0;
    final temperature = values['temperature'] ?? 0;
    final tint = values['tint'] ?? 0;
    final grain = values['grain'] ?? 0;
    final fade = values['fade'] ?? 0;
    final lightSenseBrightness = lightSense * 0.09;
    final lightSenseContrast = lightSense * 0.18;
    final vibranceSaturation = vibrance * 0.65;
    final textureContrast = texture * 0.14;
    final sharpenContrast = sharpen * 0.12;
    final structureContrast = structure * 0.24;
    final highlightBrightness = highlights * 0.20;
    final shadowBrightness = shadows * 0.25;
    final grainContrast = grain * 0.10;
    final fadeLift = fade * 0.22;

    var matrix = _identityColorMatrix();
    matrix = _multiplyColorMatrices(_exposureMatrix(exposure), matrix);
    matrix = _multiplyColorMatrices(
      _brightnessMatrix(
        brightness +
            lightSenseBrightness +
            highlightBrightness +
            shadowBrightness +
            fadeLift,
      ),
      matrix,
    );
    matrix = _multiplyColorMatrices(
      _contrastMatrix(
        contrast +
            lightSenseContrast +
            textureContrast +
            sharpenContrast +
            structureContrast +
            grainContrast +
            highlights * 0.10 -
            shadows * 0.10 -
            fade * 0.30,
      ),
      matrix,
    );
    matrix = _multiplyColorMatrices(
      _saturationMatrix(saturation + vibranceSaturation - fade * 0.18),
      matrix,
    );
    matrix = _multiplyColorMatrices(_temperatureMatrix(temperature), matrix);
    matrix = _multiplyColorMatrices(_tintMatrix(tint), matrix);
    return matrix;
  }

  List<double> _buildProBaseColorMatrix() =>
      _buildBaseColorMatrixFromValues(_proBaseValues);

  List<double> _buildProHslColorMatrix(
    Map<String, Map<String, double>> values,
  ) {
    if (values.isEmpty) {
      return _identityColorMatrix();
    }
    final count = values.length;
    var sumHue = 0.0;
    var sumSaturation = 0.0;
    var sumLuminance = 0.0;
    for (final channelValues in values.values) {
      sumHue += channelValues[kHslAxisHue] ?? 0;
      sumSaturation += channelValues[kHslAxisSaturation] ?? 0;
      sumLuminance += channelValues[kHslAxisLuminance] ?? 0;
    }
    final avgHue = sumHue / count;
    final avgSaturation = sumSaturation / count;
    final avgLuminance = sumLuminance / count;
    var matrix = _identityColorMatrix();
    matrix = _multiplyColorMatrices(_hueRotationMatrix(avgHue), matrix);
    matrix = _multiplyColorMatrices(_saturationMatrix(avgSaturation), matrix);
    matrix = _multiplyColorMatrices(_brightnessMatrix(avgLuminance), matrix);
    return matrix;
  }

  List<double> _buildCombinedProColorMatrix({
    bool useHslSessionBaseline = false,
    bool useBwLevelsSessionBaseline = false,
    bool includeWhiteBalance = true,
  }) {
    var matrix = _identityColorMatrix();
    if (_hasProBaseAdjustments) {
      matrix = _multiplyColorMatrices(_buildProBaseColorMatrix(), matrix);
    }
    if (includeWhiteBalance && _hasWhiteBalanceAdjustments) {
      matrix = _multiplyColorMatrices(_buildWhiteBalanceColorMatrix(), matrix);
    }
    final hslSource = useHslSessionBaseline
        ? _hslSessionBaselineValues
        : _proHslValues;
    final hasHsl = hslSource.values.any(
      (channelValues) =>
          channelValues.values.any((value) => value.abs() > 0.001),
    );
    if (hasHsl) {
      matrix = _multiplyColorMatrices(
        _buildProHslColorMatrix(hslSource),
        matrix,
      );
    }
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

  Widget _wrapWithFilterAdjustments(Widget imageWidget) {
    final preset = _selectedFilterPreset;
    if (preset == null) return imageWidget;
    final strength = (_filterStrengthByPresetId[preset.id] ?? _filterIntensity)
        .clamp(0, 100);
    if (strength <= 0.001) return imageWidget;
    return ColorFiltered(
      colorFilter: ColorFilter.matrix(
        _buildFilterColorMatrix(preset, strength.toDouble()),
      ),
      child: imageWidget,
    );
  }

  Widget _wrapWithProAdjustments(Widget imageWidget) {
    if (!_hasProBaseAdjustments &&
        !_hasProHslAdjustments &&
        !_hasBwLevelsAdjustments &&
        !_hasWhiteBalanceAdjustments) {
      return imageWidget;
    }
    final useBaseline = _isComparingSessionBaseline && _isEditingHsl;
    final useBwBaseline = _isComparingSessionBaseline && _isEditingBwLevels;
    // 白平衡编辑中长按对比原图时不应用 wb 矩阵。
    final includeWhiteBalance =
        !(_isComparingSessionBaseline && _isEditingWhiteBalance);
    return ColorFiltered(
      colorFilter: ColorFilter.matrix(
        _buildCombinedProColorMatrix(
          useHslSessionBaseline: useBaseline,
          useBwLevelsSessionBaseline: useBwBaseline,
          includeWhiteBalance: includeWhiteBalance,
        ),
      ),
      child: imageWidget,
    );
  }
}
