part of 'image_editor_page.dart';

extension _ImageEditorPageFilterLogic on _ImageEditorPageState {
  Future<void> _initFilterConfig() async {
    if (mounted) {
      _setEditorState(() {
        _filterCatalogLoading = true;
        _filterCatalogLoadFailed = false;
      });
    }
    try {
      final config = await _filterRepository.loadConfig();
      if (!mounted) return;
      _setEditorState(() {
        _filterConfig = config;
        _filterCatalogLoading = false;
      });
      _observability.recordPageState(
        pageName: _ImageEditorPageState._kPageName,
        phase: 'filter_catalog_ready',
        surface: _ImageEditorPageState._kSurfaceId,
        itemCount: config.presets.length,
      );
      await _rebuildFilterData();
    } catch (error) {
      if (!mounted) return;
      _setEditorState(() {
        _filterCatalogLoading = false;
        _filterCatalogLoadFailed = true;
      });
      _observability.recordPageState(
        pageName: _ImageEditorPageState._kPageName,
        phase: 'filter_catalog_failure',
        surface: _ImageEditorPageState._kSurfaceId,
        error: error,
      );
    }
  }

  Future<void> _rebuildFilterData() async {
    final config = _filterConfig;
    if (config == null) return;
    final recentIds = await _filterRepository.loadRecentPresetIds();
    final usageCounts = await _filterRepository.loadUsageCounts();
    final features = await _resolveFilterImageFeatures();
    if (!mounted) return;

    final presetById = <String, ImageEditorFilterPreset>{
      for (final preset in config.presets.where((entry) => entry.enabled))
        preset.id: preset,
    };
    _filterUsageCountByPresetId
      ..clear()
      ..addAll(usageCounts);
    final filteredCategories =
        config.categories
            .where(
              (entry) =>
                  entry.enabled &&
                  entry.id != 'recommended' &&
                  entry.id != 'common',
            )
            .toList(growable: false)
          ..sort((a, b) => a.sort.compareTo(b.sort));

    final commonIds = _resolveCommonPresetIds(
      presetById: presetById,
      recentIds: recentIds,
      usageCounts: usageCounts,
      maxCount: 3,
    );
    final recommendedIds = _resolveSmartRecommendedPresetIds(
      presets: presetById.values.toList(growable: false),
      features: features,
      excludedPresetIds: commonIds.toSet(),
      fallbackPresetIds: config.recommendedFallbackPresetIds,
      maxCount: 10,
    );

    final builtCategories = <ImageEditorFilterCategory>[];
    final builtPresets = <ImageEditorFilterPreset>[];
    final builtAnchors = <int>[];

    void appendCategory(
      ImageEditorFilterCategory category,
      List<ImageEditorFilterPreset> presets, {
      bool allowEmpty = false,
    }) {
      if (presets.isEmpty && !allowEmpty) return;
      builtCategories.add(category);
      builtAnchors.add(builtPresets.length);
      builtPresets.addAll(presets);
    }

    appendCategory(
      const ImageEditorFilterCategory(
        id: 'common',
        label: MediaText.imageEditorFilterFrequent,
        sort: -10,
        enabled: true,
      ),
      [
        for (final id in commonIds)
          if (presetById[id] != null) presetById[id]!,
      ],
      allowEmpty: true,
    );
    appendCategory(
      const ImageEditorFilterCategory(
        id: 'recommended',
        label: MediaText.imageEditorFilterRecommended,
        sort: 0,
        enabled: true,
      ),
      [
        for (final id in recommendedIds)
          if (presetById[id] != null) presetById[id]!,
      ],
      allowEmpty: true,
    );
    for (final category in filteredCategories) {
      final categoryPresets =
          presetById.values
              .where(
                (entry) =>
                    entry.categoryId == category.id &&
                    !commonIds.contains(entry.id) &&
                    !recommendedIds.contains(entry.id),
              )
              .toList(growable: false)
            ..sort((a, b) => a.sort.compareTo(b.sort));
      appendCategory(category, categoryPresets);
    }
    if (builtCategories.isEmpty) {
      builtAnchors.clear();
    }

    final currentPresetId = _selectedFilterPresetId;
    final fallbackIndex = _filterTemplateIndex
        .clamp(0, math.max(0, builtPresets.length - 1))
        .toInt();
    final fallbackPreset = builtPresets.isEmpty
        ? null
        : builtPresets[fallbackIndex];
    final currentStrength = currentPresetId == null
        ? 100.0
        : (_filterStrengthByPresetId[currentPresetId] ??
                  (fallbackPreset?.defaultStrength ?? 100))
              .toDouble();

    _setEditorState(() {
      _filterCategories = builtCategories;
      _filterPresets = builtPresets;
      _filterCategoryAnchors = builtAnchors;
      _selectedFilterPresetId = currentPresetId;
      if (currentPresetId == null || builtPresets.isEmpty) {
        _filterTemplateIndex = -1;
      } else {
        final foundIndex = builtPresets.indexWhere(
          (entry) => entry.id == currentPresetId,
        );
        _filterTemplateIndex = foundIndex < 0
            ? 0
            : foundIndex.clamp(0, builtPresets.length - 1);
      }
      _filterIntensity = currentStrength.clamp(0, 100);
      _syncFilterCategoryFromTemplateIndex(
        _filterTemplateIndex < 0 ? 0 : _filterTemplateIndex,
      );
    });
  }

  List<String> _resolveCommonPresetIds({
    required Map<String, ImageEditorFilterPreset> presetById,
    required List<String> recentIds,
    required Map<String, int> usageCounts,
    required int maxCount,
  }) {
    final pairs =
        usageCounts.entries
            .where(
              (entry) => entry.value > 0 && presetById.containsKey(entry.key),
            )
            .toList(growable: false)
          ..sort((a, b) {
            final usage = b.value.compareTo(a.value);
            if (usage != 0) return usage;
            final ai = recentIds.indexOf(a.key);
            final bi = recentIds.indexOf(b.key);
            if (ai < 0 && bi < 0) return 0;
            if (ai < 0) return 1;
            if (bi < 0) return -1;
            return ai.compareTo(bi);
          });
    final ids = <String>[...pairs.map((entry) => entry.key)];
    if (ids.length < maxCount) {
      for (final id in recentIds) {
        if (presetById.containsKey(id) && !ids.contains(id)) {
          ids.add(id);
        }
        if (ids.length >= maxCount) break;
      }
    }
    return ids.take(maxCount).toList(growable: false);
  }

  List<String> _resolveSmartRecommendedPresetIds({
    required List<ImageEditorFilterPreset> presets,
    required ImageEditorFilterImageFeatures features,
    required Set<String> excludedPresetIds,
    required List<String> fallbackPresetIds,
    required int maxCount,
  }) {
    return _filterRecommender.recommendPresetIds(
      presets: presets,
      features: features,
      excludedPresetIds: excludedPresetIds,
      fallbackPresetIds: fallbackPresetIds,
      maxCount: maxCount,
    );
  }

  Future<ImageEditorFilterImageFeatures> _resolveFilterImageFeatures() async {
    if (_filterImageFeatures != null &&
        _filterImageFeaturesPath == _currentPath) {
      return _filterImageFeatures!;
    }
    final features = await _analyzeImageFeatures(_currentPath);
    _filterImageFeatures = features;
    _filterImageFeaturesPath = _currentPath;
    return features;
  }

  Future<ImageEditorFilterImageFeatures> _analyzeImageFeatures(
    String path,
  ) async {
    if (path.isEmpty) return const ImageEditorFilterImageFeatures();
    try {
      final bytes = await _loadImageBytes(path);
      if (bytes.isEmpty) return const ImageEditorFilterImageFeatures();
      return _filterFeatureExtractor.extractFromBytes(bytes);
    } catch (_) {
      return const ImageEditorFilterImageFeatures();
    }
  }

  void _prepareFilterSnapshot() {
    _filterSnapshotCategoryIndex = _filterCategoryIndex;
    _filterSnapshotTemplateIndex = _filterTemplateIndex;
    _filterSnapshotIntensity = _filterIntensity;
    _filterSnapshotPresetId = _selectedFilterPresetId;
    _filterSnapshotStrengthByPresetId = Map<String, double>.from(
      _filterStrengthByPresetId,
    );
    _clearFilterPreviewCache();
  }

  void _cancelFilterAndExit() {
    _setEditorState(() {
      _filterCategoryIndex = _filterSnapshotCategoryIndex;
      _filterTemplateIndex = _filterSnapshotTemplateIndex;
      _filterIntensity = _filterSnapshotIntensity;
      _selectedFilterPresetId = _filterSnapshotPresetId;
      _filterStrengthByPresetId
        ..clear()
        ..addAll(_filterSnapshotStrengthByPresetId);
      _selectedToolIndex = null;
    });
    _disposeFilterPreviewResources();
  }

  void _clearFilterPreviewCache() {
    _filterTemplatePreviewBytes.clear();
    _filterTemplatePreviewLoading.clear();
    _filterTemplatePreviewQueued.clear();
    _filterTemplatePreviewFailed.clear();
    _filterVisibleIndices.clear();
    _filterPreviewQueue.clear();
  }

  void _syncFilterCategoryFromTemplateIndex(int templateIndex) {
    if (_filterCategoryAnchors.isEmpty) {
      _filterCategoryIndex = 0;
      return;
    }
    var categoryIndex = 0;
    for (var i = 0; i < _filterCategoryAnchors.length; i++) {
      if (templateIndex >= _filterCategoryAnchors[i]) {
        categoryIndex = i;
      } else {
        break;
      }
    }
    _filterCategoryIndex = categoryIndex;
  }

  void _onFilterCategoryChanged(int categoryIndex) {
    if (_filterCategories.isEmpty) return;
    final next = categoryIndex.clamp(0, _filterCategories.length - 1);
    if (next == _filterCategoryIndex) return;
    _setEditorState(() => _filterCategoryIndex = next);
  }

  void _onFilterTemplateChanged(int index) {
    if (_filterPresets.isEmpty) return;
    final safeIndex = index.clamp(0, _filterPresets.length - 1);
    final preset = _filterPresets[safeIndex];
    _setEditorState(() {
      _selectedFilterPresetId = preset.id;
      _filterTemplateIndex = safeIndex;
      _filterIntensity =
          (_filterStrengthByPresetId[preset.id] ?? preset.defaultStrength)
              .clamp(0, 100)
              .toDouble();
      _syncFilterCategoryFromTemplateIndex(safeIndex);
    });
    _scheduleFilterPreviewRecompute();
  }

  void _onFilterIntensityChanged(double value) {
    final clamped = value.clamp(0.0, 100.0).toDouble();
    final presetId = _selectedFilterPresetId;
    if (presetId == null || presetId.isEmpty) {
      if (_filterPresets.isEmpty) return;
      final fallback =
          _filterPresets[_filterTemplateIndex.clamp(
            0,
            _filterPresets.length - 1,
          )];
      _selectedFilterPresetId = fallback.id;
    }
    _setEditorState(() {
      _filterIntensity = clamped;
      _filterStrengthByPresetId[_selectedFilterPresetId!] = clamped;
    });
    _scheduleFilterPreviewRecompute();
  }

  void _onFilterRemove() {
    _setEditorState(() {
      _selectedFilterPresetId = null;
      _filterTemplateIndex = -1;
      _filterIntensity = 100;
    });
    _scheduleFilterPreviewRecompute();
  }

  void _ensureFilterSelectionForEditing() {
    if (_selectedFilterPresetId != null || _filterPresets.isEmpty) return;
    final preset = _filterPresets.first;
    _selectedFilterPresetId = preset.id;
    _filterTemplateIndex = 0;
    _filterIntensity =
        (_filterStrengthByPresetId[preset.id] ?? preset.defaultStrength)
            .clamp(0, 100)
            .toDouble();
    _syncFilterCategoryFromTemplateIndex(0);
  }

  void _onFilterVisibleRangeChanged(int start, int end) {
    if (_filterPresets.isEmpty) return;
    final safeStart = start.clamp(0, _filterPresets.length - 1);
    final safeEnd = end.clamp(safeStart, _filterPresets.length - 1);
    _filterVisibleIndices
      ..clear()
      ..addAll(
        List<int>.generate(safeEnd - safeStart + 1, (i) => safeStart + i),
      );
    for (var i = safeStart; i <= safeEnd; i++) {
      if (_filterTemplatePreviewBytes.containsKey(i) ||
          _filterTemplatePreviewLoading.contains(i) ||
          _filterTemplatePreviewQueued.contains(i) ||
          _filterTemplatePreviewFailed.contains(i)) {
        continue;
      }
      _filterTemplatePreviewQueued.add(i);
      _filterPreviewQueue.add(i);
    }
    _processFilterPreviewQueue();
  }

  Future<void> _processFilterPreviewQueue() async {
    if (_processingFilterPreviewQueue) return;
    _processingFilterPreviewQueue = true;
    while (_filterPreviewQueue.isNotEmpty) {
      final index = _filterPreviewQueue.removeAt(0);
      _filterTemplatePreviewQueued.remove(index);
      if (!_filterVisibleIndices.contains(index) ||
          _filterTemplatePreviewBytes.containsKey(index) ||
          _filterTemplatePreviewFailed.contains(index)) {
        continue;
      }
      _setEditorState(() => _filterTemplatePreviewLoading.add(index));
      final bytes = await _buildFilterPreviewBytes(index);
      if (!mounted) break;
      _setEditorState(() {
        _filterTemplatePreviewLoading.remove(index);
        if (bytes != null) {
          _filterTemplatePreviewBytes[index] = bytes;
        } else {
          _filterTemplatePreviewFailed.add(index);
        }
      });
    }
    _processingFilterPreviewQueue = false;
  }

  Future<Uint8List?> _buildFilterPreviewBytes(int presetIndex) async {
    if (_currentPath.isEmpty ||
        presetIndex < 0 ||
        presetIndex >= _filterPresets.length) {
      return null;
    }
    final preset = _filterPresets[presetIndex];
    try {
      final bytes = await _loadImageBytes(_currentPath);
      if (bytes.isEmpty) return null;
      final codec = await ui.instantiateImageCodec(bytes);
      final frame = await codec.getNextFrame();
      final image = frame.image;
      const previewTarget = 220;
      final ratio = image.width / image.height;
      final width = ratio >= 1
          ? previewTarget
          : math.max(1, (previewTarget * ratio).round());
      final height = ratio >= 1
          ? math.max(1, (previewTarget / ratio).round())
          : previewTarget;
      final recorder = ui.PictureRecorder();
      final canvas = Canvas(recorder);
      final srcRect = Rect.fromLTWH(
        0,
        0,
        image.width.toDouble(),
        image.height.toDouble(),
      );
      final dstRect = Rect.fromLTWH(0, 0, width.toDouble(), height.toDouble());
      final paint = Paint()
        ..filterQuality = FilterQuality.low
        ..colorFilter = ColorFilter.matrix(
          _buildFilterColorMatrix(
            preset,
            _filterStrengthByPresetId[preset.id] ?? preset.defaultStrength,
          ),
        );
      canvas.drawImageRect(image, srcRect, dstRect, paint);
      final preview = await recorder.endRecording().toImage(width, height);
      final data = await preview.toByteData(format: ui.ImageByteFormat.png);
      return data?.buffer.asUint8List();
    } catch (_) {
      return null;
    }
  }

  // ---- 滤镜 CPU 预览 session（与烘焙同一管线，GWT-009）----
  //
  // 目录小缩略图（上方 _buildFilterPreviewBytes）保留纯矩阵轻量近似（仅供
  // 挑选参考）；主预览在选中滤镜含细节类参数时由以下 CPU session 接管，
  // 矩阵 + 细节逐像素与确认烘焙 applyBaseAdjustments 同源不跳变。

  void _disposeFilterPreviewResources() {
    _filterPreviewBase?.dispose();
    _filterPreviewBase = null;
    _filterPreviewBaseRgba = null;
    _filterPreviewImage?.dispose();
    _filterPreviewImage = null;
    _filterPreviewDirty = false;
    _filterPreviewComputing = false;
  }

  /// 进入滤镜工具：异步准备降采样底图供 CPU 滤镜预览。
  void _prepareFilterPreviewSession() {
    _disposeFilterPreviewResources();
    unawaited(_loadFilterPreviewBase());
  }

  Future<void> _loadFilterPreviewBase() async {
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
        _filterPreviewBase = image;
        _filterPreviewBaseRgba = data?.buffer.asUint8List();
      });
      _scheduleFilterPreviewRecompute();
    } catch (error) {
      _observability.recordPageState(
        pageName: _ImageEditorPageState._kPageName,
        phase: 'failure',
        surface: _ImageEditorPageState._kSurfaceId,
        copyKey: 'filter_preview_load',
        error: error is Exception ? error : null,
      );
    }
  }

  void _scheduleFilterPreviewRecompute() {
    if (_filterPreviewComputing) {
      _filterPreviewDirty = true;
      return;
    }
    _filterPreviewDirty = false;
    _filterPreviewComputing = true;
    unawaited(_recomputeFilterPreview());
  }

  Future<void> _recomputeFilterPreview() async {
    try {
      final base = _filterPreviewBase;
      final baseRgba = _filterPreviewBaseRgba;
      if (base == null || baseRgba == null || !mounted) {
        return;
      }
      final preset = _selectedFilterPreset;
      final strength =
          (preset == null
                  ? 0
                  : (_filterStrengthByPresetId[preset.id] ?? _filterIntensity))
              .clamp(0, 100)
              .toDouble();
      // 无滤镜或滤镜不含细节参数：交回 GPU 矩阵路径。
      if (preset == null ||
          strength <= 0.001 ||
          !imageEditorFilterHasDetailParams(preset)) {
        final old = _filterPreviewImage;
        if (old != null) {
          _setEditorState(() => _filterPreviewImage = null);
          old.dispose();
        }
        return;
      }
      final pixels = Uint8List.fromList(baseRgba);
      ImageEditorExportEngine.applyColorMatrixToRgbaPixels(
        pixels,
        _buildFilterColorMatrix(preset, strength),
      );
      ImageEditorExportEngine.applyDetailAdjustmentsToRgbaPixels(
        pixels,
        base.width,
        base.height,
        _buildFilterDetailSpec(preset, strength),
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
      final old = _filterPreviewImage;
      _setEditorState(() => _filterPreviewImage = frame.image);
      if (!identical(old, frame.image)) {
        old?.dispose();
      }
    } finally {
      _filterPreviewComputing = false;
      if (_filterPreviewDirty && mounted) {
        _scheduleFilterPreviewRecompute();
      }
    }
  }
}
