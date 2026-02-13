import 'dart:io';
import 'dart:math' as math;
import 'dart:async';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:path_provider/path_provider.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/components/media/image/editor/models/image_editor_step.dart';
import 'package:quwoquan_app/components/media/image/editor/top_bar/image_editor_top_bar.dart';
import 'package:quwoquan_app/components/media/image/editor/bottom_bar/image_editor_bottom_bar.dart';
import 'package:quwoquan_app/components/media/image/editor/icons/image_editor_semantic_icon.dart';
import 'package:quwoquan_app/components/media/image/editor/panels/image_editor_curve_overlay_bar.dart';
import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_models.dart';
import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_feature_extractor.dart';
import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_recommendation_models.dart';
import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_recommender.dart';
import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_repository.dart';
import 'package:quwoquan_app/components/media/image/editor/panels/hsl/image_editor_hsl_models.dart';
import 'package:quwoquan_app/components/media/image/editor/panels/local/image_editor_local_models.dart';
import 'package:quwoquan_app/components/media/image/editor/panels/image_editor_operation_panel.dart';
import 'package:quwoquan_app/components/media/image/editor/panels/image_editor_rotate_overlay.dart';
import 'package:quwoquan_app/components/media/image/editor/shared/editor_session_ops_strip.dart';
import 'package:quwoquan_app/components/media/image/editor/tool_list/image_editor_tool_constants.dart';
import 'package:quwoquan_app/components/media/image/editor/tool_list/image_editor_pro_tool_entries.dart';

/// 图片编辑器页面（三段式布局：顶栏、中部图片、底栏工具）
///
/// 路由：/create/edit-image?path=...&source=...&index=...&total=...
/// 返回：context.pop(editedPath) 或 context.pop() 取消
///
/// 嵌入式使用：传入 [onBack]/[onDone] 时不再 pop，由回调处理（用于创作页内全屏编辑、底部栏隐退）
class ImageEditorPage extends ConsumerStatefulWidget {
  const ImageEditorPage({
    super.key,
    required this.initialPath,
    required this.source,
    this.index = 0,
    this.total = 1,
    this.imagePaths,
    this.onBack,
    this.onDone,
  });

  final String initialPath;
  final String source;
  final int index;
  final int total;
  /// 多图时传入全部路径，用于大图左右滑动与缩略图联动
  final List<String>? imagePaths;
  /// 嵌入式时使用：返回/取消时调用，不执行 context.pop
  final VoidCallback? onBack;
  /// 嵌入式时使用：完成时传入结果（String 或 Map），不执行 context.pop
  final void Function(Object? result)? onDone;

  @override
  ConsumerState<ImageEditorPage> createState() => _ImageEditorPageState();
}

class _ImageEditorPageState extends ConsumerState<ImageEditorPage> {
  static const int _kLocalAnchorMaxCount = 10;
  List<String> _paths = const [];

  int _currentIndex = 0;
  PageController? _pageController;
  ScrollController? _thumbScrollController;

  @override
  void initState() {
    super.initState();
    _syncPaths(resetIndex: true);
    _loadImageAspectRatio(_currentPath);
    _initFilterConfig();
  }

  @override
  void didUpdateWidget(ImageEditorPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.initialPath != widget.initialPath ||
        oldWidget.imagePaths != widget.imagePaths ||
        oldWidget.index != widget.index) {
      _syncPaths(resetIndex: true);
    }
  }

  @override
  void dispose() {
    _pageController?.dispose();
    _thumbScrollController?.dispose();
    _proToolScrollController.dispose();
    _cropRatioScrollController.dispose();
    _filterTemplateScrollController.dispose();
    super.dispose();
  }

  String get _currentPath {
    if (_paths.isEmpty) return widget.initialPath;
    final i = _currentIndex.clamp(0, _paths.length - 1);
    return _paths[i];
  }

  bool get _isMultiImage => _paths.length > 1;

  void _syncPaths({required bool resetIndex}) {
    final source = widget.imagePaths?.isNotEmpty == true
        ? widget.imagePaths!
        : (widget.initialPath.isNotEmpty ? [widget.initialPath] : <String>[]);
    _paths = List<String>.of(source, growable: true);
    if (_paths.isEmpty) {
      _currentIndex = 0;
    } else if (resetIndex) {
      _currentIndex =
          widget.index.clamp(0, (_paths.length - 1).clamp(0, 0x7fffffff));
    } else {
      _currentIndex =
          _currentIndex.clamp(0, (_paths.length - 1).clamp(0, 0x7fffffff));
    }
    if (_paths.length > 1) {
      _pageController ??= PageController(initialPage: _currentIndex);
      _thumbScrollController ??= ScrollController();
    } else {
      _pageController?.dispose();
      _thumbScrollController?.dispose();
      _pageController = null;
      _thumbScrollController = null;
    }
  }

  Future<void> _initFilterConfig() async {
    final config = await _filterRepository.loadConfig();
    if (!mounted) return;
    setState(() {
      _filterConfig = config;
    });
    _rebuildFilterData();
    await _filterRepository.scheduleUpdateCheckPlaceholder();
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
    final filteredCategories = config.categories
        .where((entry) =>
            entry.enabled &&
            entry.id != 'recommended' &&
            entry.id != 'common')
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
        label: UITextConstants.imageEditorFilterFrequent,
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
        label: UITextConstants.imageEditorFilterRecommended,
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
      final categoryPresets = presetById.values
          .where((entry) =>
              entry.categoryId == category.id &&
              !commonIds.contains(entry.id) &&
              !recommendedIds.contains(entry.id))
          .toList(growable: false)
        ..sort((a, b) => a.sort.compareTo(b.sort));
      appendCategory(category, categoryPresets);
    }
    if (builtCategories.isEmpty) {
      builtAnchors.clear();
    }

    final currentPresetId = _selectedFilterPresetId;
    final fallbackIndex = _filterTemplateIndex.clamp(
      0,
      math.max(0, builtPresets.length - 1),
    ).toInt();
    final fallbackPreset =
        builtPresets.isEmpty ? null : builtPresets[fallbackIndex];
    final currentStrength = currentPresetId == null
        ? 100.0
        : (_filterStrengthByPresetId[currentPresetId] ??
                (fallbackPreset?.defaultStrength ?? 100))
            .toDouble();

    setState(() {
      _filterCategories = builtCategories;
      _filterPresets = builtPresets;
      _filterCategoryAnchors = builtAnchors;
      _selectedFilterPresetId = currentPresetId;
      if (currentPresetId == null || builtPresets.isEmpty) {
        _filterTemplateIndex = -1;
      } else {
        final foundIndex =
            builtPresets.indexWhere((entry) => entry.id == currentPresetId);
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
    final pairs = usageCounts.entries
        .where((entry) => entry.value > 0 && presetById.containsKey(entry.key))
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
    final ids = <String>[
      ...pairs.map((entry) => entry.key),
    ];
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
    if (_filterImageFeatures != null && _filterImageFeaturesPath == _currentPath) {
      return _filterImageFeatures!;
    }
    final features = await _analyzeImageFeatures(_currentPath);
    _filterImageFeatures = features;
    _filterImageFeaturesPath = _currentPath;
    return features;
  }

  Future<ImageEditorFilterImageFeatures> _analyzeImageFeatures(String path) async {
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
    setState(() {
      _filterCategoryIndex = _filterSnapshotCategoryIndex;
      _filterTemplateIndex = _filterSnapshotTemplateIndex;
      _filterIntensity = _filterSnapshotIntensity;
      _selectedFilterPresetId = _filterSnapshotPresetId;
      _filterStrengthByPresetId
        ..clear()
        ..addAll(_filterSnapshotStrengthByPresetId);
      _selectedToolIndex = null;
    });
  }

  void _clearFilterPreviewCache() {
    _filterTemplatePreviewBytes.clear();
    _filterTemplatePreviewLoading.clear();
    _filterTemplatePreviewQueued.clear();
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
    setState(() => _filterCategoryIndex = next);
  }

  void _onFilterTemplateChanged(int index) {
    if (_filterPresets.isEmpty) return;
    final safeIndex = index.clamp(0, _filterPresets.length - 1);
    final preset = _filterPresets[safeIndex];
    setState(() {
      _selectedFilterPresetId = preset.id;
      _filterTemplateIndex = safeIndex;
      _filterIntensity =
          (_filterStrengthByPresetId[preset.id] ?? preset.defaultStrength)
              .clamp(0, 100)
              .toDouble();
      _syncFilterCategoryFromTemplateIndex(safeIndex);
    });
  }

  void _onFilterIntensityChanged(double value) {
    final clamped = value.clamp(0.0, 100.0).toDouble();
    final presetId = _selectedFilterPresetId;
    if (presetId == null || presetId.isEmpty) {
      if (_filterPresets.isEmpty) return;
      final fallback = _filterPresets[_filterTemplateIndex.clamp(
        0,
        _filterPresets.length - 1,
      )];
      _selectedFilterPresetId = fallback.id;
    }
    setState(() {
      _filterIntensity = clamped;
      _filterStrengthByPresetId[_selectedFilterPresetId!] = clamped;
    });
  }

  void _onFilterRemove() {
    setState(() {
      _selectedFilterPresetId = null;
      _filterTemplateIndex = -1;
      _filterIntensity = 100;
    });
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
      ..addAll(List<int>.generate(
        safeEnd - safeStart + 1,
        (i) => safeStart + i,
      ));
    for (var i = safeStart; i <= safeEnd; i++) {
      if (_filterTemplatePreviewBytes.containsKey(i) ||
          _filterTemplatePreviewLoading.contains(i) ||
          _filterTemplatePreviewQueued.contains(i)) {
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
          _filterTemplatePreviewBytes.containsKey(index)) {
        continue;
      }
      setState(() => _filterTemplatePreviewLoading.add(index));
      final bytes = await _buildFilterPreviewBytes(index);
      if (!mounted) break;
      setState(() {
        _filterTemplatePreviewLoading.remove(index);
        if (bytes != null) {
          _filterTemplatePreviewBytes[index] = bytes;
        }
      });
    }
    _processingFilterPreviewQueue = false;
  }

  Future<Uint8List?> _buildFilterPreviewBytes(int presetIndex) async {
    if (_currentPath.isEmpty || presetIndex < 0 || presetIndex >= _filterPresets.length) {
      return null;
    }
    final preset = _filterPresets[presetIndex];
    final bytes = await _loadImageBytes(_currentPath);
    if (bytes.isEmpty) return null;
    final codec = await ui.instantiateImageCodec(bytes);
    final frame = await codec.getNextFrame();
    final image = frame.image;
    const previewTarget = 220;
    final ratio = image.width / image.height;
    final width = ratio >= 1 ? previewTarget : (previewTarget * ratio).round();
    final height = ratio >= 1 ? (previewTarget / ratio).round() : previewTarget;
    final recorder = ui.PictureRecorder();
    final canvas = Canvas(recorder);
    final srcRect = Rect.fromLTWH(0, 0, image.width.toDouble(), image.height.toDouble());
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
  }

  /// 是否在图片下方展示曲线调节蒙皮（专业修图-曲线子工具选中时）
  bool get _showCurveOverlayBelowImage => false;

  /// 编辑步骤栈（Snapseed 式历史）
  final List<ImageEditorStep> _steps = [];

  void _pushStep(ImageEditorStep step) {
    setState(() => _steps.add(step));
  }

  void _removeStepAt(int index) {
    if (index < 0 || index >= _steps.length) return;
    setState(() {
      _steps.removeAt(index);
      // 重算：当前为占位，实际应用时按顺序重算其后步骤并更新画布
    });
  }

  void _redoStepAt(int index) {
    if (index < 0 || index >= _steps.length) return;
    final step = _steps[index];
    setState(() {
      if (step.type == 'proTools') {
        final sub = step.params['subType'] as String?;
        if (sub == 'baseAdjustments') {
          final values = (step.params['values'] as Map?)?.map(
                (key, value) => MapEntry(
                  key.toString(),
                  (value as num?)?.toDouble() ?? 0,
                ),
              ) ??
              const <String, double>{};
          _selectedToolIndex = kImageEditorToolPro;
          _selectedProCategory = kImageEditorProCategoryOverall;
          _selectedProBaseToolIndex =
              (step.params['selectedIndex'] as int?) ?? _selectedProBaseToolIndex;
          _proBaseValues
            ..clear()
            ..addAll({
              for (final entry in kImageEditorProBaseEntries)
                entry.type: values[entry.type] ?? 0,
            });
          _prepareProPanelSnapshot();
          return;
        }
        if (sub == 'hslAdjustments') {
          final valuesRaw = (step.params['values'] as Map?)?.map(
                (key, value) => MapEntry(key.toString(), value),
              ) ??
              const <String, Object?>{};
          final restored = createDefaultHslValues();
          for (final channel in kImageEditorHslChannels) {
            final channelMap = valuesRaw[channel.key];
            if (channelMap is Map) {
              restored[channel.key] = {
                kHslAxisHue: (channelMap[kHslAxisHue] as num?)?.toDouble() ?? 0,
                kHslAxisSaturation:
                    (channelMap[kHslAxisSaturation] as num?)?.toDouble() ?? 0,
                kHslAxisLuminance:
                    (channelMap[kHslAxisLuminance] as num?)?.toDouble() ?? 0,
              };
            }
          }
          _selectedToolIndex = kImageEditorToolPro;
          _selectedProCategory = kImageEditorProCategoryHsl;
          _selectedHslChannel = (step.params['selectedChannel'] as String?) ??
              kImageEditorHslChannels.first.key;
          _proHslValues = restored;
          _prepareProPanelSnapshot();
          return;
        }
        if (sub == 'bwLevelsAdjustments') {
          _selectedToolIndex = kImageEditorToolPro;
          _selectedProCategory = kImageEditorProCategoryBwLevels;
          _bwWhiteLevel = (step.params['whiteLevel'] as num?)?.toDouble() ?? _bwWhiteLevel;
          _bwBlackLevel = (step.params['blackLevel'] as num?)?.toDouble() ?? _bwBlackLevel;
          _prepareProPanelSnapshot();
          return;
        }
        if (sub == 'localAdjustments') {
          final anchorsRaw = (step.params['anchors'] as List?) ?? const [];
          final restored = <LocalAnchor>[];
          for (final raw in anchorsRaw) {
            if (raw is! Map) continue;
            final map = raw.cast<dynamic, dynamic>();
            final valuesRaw = (map['values'] as Map?)?.cast<dynamic, dynamic>() ?? const {};
            restored.add(
              LocalAnchor(
                id: (map['id'] as num?)?.toInt() ?? (_localAnchorIdSeed += 1),
                center: Offset(
                  ((map['x'] as num?)?.toDouble() ?? 0.5).clamp(0.0, 1.0),
                  ((map['y'] as num?)?.toDouble() ?? 0.5).clamp(0.0, 1.0),
                ),
                radius: ((map['radius'] as num?)?.toDouble() ?? 0.18).clamp(0.06, 0.45),
                values: <String, double>{
                  for (final key in kLocalParamOrder)
                    key: (valuesRaw[key] as num?)?.toDouble() ?? 0,
                },
                selectedParam: (map['selectedParam'] as String?) ?? kLocalParamBrightness,
              ),
            );
          }
          _selectedToolIndex = kImageEditorToolPro;
          _selectedProCategory = kImageEditorProCategoryLocal;
          _localAnchors
            ..clear()
            ..addAll(restored);
          if (restored.isNotEmpty) {
            _localAnchorIdSeed = restored
                .map((anchor) => anchor.id)
                .reduce(math.max);
          }
          _selectedLocalAnchorId = (step.params['selectedAnchorId'] as num?)?.toInt() ??
              (restored.isNotEmpty ? restored.last.id : null);
          _prepareProPanelSnapshot();
          return;
        }
        final i = kImageEditorProToolEntries.indexWhere((entry) => entry.type == sub);
        if (i >= 0) {
          _selectedToolIndex = kImageEditorToolPro;
          _selectedProToolIndex = i;
          _selectedProCategory = kImageEditorProToolEntries[i].categoryIndex;
          _curveBrightness =
              (step.params['curveBrightness'] as num?)?.toDouble() ??
                  _curveBrightness;
          _curveContrast =
              (step.params['curveContrast'] as num?)?.toDouble() ??
                  _curveContrast;
          _whiteBalanceTemp =
              (step.params['whiteBalanceTemp'] as num?)?.toDouble() ??
                  _whiteBalanceTemp;
        }
      } else {
        if (step.type == 'filter') {
          final presetId = step.params['presetId'] as String?;
          final intensity = (step.params['intensity'] as num?)?.toDouble() ?? 100;
          _selectedFilterPresetId = presetId;
          _filterIntensity = intensity.clamp(0, 100);
          if (presetId != null && presetId.isNotEmpty) {
            _filterStrengthByPresetId[presetId] = _filterIntensity;
            final index = _filterPresets.indexWhere((entry) => entry.id == presetId);
            _filterTemplateIndex = index >= 0 ? index : -1;
            if (index >= 0) {
              _syncFilterCategoryFromTemplateIndex(index);
            }
          }
        }
        _selectedToolIndex = _toolIndexForType(step.type);
      }
    });
  }

  int _toolIndexForType(String type) {
    final i = kImageEditorToolTypes.indexOf(type);
    return i >= 0 ? i : kImageEditorToolCrop;
  }

  static String _stepTypeLabel(String type, [Map<String, dynamic>? params]) {
    if (type == 'proTools' && params != null) {
      switch (params['subType'] as String?) {
        case 'curve':
          return UITextConstants.imageEditorProCurve;
        case 'baseAdjustments':
          return UITextConstants.imageEditorProTabOverall;
        case 'localAdjustments':
          return UITextConstants.imageEditorProTabLocal;
        case 'hslAdjustments':
          return UITextConstants.imageEditorProTabHsl;
        case 'bwLevelsAdjustments':
          return UITextConstants.imageEditorProTabBwLevels;
        case 'whiteBalance':
          return UITextConstants.imageEditorProWhiteBalance;
        case 'local':
          return UITextConstants.imageEditorProLocal;
        case 'hsl':
          return UITextConstants.imageEditorProHsl;
        case 'exposure':
          return UITextConstants.imageEditorProExposure;
        case 'brightness':
          return UITextConstants.imageEditorProBrightness;
        case 'contrast':
          return UITextConstants.imageEditorProContrast;
        case 'saturation':
          return UITextConstants.imageEditorProSaturation;
        case 'highlight':
          return UITextConstants.imageEditorProHighlight;
        case 'shadow':
          return UITextConstants.imageEditorProShadow;
        case 'tone':
          return UITextConstants.imageEditorProTone;
        case 'denoise':
          return UITextConstants.imageEditorProDenoise;
        case 'sharpen':
          return UITextConstants.imageEditorProSharpen;
        case 'unsharpen':
          return UITextConstants.imageEditorProUnsharpen;
      }
    }
    switch (type) {
      case 'rotate':
        return UITextConstants.imageEditorRotate;
      case 'crop':
        return UITextConstants.imageEditorCrop;
      case 'filter':
        return UITextConstants.imageEditorFilter;
      case 'beauty':
        return UITextConstants.imageEditorBeauty;
      case 'proTools':
        return UITextConstants.imageEditorProTools;
      case 'frame':
        return UITextConstants.imageEditorFrame;
      case 'text':
        return UITextConstants.imageEditorText;
      case 'mosaic':
        return UITextConstants.imageEditorMosaic;
      default:
        return type;
    }
  }

  int? _selectedToolIndex;

  /// 裁剪比例：free|original|1x1|2x3|3x2|3x4|4x3|9x16|16x9
  String _cropRatio = 'free';
  Rect _cropRect = const Rect.fromLTWH(0, 0, 1, 1);
  Rect _cropInitialRect = const Rect.fromLTWH(0, 0, 1, 1);
  String _cropInitialRatio = 'free';
  bool _cropEdited = false;
  double? _imageAspectRatio;
  Size _cropLayoutSize = Size.zero;
  Rect _cropImageRect = Rect.zero;
  Offset _cropImageOffset = Offset.zero;
  Offset _cropInitialImageOffset = Offset.zero;
  /// 滤镜：分类索引、模板索引、强度 0~100
  int _filterCategoryIndex = 0;
  int _filterTemplateIndex = -1;
  double _filterIntensity = 100;
  int _filterSnapshotCategoryIndex = 0;
  int _filterSnapshotTemplateIndex = -1;
  double _filterSnapshotIntensity = 100;
  String? _selectedFilterPresetId;
  String? _filterSnapshotPresetId;
  final Map<String, double> _filterStrengthByPresetId = <String, double>{};
  final Map<String, int> _filterUsageCountByPresetId = <String, int>{};
  Map<String, double> _filterSnapshotStrengthByPresetId = <String, double>{};
  final ImageEditorFilterRepository _filterRepository =
      ImageEditorFilterRepository();
  final ImageEditorFilterFeatureExtractor _filterFeatureExtractor =
      const ImageEditorFilterFeatureExtractor();
  final ImageEditorFilterRecommender _filterRecommender =
      const ImageEditorFilterRecommender();
  ImageEditorFilterConfig? _filterConfig;
  List<ImageEditorFilterCategory> _filterCategories = const <ImageEditorFilterCategory>[];
  List<ImageEditorFilterPreset> _filterPresets = const <ImageEditorFilterPreset>[];
  List<int> _filterCategoryAnchors = const <int>[];
  final ScrollController _filterTemplateScrollController = ScrollController();
  final Map<int, Uint8List> _filterTemplatePreviewBytes = <int, Uint8List>{};
  final Set<int> _filterTemplatePreviewLoading = <int>{};
  final Set<int> _filterTemplatePreviewQueued = <int>{};
  final Set<int> _filterVisibleIndices = <int>{};
  final List<int> _filterPreviewQueue = <int>[];
  bool _processingFilterPreviewQueue = false;
  ImageEditorFilterImageFeatures? _filterImageFeatures;
  String? _filterImageFeaturesPath;
  /// 马赛克：类型索引、笔刷大小 0~1
  int _mosaicTypeIndex = 0;
  double _mosaicBrushSize = 0.5;
  /// 相框：模板索引
  int _frameTemplateIndex = 0;
  /// 文字：样式/颜色索引（占位）
  int _textStyleIndex = 0;
  int _textColorIndex = 0;
  /// 旋转：当前角度（度）
  int _rotateDegrees = 0;

  /// 专业修图：当前二级分组（整体/局部/HSL/曲线）
  int _selectedProCategory = kImageEditorProCategoryOverall;
  /// 专业修图：当前选中的工具索引（为空表示停留在工具列表面板）
  int? _selectedProToolIndex;
  /// 专业修图基础分组：当前选中的调节项索引（默认光感）
  int _selectedProBaseToolIndex = 0;
  /// 专业修图基础分组：各调节项值（-100~100）
  final Map<String, double> _proBaseValues = {
    for (final entry in kImageEditorProBaseEntries) entry.type: 0,
  };
  /// 专业修图会话快照：用于 X 取消时回滚
  Map<String, double> _proBaseSnapshotValues = {
    for (final entry in kImageEditorProBaseEntries) entry.type: 0,
  };
  /// HSL：当前选中的颜色通道
  String _selectedHslChannel = kImageEditorHslChannels.first.key;
  /// HSL：通道 -> (hue/saturation/luminance)
  Map<String, Map<String, double>> _proHslValues = createDefaultHslValues();
  /// HSL：进入本次专业面板时的快照
  Map<String, Map<String, double>> _proHslSnapshotValues = createDefaultHslValues();
  /// HSL：会话基线（用于对比原图）
  Map<String, Map<String, double>> _hslSessionBaselineValues = createDefaultHslValues();
  /// HSL：会话撤回/重做栈
  final List<Map<String, Map<String, double>>> _hslSessionStack = [];
  int _hslSessionCursor = -1;
  bool _isComparingSessionBaseline = false;
  bool _hslPickerActive = false;
  Offset? _hslPickerPoint;
  /// 局部：锚点与会话状态
  final List<LocalAnchor> _localAnchors = <LocalAnchor>[];
  List<LocalAnchor> _localSnapshotAnchors = <LocalAnchor>[];
  final List<List<LocalAnchor>> _localSessionStack = <List<LocalAnchor>>[];
  int _localSessionCursor = -1;
  int? _selectedLocalAnchorId;
  bool _localShowAllAnchors = true;
  bool _localRangeVisible = false;
  bool _localAddMode = false;
  bool _localDragging = false;
  bool _localShowAnchorMenu = false;
  Offset? _localMagnifierPoint;
  int? _draggingAnchorId;
  Offset? _draggingAnchorCenter;
  double? _draggingAnchorBaseRadius;
  int _localAnchorIdSeed = 0;
  int _proCategorySnapshot = kImageEditorProCategoryOverall;
  int _proBaseToolSnapshot = 0;
  bool _showProToolbox = false;
  String? _proPlaceholderTitle;
  /// 专业修图工具横向滚动控制器
  final ScrollController _proToolScrollController = ScrollController();
  /// 剪裁比例列表横向滚动，重置时滚回「原始」
  final ScrollController _cropRatioScrollController = ScrollController();

  /// 曲线参数（简化：亮度/对比度占位）
  double _curveBrightness = 0.5;
  double _curveContrast = 0.5;
  /// 白平衡参数（色温占位）
  double _whiteBalanceTemp = 0.5;
  /// 黑白色阶参数（-100..100）
  double _bwWhiteLevel = 0;
  double _bwBlackLevel = 0;
  double _bwSnapshotWhiteLevel = 0;
  double _bwSnapshotBlackLevel = 0;
  double _bwSessionBaselineWhiteLevel = 0;
  double _bwSessionBaselineBlackLevel = 0;
  final List<Map<String, double>> _bwSessionStack = <Map<String, double>>[];
  int _bwSessionCursor = -1;
  /// 旋转精细角度（约 ±45° 或更大，度）
  double _rotateFineDegrees = 0;
  /// 水平/垂直翻转状态（用于旋转工具）
  bool _flipHorizontal = false;
  bool _flipVertical = false;

  @override
  Widget build(BuildContext context) {
    const isDark = true;
    final baseBg = AppColors.black;
    final panelBg = AppColors.black;
    final fg = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    final topPad = MediaQuery.paddingOf(context).top;
    final bottomPad = MediaQuery.paddingOf(context).bottom;
    final isToolEditing = _selectedToolIndex != null;
    // 顶栏纯黑；状态栏纯黑且图标略降对比（通过深灰背景弱化白图标）
    final topBarBg = AppColors.black;
    SystemChrome.setEnabledSystemUIMode(
      SystemUiMode.manual,
      overlays:
          isToolEditing ? [SystemUiOverlay.bottom] : SystemUiOverlay.values,
    );
    SystemChrome.setSystemUIOverlayStyle(
      SystemUiOverlayStyle(
        statusBarColor: AppColors.black,
        statusBarIconBrightness: Brightness.light,
        statusBarBrightness: Brightness.dark,
        systemNavigationBarColor: baseBg,
        systemNavigationBarIconBrightness: Brightness.light,
      ),
    );

    return Scaffold(
      backgroundColor: baseBg,
      body: SafeArea(
        top: false,
        bottom: false,
        child: Stack(
          children: [
            Column(
              children: [
            // 1. 顶栏：仅在图片编辑器主界面显示；进入工具编辑页（剪裁等）时隐藏，保持图片上方整洁
            if (!isToolEditing)
              ImageEditorTopBar(
                backgroundColor: topBarBg,
                foregroundColor: fg,
                foregroundSecondary: fgSecondary,
                topPadding: topPad,
                positionText:
                    '${_currentIndex + 1}/${_paths.isEmpty ? widget.total : _paths.length}',
                onBack: _handleBack,
                onHistory: _showHistorySheet,
                historyEnabled: _steps.isNotEmpty,
              )
            else
              const SizedBox.shrink(),
            // 2. 中部：工具编辑页仅对当前图编辑、不可左右滑动；主界面可多图滑动
            Expanded(
              child: _showCurveOverlayBelowImage
                  ? Column(
                      children: [
                        Expanded(
                          child: _buildMiddleImage(fgSecondary),
                        ),
                        ImageEditorCurveOverlayBar(
                          backgroundColor: panelBg,
                          foregroundColor: fg,
                          foregroundSecondary: fgSecondary,
                          brightness: _curveBrightness,
                          contrast: _curveContrast,
                          onBrightnessChanged: (v) =>
                              setState(() => _curveBrightness = v),
                          onContrastChanged: (v) =>
                              setState(() => _curveContrast = v),
                          onCancel: () =>
                              setState(() => _selectedProToolIndex = null),
                          onConfirm: () {
                            _pushStep(ImageEditorStep(
                              type: 'proTools',
                              params: {
                                'subType': 'curve',
                                'curveBrightness': _curveBrightness,
                                'curveContrast': _curveContrast,
                              },
                            ));
                            setState(() => _selectedProToolIndex = null);
                          },
                        ),
                      ],
                    )
                  : _selectedToolIndex != null
                      ? _buildMiddleImage(fgSecondary)
                      : _isMultiImage && _pageController != null
                          ? PageView.builder(
                              controller: _pageController,
                              itemCount: _paths.length,
                              onPageChanged: (int index) {
                                setState(() => _currentIndex = index);
                                _scrollThumbToIndex(index);
                                _loadImageAspectRatio(_paths[index]);
                                _clearFilterPreviewCache();
                              },
                              itemBuilder: (context, index) {
                                return _buildMiddleImageForPath(
                                    _paths[index], fgSecondary);
                              },
                            )
                          : _buildMiddleImage(fgSecondary),
            ),
            // 多图时仅在主界面显示缩略图；工具编辑页不左右滑动
            if (_isMultiImage && _selectedToolIndex == null)
              _buildThumbnailStrip(panelBg, fgSecondary),
            if (_selectedToolIndex != null && !_showCurveOverlayBelowImage)
              ImageEditorOperationPanel(
                backgroundColor: panelBg,
                foregroundColor: fg,
                foregroundSecondary: fgSecondary,
                bottomInset: bottomPad,
                toolIndex: _selectedToolIndex ?? kImageEditorToolCrop,
                selectedProToolIndex: _selectedProToolIndex,
                selectedProCategory: _selectedProCategory,
                proPlaceholderTitle: _proPlaceholderTitle,
                proToolScrollController: _proToolScrollController,
                onSelectProTool: (index) => setState(() {
                  _selectedProToolIndex = index;
                  _selectedProBaseToolIndex = index;
                }),
                onSelectProCategory: (index) {
                  setState(() {
                    _selectedProCategory = index;
                    _proPlaceholderTitle = null;
                    _hslPickerActive = false;
                    _hslPickerPoint = null;
                    _localShowAnchorMenu = false;
                    _localAddMode = false;
                    _localRangeVisible = false;
                    if (index == kImageEditorProCategoryHsl) {
                      _resetHslSessionHistory();
                    }
                    if (index == kImageEditorProCategoryBwLevels) {
                      _resetBwSessionHistory();
                    }
                    if (index == kImageEditorProCategoryOverall ||
                        index == kImageEditorProCategoryLocal) {
                      _resetLocalSessionHistory();
                    }
                  });
                },
                onProToolScrollSync: (viewportWidth, itemWidth) {},
                onExitProPanel: _cancelProPanel,
                onConfirmProPanel: _confirmProPanel,
                onCancelProTool: () =>
                    _cancelProPanel(),
                onConfirmProTool: _confirmProPanel,
                onCancelPanel: _selectedToolIndex == kImageEditorToolCrop
                    ? _cancelCropAndExit
                    : _selectedToolIndex == kImageEditorToolRotate
                        ? _cancelRotateAndExit
                        : _selectedToolIndex == kImageEditorToolFilter
                            ? _cancelFilterAndExit
                        : _closePanel,
                onConfirmPanel: _selectedToolIndex == kImageEditorToolCrop
                    ? _confirmCropAndExit
                    : _confirmToolPanel,
                showCropReset: _cropEdited,
                onCropReset: _resetCropPanel,
                cropRatioScrollController: _cropRatioScrollController,
                cropRatio: _cropRatio,
                onCropRatioChanged: _onCropRatioChanged,
                filterCategoryIndex: _filterCategoryIndex,
                filterTemplateIndex: _filterTemplateIndex,
                filterIntensity: _filterIntensity,
                onFilterCategoryChanged: _onFilterCategoryChanged,
                onFilterTemplateChanged: _onFilterTemplateChanged,
                onFilterIntensityChanged: _onFilterIntensityChanged,
                filterCategories: _filterCategories,
                filterCategoryAnchors: _filterCategoryAnchors,
                filterPresets: _filterPresets,
                filterTemplatePreviewBytes: _filterTemplatePreviewBytes,
                filterTemplatePreviewLoadingIndices: _filterTemplatePreviewLoading,
                filterTemplateScrollController: _filterTemplateScrollController,
                onFilterVisibleRangeChanged: _onFilterVisibleRangeChanged,
                onFilterRemove: _onFilterRemove,
                mosaicTypeIndex: _mosaicTypeIndex,
                mosaicBrushSize: _mosaicBrushSize,
                onMosaicTypeChanged: (i) =>
                    setState(() => _mosaicTypeIndex = i),
                onMosaicBrushSizeChanged: (v) =>
                    setState(() => _mosaicBrushSize = v),
                frameTemplateIndex: _frameTemplateIndex,
                onFrameTemplateChanged: (i) =>
                    setState(() => _frameTemplateIndex = i),
                textStyleIndex: _textStyleIndex,
                textColorIndex: _textColorIndex,
                onTextStyleChanged: (i) => setState(() => _textStyleIndex = i),
                onTextColorChanged: (i) => setState(() => _textColorIndex = i),
                rotateDegrees: _rotateDegrees,
                rotateFineDegrees: _rotateFineDegrees,
                flipHorizontal: _flipHorizontal,
                flipVertical: _flipVertical,
                onRotateLeft: () => setState(() =>
                    _rotateDegrees = (_rotateDegrees - 90) % 360),
                onRotateRight: () => setState(() =>
                    _rotateDegrees = (_rotateDegrees + 90) % 360),
                onRotateFineChanged: _setRotateFineDegrees,
                onFlipHorizontal: () =>
                    setState(() => _flipHorizontal = !_flipHorizontal),
                onFlipVertical: () =>
                    setState(() => _flipVertical = !_flipVertical),
                showRotateReset: _isRotateEdited,
                onRotateReset: _resetRotateState,
                curveBrightness: _curveBrightness,
                curveContrast: _curveContrast,
                whiteBalanceTemp: _whiteBalanceTemp,
                onCurveBrightnessChanged: (v) =>
                    setState(() => _curveBrightness = v),
                onCurveContrastChanged: (v) =>
                    setState(() => _curveContrast = v),
                onWhiteBalanceTempChanged: (v) =>
                    setState(() => _whiteBalanceTemp = v),
                bwWhiteLevel: _bwWhiteLevel,
                bwBlackLevel: _bwBlackLevel,
                onBwWhiteLevelChanged: (v) => _onBwLevelChanged(isWhite: true, value: v),
                onBwBlackLevelChanged: (v) => _onBwLevelChanged(isWhite: false, value: v),
                proBaseSelectedIndex: _selectedProBaseToolIndex,
                proBaseValues: _proBaseValues,
                onProBaseSelectedIndexChanged: (index) => setState(() {
                  _selectedProBaseToolIndex = index;
                  if (_selectedProCategory == kImageEditorProCategoryLocal &&
                      _selectedLocalAnchor != null) {
                    final selected = _selectedLocalAnchor!;
                    final entry = kImageEditorProBaseEntries[index];
                    final localIndex = _localAnchors.indexWhere(
                      (anchor) => anchor.id == selected.id,
                    );
                    if (localIndex >= 0) {
                      _localAnchors[localIndex] = selected.copyWith(
                        selectedParam: entry.type,
                      );
                    }
                  }
                }),
                onProBaseValueChanged: _onProBaseValueChanged,
                hslSelectedChannel: _selectedHslChannel,
                hslValues: _proHslValues,
                hslPickerActive: _hslPickerActive,
                onSelectHslChannel: (channelKey) => setState(
                  () => _selectedHslChannel = channelKey,
                ),
                onHslValueChanged: _onProHslValueChanged,
                onToggleHslPicker: () => setState(
                  () => _hslPickerActive = !_hslPickerActive,
                ),
                localValues: _selectedLocalValues,
                hasSelectedLocalAnchor: _selectedLocalAnchor != null,
                localShowAllAnchors: _localShowAllAnchors,
                localAddMode: _localAddMode,
                onToggleLocalAddMode: _toggleLocalAddMode,
                onToggleLocalShowAll: () => setState(
                  () => _localShowAllAnchors = !_localShowAllAnchors,
                ),
                localRangeVisible: _localRangeVisible,
                onToggleLocalRangeVisible: () => setState(
                  () => _localRangeVisible = !_localRangeVisible,
                ),
                onCopyLocalAnchor: _copySelectedLocalAnchor,
                onDeleteLocalAnchor: _deleteSelectedLocalAnchor,
              ),
            if (_selectedToolIndex == null)
              ImageEditorBottomBar(
                backgroundColor: panelBg,
                foregroundColor: fg,
                foregroundSecondary: fgSecondary,
                bottomPadding: bottomPad,
                selectedToolIndex: _showProToolbox ? kImageEditorToolPro : _selectedToolIndex,
                onToolSelected: (index) {
                  setState(() {
                    _showProToolbox = false;
                    _selectedToolIndex = index;
                    _selectedProToolIndex = null;
                    if (index == kImageEditorToolCrop) {
                      _prepareCropSnapshot();
                    }
                    if (index == kImageEditorToolRotate) {
                      _applyRotateReset();
                    }
                    if (index == kImageEditorToolFilter) {
                      _prepareFilterSnapshot();
                      _clearFilterPreviewCache();
                      _ensureFilterSelectionForEditing();
                    }
                    if (index == kImageEditorToolPro) {
                      _selectedToolIndex = null;
                      _selectedProCategory = kImageEditorProCategoryOverall;
                      _selectedProToolIndex = null;
                      _proPlaceholderTitle = null;
                      _hslPickerActive = false;
                      _hslPickerPoint = null;
                      _localAddMode = false;
                      _localShowAnchorMenu = false;
                      _localRangeVisible = false;
                      _showProToolbox = true;
                      _prepareProPanelSnapshot();
                    }
                  });
                  if (index == kImageEditorToolFilter) {
                    _rebuildFilterData();
                  }
                },
              ),
              ],
            ),
            if (_selectedToolIndex == null && _showProToolbox)
              _buildProToolboxOverlay(bottomPad),
          ],
        ),
      ),
    );
  }

  void _handleBack() {
    _onDone();
  }

  List<_ProToolboxEntry> _buildProToolboxEntries() {
    return <_ProToolboxEntry>[
      _ProToolboxEntry(
        icon: Icons.tune,
        label: UITextConstants.imageEditorProTabOverall,
        category: kImageEditorProCategoryOverall,
      ),
      _ProToolboxEntry(
        icon: Icons.place_outlined,
        label: UITextConstants.imageEditorProTabLocal,
        category: kImageEditorProCategoryLocal,
      ),
      _ProToolboxEntry(
        icon: Icons.circle_outlined,
        label: UITextConstants.imageEditorProHsl,
        category: kImageEditorProCategoryHsl,
        semanticIconKey: kEditorIconHslSolid,
      ),
      _ProToolboxEntry(
        icon: Icons.crop_16_9_outlined,
        label: UITextConstants.imageEditorProBwLevels,
        category: kImageEditorProCategoryBwLevels,
        semanticIconKey: kEditorIconBwLevels,
      ),
      _ProToolboxEntry(
        icon: Icons.show_chart,
        label: UITextConstants.imageEditorProCurve,
        category: kImageEditorProCategoryCurve,
      ),
      _ProToolboxEntry(
        icon: Icons.wb_sunny_outlined,
        label: UITextConstants.imageEditorProWhiteBalance,
        category: kImageEditorProCategoryWhiteBalance,
      ),
      _ProToolboxEntry(
        icon: Icons.crop_free,
        label: UITextConstants.imageEditorProPerspective,
        category: kImageEditorProCategoryPerspective,
      ),
      _ProToolboxEntry(
        icon: Icons.healing_outlined,
        label: UITextConstants.imageEditorProHeal,
        category: kImageEditorProCategoryPerspective,
        placeholderTitle: UITextConstants.imageEditorProHeal,
      ),
      _ProToolboxEntry(
        icon: Icons.tonality_outlined,
        label: UITextConstants.imageEditorProToneContrast,
        category: kImageEditorProCategoryPerspective,
        placeholderTitle: UITextConstants.imageEditorProToneContrast,
      ),
      _ProToolboxEntry(
        icon: Icons.auto_awesome_outlined,
        label: UITextConstants.imageEditorProGlamourGlow,
        category: kImageEditorProCategoryPerspective,
        placeholderTitle: UITextConstants.imageEditorProGlamourGlow,
      ),
      _ProToolboxEntry(
        icon: Icons.shutter_speed_outlined,
        label: UITextConstants.imageEditorProSharpen,
        category: kImageEditorProCategoryPerspective,
        placeholderTitle: UITextConstants.imageEditorProSharpen,
      ),
    ];
  }

  void _openProEditorFromToolbox(_ProToolboxEntry entry) {
    setState(() {
      _showProToolbox = false;
      _selectedToolIndex = kImageEditorToolPro;
      _selectedProCategory = entry.category;
      _proPlaceholderTitle = entry.placeholderTitle;
      _hslPickerActive = false;
      _hslPickerPoint = null;
      _localShowAnchorMenu = false;
      _localRangeVisible = false;
      _localAddMode = false;
      _isComparingSessionBaseline = false;
      if (entry.category == kImageEditorProCategoryHsl) {
        _resetHslSessionHistory();
      }
      if (entry.category == kImageEditorProCategoryBwLevels) {
        _resetBwSessionHistory();
      }
      if (entry.category == kImageEditorProCategoryOverall ||
          entry.category == kImageEditorProCategoryLocal) {
        _resetLocalSessionHistory();
      }
      _prepareProPanelSnapshot();
    });
  }

  Widget _buildProToolboxOverlay(double bottomPad) {
    final entries = _buildProToolboxEntries();
    final borderColor = AppColors.white.withValues(alpha: 0.10);
    final popupBottom = bottomPad + AppSpacing.bottomNavHeight + AppSpacing.sm;
    return Positioned.fill(
      child: Stack(
        children: [
          Positioned(
            left: 0,
            right: 0,
            top: 0,
            bottom: popupBottom,
            child: GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: () => setState(() => _showProToolbox = false),
              child: const SizedBox.expand(),
            ),
          ),
          Positioned(
            left: 0,
            right: 0,
            bottom: popupBottom,
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: AppColors.black.withValues(alpha: 0.96),
                borderRadius: BorderRadius.vertical(
                  top: Radius.circular(AppSpacing.largeBorderRadius),
                ),
                border: Border(
                  top: BorderSide(color: borderColor),
                  left: BorderSide(color: borderColor),
                  right: BorderSide(color: borderColor),
                ),
              ),
              child: Padding(
                padding: EdgeInsets.fromLTRB(
                  AppSpacing.containerSm,
                  AppSpacing.intraGroupXs,
                  AppSpacing.containerSm,
                  AppSpacing.intraGroupXs,
                ),
                child: GridView.builder(
                  shrinkWrap: true,
                  itemCount: entries.length,
                  physics: const NeverScrollableScrollPhysics(),
                  gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                    crossAxisCount: 5,
                    crossAxisSpacing: AppSpacing.intraGroupSm,
                    mainAxisSpacing: AppSpacing.intraGroupXs,
                    childAspectRatio: 1.02,
                  ),
                  itemBuilder: (context, index) {
                    final entry = entries[index];
                    final unselectedColor =
                        AppColors.white.withValues(alpha: 0.6);
                    return InkWell(
                      onTap: () => _openProEditorFromToolbox(entry),
                      borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          if (entry.semanticIconKey != null)
                            ImageEditorSemanticIcon(
                              iconKey: entry.semanticIconKey!,
                              size: AppSpacing.iconLarge,
                              color: unselectedColor,
                            )
                          else
                            Icon(
                              entry.icon,
                              size: AppSpacing.iconLarge,
                              color: unselectedColor,
                            ),
                          SizedBox(height: AppSpacing.toolPanelItemIconLabelGap),
                          Text(
                            entry.label,
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              fontSize: AppTypography.sm,
                              color: unselectedColor,
                            ),
                          ),
                        ],
                      ),
                    );
                  },
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  void _closePanel() {
    setState(() {
      _selectedToolIndex = null;
      _selectedProToolIndex = null;
      _proPlaceholderTitle = null;
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
    _resetHslSessionHistory();
    _resetBwSessionHistory();
    _resetLocalSessionHistory();
  }

  void _cancelProPanel() {
    setState(() {
      _selectedProCategory = _proCategorySnapshot;
      _selectedProBaseToolIndex = _proBaseToolSnapshot;
      _proPlaceholderTitle = null;
      _proBaseValues
        ..clear()
        ..addAll(_proBaseSnapshotValues);
      _bwWhiteLevel = _bwSnapshotWhiteLevel;
      _bwBlackLevel = _bwSnapshotBlackLevel;
      _proHslValues = cloneHslValues(_proHslSnapshotValues);
      _localAnchors
        ..clear()
        ..addAll(cloneLocalAnchors(_localSnapshotAnchors));
      if (_selectedLocalAnchorId != null &&
          _localAnchors.every((anchor) => anchor.id != _selectedLocalAnchorId)) {
        _selectedLocalAnchorId = _localAnchors.isNotEmpty ? _localAnchors.last.id : null;
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
      _selectedProToolIndex = null;
      _showProToolbox = false;
    });
  }

  void _onProBaseValueChanged(String toolType, double value) {
    if (_selectedToolIndex == kImageEditorToolPro &&
        _selectedProCategory == kImageEditorProCategoryLocal &&
        _selectedLocalAnchor == null) {
      _showLocalHint(UITextConstants.imageEditorProAnchorSelectHint);
      return;
    }
    final clamped = value.clamp(-100.0, 100.0);
    setState(() {
      if (_selectedToolIndex == kImageEditorToolPro &&
          _selectedProCategory == kImageEditorProCategoryLocal &&
          _selectedLocalAnchor != null) {
        final selected = _selectedLocalAnchor!;
        final index = _localAnchors.indexWhere((anchor) => anchor.id == selected.id);
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
    ScaffoldMessenger.of(context)
      ..clearSnackBars()
      ..showSnackBar(
        SnackBar(
          content: Text(message),
          duration: const Duration(milliseconds: 1400),
        ),
      );
  }

  void _toggleLocalAddMode() {
    final toEnable = !_localAddMode;
    if (toEnable && _localAnchors.length >= _kLocalAnchorMaxCount) {
      _showLocalHint(UITextConstants.imageEditorProAnchorLimitReached);
      return;
    }
    setState(() {
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
    if (_localAnchors.length >= _kLocalAnchorMaxCount) {
      _showLocalHint(UITextConstants.imageEditorProAnchorLimitReached);
      setState(() => _localAddMode = false);
      return;
    }
    final imageRect = _resolveImageRect(imageSize);
    if (!imageRect.contains(localPosition)) return;
    final nx =
        ((localPosition.dx - imageRect.left) / imageRect.width).clamp(0.0, 1.0);
    final ny =
        ((localPosition.dy - imageRect.top) / imageRect.height).clamp(0.0, 1.0);
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
    setState(() {
      _localAnchors.add(anchor);
      _selectedLocalAnchorId = nextId;
      _localAddMode = false;
      _localShowAnchorMenu = false;
      _recordLocalSessionStep();
    });
  }

  void _updateLocalAnchorPosition(int anchorId, Offset localPosition, Rect imageRect) {
    final dx = ((localPosition.dx - imageRect.left) / imageRect.width).clamp(0.0, 1.0);
    final dy = ((localPosition.dy - imageRect.top) / imageRect.height).clamp(0.0, 1.0);
    final index = _localAnchors.indexWhere((anchor) => anchor.id == anchorId);
    if (index < 0) return;
    setState(() {
      _localAnchors[index] = _localAnchors[index].copyWith(center: Offset(dx, dy));
      _selectedLocalAnchorId = anchorId;
      _localShowAnchorMenu = false;
    });
  }

  void _updateLocalAnchorRadius(int anchorId, double radius) {
    final index = _localAnchors.indexWhere((anchor) => anchor.id == anchorId);
    if (index < 0) return;
    final clamped = radius.clamp(0.06, 0.45);
    setState(() {
      _localAnchors[index] = _localAnchors[index].copyWith(radius: clamped);
      _selectedLocalAnchorId = anchorId;
      _localShowAnchorMenu = false;
    });
  }

  void _copySelectedLocalAnchor() {
    final selected = _selectedLocalAnchor;
    if (selected == null) return;
    if (_localAnchors.length >= _kLocalAnchorMaxCount) {
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
    setState(() {
      _localAnchors.add(copied);
      _selectedLocalAnchorId = copied.id;
      _localShowAnchorMenu = false;
      _recordLocalSessionStep();
    });
  }

  void _deleteSelectedLocalAnchor() {
    final selected = _selectedLocalAnchor;
    if (selected == null) return;
    setState(() {
      _localAnchors.removeWhere((anchor) => anchor.id == selected.id);
      _selectedLocalAnchorId =
          _localAnchors.isNotEmpty ? _localAnchors.last.id : null;
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
        1, 0, 0, 0, 0,
        0, 1, 0, 0, 0,
        0, 0, 1, 0, 0,
        0, 0, 0, 1, 0,
      ];

  List<double> _multiplyColorMatrices(List<double> a, List<double> b) {
    final out = List<double>.filled(20, 0);
    for (var row = 0; row < 4; row++) {
      final rowOffset = row * 5;
      for (var col = 0; col < 5; col++) {
        if (col == 4) {
          out[rowOffset + col] = a[rowOffset] * b[4] +
              a[rowOffset + 1] * b[9] +
              a[rowOffset + 2] * b[14] +
              a[rowOffset + 3] * b[19] +
              a[rowOffset + 4];
        } else {
          out[rowOffset + col] = a[rowOffset] * b[col] +
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
      1, 0, 0, 0, offset,
      0, 1, 0, 0, offset,
      0, 0, 1, 0, offset,
      0, 0, 0, 1, 0,
    ];
  }

  List<double> _contrastMatrix(double value) {
    final factor = (1 + value / 100).clamp(0.0, 3.0);
    final translate = 128 * (1 - factor);
    return <double>[
      factor, 0, 0, 0, translate,
      0, factor, 0, 0, translate,
      0, 0, factor, 0, translate,
      0, 0, 0, 1, 0,
    ];
  }

  List<double> _saturationMatrix(double value) {
    final s = (1 + value / 100).clamp(0.0, 3.0);
    const lR = 0.2126;
    const lG = 0.7152;
    const lB = 0.0722;
    return <double>[
      lR * (1 - s) + s, lG * (1 - s), lB * (1 - s), 0, 0,
      lR * (1 - s), lG * (1 - s) + s, lB * (1 - s), 0, 0,
      lR * (1 - s), lG * (1 - s), lB * (1 - s) + s, 0, 0,
      0, 0, 0, 1, 0,
    ];
  }

  List<double> _temperatureMatrix(double value) {
    final t = (value / 100).clamp(-1.0, 1.0);
    final redScale = (1 + t * 0.18).clamp(0.7, 1.3);
    final blueScale = (1 - t * 0.18).clamp(0.7, 1.3);
    return <double>[
      redScale, 0, 0, 0, 0,
      0, 1, 0, 0, 0,
      0, 0, blueScale, 0, 0,
      0, 0, 0, 1, 0,
    ];
  }

  List<double> _tintMatrix(double value) {
    final t = (value / 100).clamp(-1.0, 1.0);
    final greenScale = (1 - t * 0.12).clamp(0.75, 1.25);
    final redBlueScale = (1 + t * 0.08).clamp(0.75, 1.25);
    return <double>[
      redBlueScale, 0, 0, 0, 0,
      0, greenScale, 0, 0, 0,
      0, 0, redBlueScale, 0, 0,
      0, 0, 0, 1, 0,
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
      scale, 0, 0, 0, offset,
      0, scale, 0, 0, offset,
      0, 0, scale, 0, offset,
      0, 0, 0, 1, 0,
    ];
  }

  List<double> _exposureMatrix(double value) {
    final ev = (value / 100).clamp(-1.5, 1.5);
    final factor = math.pow(2, ev).toDouble();
    return <double>[
      factor, 0, 0, 0, 0,
      0, factor, 0, 0, 0,
      0, 0, factor, 0, 0,
      0, 0, 0, 1, 0,
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

  List<double> _buildProBaseColorMatrix() => _buildBaseColorMatrixFromValues(_proBaseValues);

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

  List<double> _buildLocalApproxColorMatrix(List<LocalAnchor> anchors) {
    if (anchors.isEmpty) return _identityColorMatrix();
    var sumWeight = 0.0;
    final weighted = <String, double>{
      for (final key in kLocalParamOrder) key: 0.0,
    };
    for (final anchor in anchors) {
      final weight = (anchor.radius * anchor.radius).clamp(0.0, 1.0);
      sumWeight += weight;
      for (final key in kLocalParamOrder) {
        weighted[key] = (weighted[key] ?? 0) + (anchor.values[key] ?? 0) * weight;
      }
    }
    if (sumWeight <= 0) return _identityColorMatrix();
    final averaged = <String, double>{
      for (final entry in weighted.entries) entry.key: entry.value / sumWeight,
    };
    return _buildBaseColorMatrixFromValues(averaged);
  }

  List<double> _buildCombinedProColorMatrix({
    bool useHslSessionBaseline = false,
    bool useBwLevelsSessionBaseline = false,
    bool useLocalSessionBaseline = false,
    bool includeLocal = true,
  }) {
    var matrix = _identityColorMatrix();
    if (_hasProBaseAdjustments) {
      matrix = _multiplyColorMatrices(_buildProBaseColorMatrix(), matrix);
    }
    final hslSource = useHslSessionBaseline ? _hslSessionBaselineValues : _proHslValues;
    final hasHsl = hslSource.values.any(
      (channelValues) => channelValues.values.any((value) => value.abs() > 0.001),
    );
    if (hasHsl) {
      matrix = _multiplyColorMatrices(_buildProHslColorMatrix(hslSource), matrix);
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
    if (includeLocal) {
      final localSource = useLocalSessionBaseline ? _localSnapshotAnchors : _localAnchors;
      final hasLocal = localSource.any(
        (anchor) => anchor.values.values.any((value) => value.abs() > 0.001),
      );
      if (hasLocal) {
        matrix = _multiplyColorMatrices(_buildLocalApproxColorMatrix(localSource), matrix);
      }
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
  ) {
    final ratio = (strength / 100).clamp(0.0, 1.0);
    final scaledValues = <String, double>{
      for (final entry in preset.params.entries)
        entry.key: _boostFilterParam(entry.key, entry.value) * ratio,
    };
    var matrix = _buildBaseColorMatrixFromValues(scaledValues);
    final hue = (preset.params['hue'] ?? 0) * ratio;
    if (hue.abs() > 0.001) {
      matrix = _multiplyColorMatrices(_hueRotationMatrix(hue), matrix);
    }
    return matrix;
  }

  double _boostFilterParam(String key, double value) {
    final abs = value.abs();
    double factor;
    switch (key) {
      case 'contrast':
      case 'saturation':
      case 'vibrance':
      case 'temperature':
      case 'tint':
      case 'hue':
        factor = 1.45;
        break;
      case 'fade':
      case 'grain':
      case 'structure':
      case 'sharpen':
      case 'texture':
        factor = 1.55;
        break;
      case 'highlight':
      case 'shadow':
      case 'lightSense':
      case 'brightness':
      case 'exposure':
      default:
        factor = 1.30;
        break;
    }
    if (abs >= 45) factor += 0.12;
    return (value * factor).clamp(-100.0, 100.0).toDouble();
  }

  Widget _wrapWithFilterAdjustments(Widget imageWidget) {
    final preset = _selectedFilterPreset;
    if (preset == null) return imageWidget;
    final strength =
        (_filterStrengthByPresetId[preset.id] ?? _filterIntensity).clamp(0, 100);
    if (strength <= 0.001) return imageWidget;
    return ColorFiltered(
      colorFilter: ColorFilter.matrix(
        _buildFilterColorMatrix(preset, strength.toDouble()),
      ),
      child: imageWidget,
    );
  }

  Widget _wrapWithProAdjustments(
    Widget imageWidget, {
    bool includeLocal = true,
  }) {
    if (!_hasProBaseAdjustments &&
        !_hasProHslAdjustments &&
        !_hasBwLevelsAdjustments &&
        (!includeLocal || !_hasLocalAdjustments)) {
      return imageWidget;
    }
    final useBaseline = _isComparingSessionBaseline && _isEditingHsl;
    final useBwBaseline = _isComparingSessionBaseline && _isEditingBwLevels;
    final useLocalBaseline = _isComparingSessionBaseline && _isEditingLocal;
    return ColorFiltered(
      colorFilter: ColorFilter.matrix(
        _buildCombinedProColorMatrix(
          useHslSessionBaseline: useBaseline,
          useBwLevelsSessionBaseline: useBwBaseline,
          useLocalSessionBaseline: useLocalBaseline,
          includeLocal: includeLocal,
        ),
      ),
      child: imageWidget,
    );
  }

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
      ..add(<String, double>{
        'white': _bwWhiteLevel,
        'black': _bwBlackLevel,
      });
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
      _hslSessionStack.removeRange(_hslSessionCursor + 1, _hslSessionStack.length);
    }
    _hslSessionStack.add(snapshot);
    _hslSessionCursor = _hslSessionStack.length - 1;
  }

  void _onProHslValueChanged(String axis, double value) {
    final clamped = value.clamp(-100.0, 100.0);
    setState(() {
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
    setState(() {
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
        _localSessionStack[_localSessionCursor].toString() == snapshot.toString()) {
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
      final initial = _proHslSnapshotValues[channel.key] ?? const <String, double>{};
      for (final axis in const [kHslAxisHue, kHslAxisSaturation, kHslAxisLuminance]) {
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
        if (((current.values[key] ?? 0) - (initial.values[key] ?? 0)).abs() > 0.001) {
          return true;
        }
      }
    }
    return false;
  }

  void _confirmProPanel() {
    if (_selectedToolIndex != kImageEditorToolPro) return;
    final isOverall = _selectedProCategory == kImageEditorProCategoryOverall;
    final isLocal = _selectedProCategory == kImageEditorProCategoryLocal;
    final isHsl = _selectedProCategory == kImageEditorProCategoryHsl;
    final isBw = _selectedProCategory == kImageEditorProCategoryBwLevels;
    if (isOverall && _isProBaseSessionEdited()) {
      _pushStep(
        ImageEditorStep(
          type: 'proTools',
          params: {
            'subType': 'baseAdjustments',
            'values': Map<String, double>.from(_proBaseValues),
            'selectedIndex': _selectedProBaseToolIndex,
          },
        ),
      );
    }
    if (isLocal && _isLocalSessionEdited()) {
      _pushStep(
        ImageEditorStep(
          type: 'proTools',
          params: {
            'subType': 'localAdjustments',
            'anchors': _localAnchors
                .map((anchor) => <String, dynamic>{
                      'id': anchor.id,
                      'x': anchor.center.dx,
                      'y': anchor.center.dy,
                      'radius': anchor.radius,
                      'selectedParam': anchor.selectedParam,
                      'values': Map<String, double>.from(anchor.values),
                    })
                .toList(growable: false),
            'selectedAnchorId': _selectedLocalAnchorId,
          },
        ),
      );
    }
    if (isHsl && _isProHslSessionEdited()) {
      _pushStep(
        ImageEditorStep(
          type: 'proTools',
          params: {
            'subType': 'hslAdjustments',
            'values': cloneHslValues(_proHslValues),
            'selectedChannel': _selectedHslChannel,
          },
        ),
      );
    }
    if (isBw && _isProBwLevelsSessionEdited()) {
      _pushStep(
        ImageEditorStep(
          type: 'proTools',
          params: {
            'subType': 'bwLevelsAdjustments',
            'whiteLevel': _bwWhiteLevel,
            'blackLevel': _bwBlackLevel,
          },
        ),
      );
    }
    setState(() {
      _hslPickerActive = false;
      _hslPickerPoint = null;
      _isComparingSessionBaseline = false;
      _selectedToolIndex = null;
      _selectedProToolIndex = null;
      _proPlaceholderTitle = null;
      _showProToolbox = false;
    });
  }

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
    setState(_applyRotateReset);
  }

  void _setRotateFineDegrees(double v) {
    final clamped = v.clamp(
      -RotateOverlayConstants.fineMaxDegrees,
      RotateOverlayConstants.fineMaxDegrees,
    );
    setState(() => _rotateFineDegrees = clamped);
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
    setState(() {
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
    setState(() {
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
    final isFile = path.startsWith('/') ||
        (path.length > 1 && path[1] == ':');
    final ImageProvider provider = isFile
        ? FileImage(File(path))
        : NetworkImage(path);
    final stream = provider.resolve(ImageConfiguration.empty);
    late final ImageStreamListener listener;
    listener = ImageStreamListener(
      (info, _) {
        stream.removeListener(listener);
        if (!mounted) return;
        final ratio = info.image.width / info.image.height;
        setState(() => _imageAspectRatio = ratio);
      },
      onError: (error, stackTrace) => stream.removeListener(listener),
    );
    stream.addListener(listener);
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
    return (a.dx - b.dx).abs() <= tolerance &&
        (a.dy - b.dy).abs() <= tolerance;
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
      final croppedImage = await recorder
          .endRecording()
          .toImage(srcRect.width.round(), srcRect.height.round());
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
      final rotatedImage = await recorder
          .endRecording()
          .toImage(outputWidth.round(), outputHeight.round());
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
      final dstRect = Rect.fromLTWH(0, 0, image.width.toDouble(), image.height.toDouble());
      final paint = Paint()
        ..colorFilter = ColorFilter.matrix(_buildCombinedProColorMatrix());
      canvas.drawImageRect(image, dstRect, dstRect, paint);
      final adjusted = await recorder
          .endRecording()
          .toImage(image.width, image.height);
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
    final strength =
        (_filterStrengthByPresetId[preset.id] ?? _filterIntensity).clamp(0, 100);
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
      final rect = Rect.fromLTWH(0, 0, image.width.toDouble(), image.height.toDouble());
      final paint = Paint()
        ..colorFilter = ColorFilter.matrix(
          _buildFilterColorMatrix(preset, strength.toDouble()),
        );
      canvas.drawImageRect(image, rect, rect, paint);
      final adjusted = await recorder.endRecording().toImage(image.width, image.height);
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
    final isFile = path.startsWith('/') ||
        (path.length > 1 && path[1] == ':');
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
    final params = <String, dynamic>{'index': toolIndex};
    if (toolIndex == kImageEditorToolRotate) {
      if (!_isRotateEdited) {
        setState(() => _selectedToolIndex = null);
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
        return;
      }
    }
    if (toolIndex == kImageEditorToolFilter) {
      final preset = _selectedFilterPreset;
      if (preset != null && _hasFilterAdjustments) {
        final filteredPath = await _applyFilterToCurrentImage();
        if (filteredPath == null) return;
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
    setState(() {
      if (toolIndex == kImageEditorToolFilter) {
        _selectedFilterPresetId = null;
        _filterIntensity = 100;
      }
      _selectedToolIndex = null;
    });
  }

  /// 剪裁底部 X：放弃剪裁，仅退出剪裁面板，返回图片编辑器。
  void _cancelCropAndExit() {
    setState(() => _selectedToolIndex = null);
  }

  /// 旋转底部 X：放弃旋转，仅退出旋转面板并恢复初始旋转状态。
  void _cancelRotateAndExit() {
    setState(() {
      _applyRotateReset();
      _selectedToolIndex = null;
    });
  }

  /// 剪裁顶栏完成 / 底部 ✓：应用剪裁并仅退出剪裁面板，返回图片编辑器（不退出整个编辑器）。
  Future<void> _confirmCropAndExit() async {
    if (_selectedToolIndex != kImageEditorToolCrop) return;
    final croppedPath = await _applyCropToCurrentImage();
    if (croppedPath == null) return;
    _paths[_currentIndex] = croppedPath;
    _loadImageAspectRatio(croppedPath);
    _clearFilterPreviewCache();
    _prepareCropSnapshot();
    _pushStep(ImageEditorStep(type: 'crop', params: {
      'ratio': _cropRatio,
      'path': croppedPath,
    }));
    if (!mounted) return;
    setState(() => _selectedToolIndex = null);
  }

  void _scrollThumbToIndex(int index) {
    final c = _thumbScrollController;
    if (c == null || !c.hasClients) return;
    final thumbWidth = AppSpacing.bottomNavHeight + AppSpacing.intraGroupSm;
    final offset = (index * thumbWidth) - c.position.viewportDimension / 2 + thumbWidth / 2;
    c.animateTo(
      offset.clamp(0.0, c.position.maxScrollExtent),
      duration: Duration(
        milliseconds: (AppSpacing.buttonSize * 4).round(),
      ),
      curve: Curves.easeOut,
    );
  }

  Widget _buildThumbnailStrip(Color bg, Color fgSecondary) {
    final thumbSize = AppSpacing.bottomNavHeight;
    final borderColor = AppColorsFunctional.getColor(
      true,
      ColorType.borderPrimary,
    ).withValues(alpha: 0.3);
    return Container(
      height: thumbSize + AppSpacing.sm * 2,
      padding: EdgeInsets.symmetric(vertical: AppSpacing.sm),
      decoration: BoxDecoration(
        color: bg,
        border: Border(top: BorderSide(color: borderColor)),
      ),
      child: ListView.builder(
        controller: _thumbScrollController,
        scrollDirection: Axis.horizontal,
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.semantic[DesignSemanticConstants.container]
                  ?[DesignSemanticConstants.sm] ??
              AppSpacing.containerSm,
        ),
        itemCount: _paths.length,
        itemBuilder: (context, index) {
          final path = _paths[index];
          final isSelected = index == _currentIndex;
          return Padding(
            padding: EdgeInsets.only(
              right: index < _paths.length - 1 ? AppSpacing.intraGroupSm : 0,
            ),
            child: GestureDetector(
              onTap: () {
                _pageController?.jumpToPage(index);
                setState(() => _currentIndex = index);
                _scrollThumbToIndex(index);
              },
              child: Container(
                width: thumbSize,
                height: thumbSize,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(
                    AppSpacing.semantic[DesignSemanticConstants.button]
                            ?[DesignSemanticConstants.sm] ??
                        AppSpacing.smallBorderRadius,
                  ),
                  border: Border.all(
                    color: isSelected
                        ? AppColors.primaryColor
                        : fgSecondary.withValues(alpha: 0.3),
                    width: isSelected ? 2 : 1,
                  ),
                ),
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(
                    (AppSpacing.semantic[DesignSemanticConstants.button]
                            ?[DesignSemanticConstants.sm] ??
                        AppSpacing.smallBorderRadius) -
                        1,
                  ),
                  child: _buildThumbnailImage(path, fgSecondary),
                ),
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _buildThumbnailImage(String path, Color fgSecondary) {
    final isFile = path.startsWith('/') ||
        (path.length > 1 && path[1] == ':');
    if (isFile && File(path).existsSync()) {
      return Image.file(File(path), fit: BoxFit.cover);
    }
    if (!isFile) {
      return Image.network(path, fit: BoxFit.cover);
    }
    return Icon(Icons.broken_image_outlined, size: AppSpacing.iconMedium, color: fgSecondary);
  }

  Widget _buildMiddleImageForPath(String path, Color fgSecondary) {
    if (path.isEmpty) {
      return Center(
        child: Text(
          UITextConstants.loadFailed,
          style: TextStyle(color: fgSecondary),
        ),
      );
    }
    final isFile = path.startsWith('/') ||
        (path.length > 1 && path[1] == ':');
    Widget imageWidget;
    if (isFile && File(path).existsSync()) {
      imageWidget = Image.file(
        File(path),
        fit: BoxFit.contain,
        errorBuilder: (context, error, stackTrace) => Icon(
          Icons.broken_image_outlined,
          size: AppSpacing.largeAvatarSize,
          color: fgSecondary,
        ),
      );
    } else if (!isFile) {
      imageWidget = Image.network(
        path,
        fit: BoxFit.contain,
        errorBuilder: (context, error, stackTrace) => Icon(
          Icons.broken_image_outlined,
          size: AppSpacing.largeAvatarSize,
          color: fgSecondary,
        ),
      );
    } else {
      imageWidget = Icon(
        Icons.broken_image_outlined,
        size: AppSpacing.largeAvatarSize,
        color: fgSecondary,
      );
    }
    imageWidget = _wrapWithFilterAdjustments(imageWidget);
    imageWidget = _wrapWithProAdjustments(
      imageWidget,
      includeLocal: !_isEditingLocal,
    );
    final previewWidget = _selectedToolIndex == kImageEditorToolRotate
        ? _buildRotatePreview(imageWidget)
        : imageWidget;
    final isHslEditing = _isEditingHsl;
    final isBwEditing = _isEditingBwLevels;
    final isLocalEditing = _isEditingLocal;
    final content = _selectedToolIndex == kImageEditorToolCrop
        ? _buildCropImageLayer(previewWidget)
        : (isHslEditing || isBwEditing || isLocalEditing)
            ? Center(child: previewWidget)
            : InteractiveViewer(
                minScale: 0.5,
                maxScale: 4,
                child: Center(child: previewWidget),
              );
    if (_selectedToolIndex == kImageEditorToolCrop) {
      return Stack(
        alignment: Alignment.center,
        children: [
          content,
          _buildCropOverlay(),
        ],
      );
    }
    if (_selectedToolIndex == kImageEditorToolRotate) {
      return Stack(
        fit: StackFit.expand,
        children: [
          content,
          _buildRotateGridOverlay(),
        ],
      );
    }
    if (isHslEditing) {
      return _buildHslSessionImageLayer(content);
    }
    if (isBwEditing) {
      return _buildBwSessionImageLayer(content);
    }
    if (isLocalEditing) {
      return _buildLocalSessionImageLayer(content);
    }
    return content;
  }

  Widget _buildMiddleImage(Color fgSecondary) {
    if (_currentPath.isEmpty) {
      return Center(
        child: Text(
          UITextConstants.loadFailed,
          style: TextStyle(color: fgSecondary),
        ),
      );
    }
    final isFile = _currentPath.startsWith('/') ||
        (_currentPath.length > 1 && _currentPath[1] == ':');
    Widget imageWidget;
    if (isFile && File(_currentPath).existsSync()) {
      imageWidget = Image.file(
        File(_currentPath),
        fit: BoxFit.contain,
        errorBuilder: (context, error, stackTrace) => Icon(
          Icons.broken_image_outlined,
          size: AppSpacing.largeAvatarSize,
          color: fgSecondary,
        ),
      );
    } else if (!isFile) {
      imageWidget = Image.network(
        _currentPath,
        fit: BoxFit.contain,
        errorBuilder: (context, error, stackTrace) => Icon(
          Icons.broken_image_outlined,
          size: AppSpacing.largeAvatarSize,
          color: fgSecondary,
        ),
      );
    } else {
      imageWidget = Icon(
        Icons.broken_image_outlined,
        size: AppSpacing.largeAvatarSize,
        color: fgSecondary,
      );
    }
    imageWidget = _wrapWithFilterAdjustments(imageWidget);
    imageWidget = _wrapWithProAdjustments(
      imageWidget,
      includeLocal: !_isEditingLocal,
    );
    final previewWidget = _selectedToolIndex == kImageEditorToolRotate
        ? _buildRotatePreview(imageWidget)
        : imageWidget;
    final isHslEditing = _isEditingHsl;
    final isBwEditing = _isEditingBwLevels;
    final isLocalEditing = _isEditingLocal;
    final content = _selectedToolIndex == kImageEditorToolCrop
        ? _buildCropImageLayer(previewWidget)
        : (isHslEditing || isBwEditing || isLocalEditing)
            ? Center(child: previewWidget)
            : InteractiveViewer(
                minScale: 0.5,
                maxScale: 4,
                child: Center(child: previewWidget),
              );
    if (_selectedToolIndex == kImageEditorToolCrop) {
      return Stack(
        alignment: Alignment.center,
        children: [
          content,
          _buildCropOverlay(),
        ],
      );
    }
    if (_selectedToolIndex == kImageEditorToolRotate) {
      return Stack(
        fit: StackFit.expand,
        children: [
          content,
          _buildRotateGridOverlay(),
        ],
      );
    }
    if (isHslEditing) {
      return _buildHslSessionImageLayer(content);
    }
    if (isBwEditing) {
      return _buildBwSessionImageLayer(content);
    }
    if (isLocalEditing) {
      return _buildLocalSessionImageLayer(content);
    }
    return content;
  }

  Widget _buildCropImageLayer(Widget imageWidget) {
    final canDrag = _cropRatio != 'free';
    return GestureDetector(
      onPanUpdate: canDrag ? (details) => _updateCropImageOffset(details.delta) : null,
      child: Transform.translate(
        offset: _cropImageOffset,
        child: Center(child: imageWidget),
      ),
    );
  }

  Widget _buildRotatePreview(Widget imageWidget) {
    return ImageEditorRotatePreview(
      totalDegrees: (_rotateDegrees + _rotateFineDegrees).toDouble(),
      flipHorizontal: _flipHorizontal,
      flipVertical: _flipVertical,
      imageAspectRatio: _imageAspectRatio ?? 1,
      child: imageWidget,
    );
  }

  Widget _buildHslSessionImageLayer(Widget content) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final imageSize = Size(constraints.maxWidth, constraints.maxHeight);
        return GestureDetector(
          behavior: HitTestBehavior.translucent,
          onTapDown: _hslPickerActive
              ? (details) => _handleHslPickerTap(details.localPosition, imageSize)
              : null,
          child: Stack(
            fit: StackFit.expand,
            children: [
              content,
              if (_hslPickerPoint != null && _hslPickerActive)
                Positioned(
                  left: _hslPickerPoint!.dx - AppSpacing.iconMedium,
                  top: _hslPickerPoint!.dy - AppSpacing.iconMedium,
                  child: IgnorePointer(
                    child: Container(
                      width: AppSpacing.iconLarge,
                      height: AppSpacing.iconLarge,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        border: Border.all(
                          color: AppColors.white,
                          width: AppSpacing.xs / 2,
                        ),
                        color: Colors.transparent,
                      ),
                    ),
                  ),
                ),
              Align(
                alignment: Alignment.bottomCenter,
                child: SafeArea(
                  top: false,
                  bottom: true,
                  child: EditorSessionOpsStrip(
                    supportsCompare: true,
                    isComparing: _isComparingSessionBaseline,
                    onCompareStart: () => setState(
                      () => _isComparingSessionBaseline = true,
                    ),
                    onCompareEnd: () => setState(
                      () => _isComparingSessionBaseline = false,
                    ),
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildBwSessionImageLayer(Widget content) {
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
              onCompareStart: () => setState(
                () => _isComparingSessionBaseline = true,
              ),
              onCompareEnd: () => setState(
                () => _isComparingSessionBaseline = false,
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildLocalSessionImageLayer(Widget content) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final imageSize = Size(constraints.maxWidth, constraints.maxHeight);
        final imageRect = _resolveImageRect(imageSize);
        return GestureDetector(
          behavior: HitTestBehavior.translucent,
          onTapDown: (details) {
            if (_localAddMode) {
              _addLocalAnchorAt(details.localPosition, imageSize);
            } else {
              setState(() => _localShowAnchorMenu = false);
            }
          },
          child: Stack(
            fit: StackFit.expand,
            children: [
              content,
              ..._buildLocalPreviewLayers(content, imageRect),
              if (_localRangeVisible) ..._buildLocalRangeOverlays(imageRect),
              ..._buildLocalAnchorWidgets(imageRect),
              if (_localDragging && _localMagnifierPoint != null)
                _buildLocalMagnifier(_localMagnifierPoint!),
              Align(
                alignment: Alignment.bottomCenter,
                child: SafeArea(
                  top: false,
                  bottom: true,
                  child: EditorSessionOpsStrip(
                    supportsCompare: true,
                    isComparing: _isComparingSessionBaseline,
                    onCompareStart: () => setState(
                      () => _isComparingSessionBaseline = true,
                    ),
                    onCompareEnd: () => setState(
                      () => _isComparingSessionBaseline = false,
                    ),
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  List<double> _buildLocalAnchorColorMatrix(LocalAnchor anchor) {
    return _buildBaseColorMatrixFromValues(anchor.values);
  }

  List<Widget> _buildLocalPreviewLayers(Widget content, Rect imageRect) {
    if (imageRect.isEmpty) return const [];
    final sourceAnchors = _isComparingSessionBaseline ? _localSnapshotAnchors : _localAnchors;
    final layers = <Widget>[];
    for (final anchor in sourceAnchors) {
      final hasEffect =
          anchor.values.values.any((value) => value.abs() > 0.001);
      if (!hasEffect) continue;
      final center = Offset(
        imageRect.left + anchor.center.dx * imageRect.width,
        imageRect.top + anchor.center.dy * imageRect.height,
      );
      final radius = (anchor.radius * math.min(imageRect.width, imageRect.height))
          .clamp(AppSpacing.iconLarge.toDouble(), imageRect.longestSide);
      layers.add(
        Positioned.fill(
          child: IgnorePointer(
            child: ShaderMask(
              blendMode: BlendMode.dstIn,
              shaderCallback: (_) => ui.Gradient.radial(
                center,
                radius,
                <Color>[
                  AppColors.white,
                  AppColors.white.withValues(alpha: 0.90),
                  AppColors.white.withValues(alpha: 0.58),
                  AppColors.white.withValues(alpha: 0.22),
                  Colors.transparent,
                ],
                const <double>[0.0, 0.22, 0.56, 0.84, 1.0],
              ),
              child: ColorFiltered(
                colorFilter: ColorFilter.matrix(_buildLocalAnchorColorMatrix(anchor)),
                child: content,
              ),
            ),
          ),
        ),
      );
    }
    return layers;
  }

  List<Widget> _buildLocalRangeOverlays(Rect imageRect) {
    if (imageRect.isEmpty) return const [];
    final overlays = <Widget>[];
    for (final anchor in _localAnchors) {
      final center = Offset(
        imageRect.left + anchor.center.dx * imageRect.width,
        imageRect.top + anchor.center.dy * imageRect.height,
      );
      final radius = (anchor.radius * math.min(imageRect.width, imageRect.height))
          .clamp(AppSpacing.iconLarge.toDouble(), imageRect.longestSide);
      overlays.add(
        Positioned(
          left: center.dx - radius,
          top: center.dy - radius,
          child: IgnorePointer(
            child: ClipOval(
              child: BackdropFilter(
                filter: ui.ImageFilter.blur(sigmaX: 6, sigmaY: 6),
                child: Container(
                  width: radius * 2,
                  height: radius * 2,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: AppColors.white.withValues(alpha: 0.06),
                    border: Border.all(
                      color: AppColors.white.withValues(alpha: 0.28),
                      width: AppSpacing.xs / 3,
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      );
    }
    return overlays;
  }

  List<Widget> _buildLocalAnchorWidgets(Rect imageRect) {
    if (imageRect.isEmpty) return const [];
    final widgets = <Widget>[];
    final selectedId = _selectedLocalAnchorId;
    final visibleAnchors = _localShowAllAnchors
        ? _localAnchors
        : _localAnchors
            .where((anchor) => anchor.id == selectedId)
            .toList(growable: false);
    for (final anchor in visibleAnchors) {
      final anchorCenter = Offset(
        imageRect.left + anchor.center.dx * imageRect.width,
        imageRect.top + anchor.center.dy * imageRect.height,
      );
      final center = _draggingAnchorId == anchor.id && _draggingAnchorCenter != null
          ? _draggingAnchorCenter!
          : anchorCenter;
      final isSelected = anchor.id == selectedId;
      final anchorSize = AppSpacing.iconLarge + AppSpacing.xs * 2;
      widgets.add(
        Positioned(
          left: center.dx - anchorSize / 2,
          top: center.dy - anchorSize / 2,
          child: GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: () {
              setState(() {
                _selectedLocalAnchorId = anchor.id;
                _localShowAnchorMenu = true;
              });
            },
            onScaleStart: (_) {
              setState(() {
                _selectedLocalAnchorId = anchor.id;
                _localDragging = true;
                _localShowAnchorMenu = false;
                _draggingAnchorId = anchor.id;
                _draggingAnchorCenter = anchorCenter;
                _localMagnifierPoint = center;
                _draggingAnchorBaseRadius = anchor.radius;
              });
            },
            onScaleUpdate: (details) {
              if (_draggingAnchorId != anchor.id) return;
              if (details.pointerCount >= 2) {
                if (!isSelected) return;
                final baseRadius = _draggingAnchorBaseRadius ?? anchor.radius;
                _updateLocalAnchorRadius(anchor.id, baseRadius * details.scale);
                return;
              }
              final base = _draggingAnchorCenter ?? anchorCenter;
              final next = Offset(
                (base.dx + details.focalPointDelta.dx)
                    .clamp(imageRect.left, imageRect.right),
                (base.dy + details.focalPointDelta.dy)
                    .clamp(imageRect.top, imageRect.bottom),
              );
              setState(() {
                _draggingAnchorCenter = next;
                _localMagnifierPoint = next;
              });
            },
            onScaleEnd: (_) {
              final finalPosition = _draggingAnchorCenter;
              if (finalPosition != null && _draggingAnchorId == anchor.id) {
                _updateLocalAnchorPosition(anchor.id, finalPosition, imageRect);
              }
              _draggingAnchorBaseRadius = null;
              setState(() {
                _localDragging = false;
                _localMagnifierPoint = null;
                _draggingAnchorId = null;
                _draggingAnchorCenter = null;
                _recordLocalSessionStep();
              });
            },
            child: _buildLocalAnchorNode(
              anchor: anchor,
              selected: isSelected,
              size: anchorSize,
            ),
          ),
        ),
      );
      if (isSelected && _localShowAnchorMenu && !_localDragging) {
        widgets.add(
          Positioned(
            left: center.dx - AppSpacing.bottomNavHeight,
            top: center.dy - AppSpacing.bottomNavHeight * 1.25,
            child: Material(
              color: Colors.transparent,
              child: Container(
                decoration: BoxDecoration(
                  color: AppColors.white,
                  borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    TextButton(
                      onPressed: _copySelectedLocalAnchor,
                      child: Text(
                        UITextConstants.imageEditorProAnchorCopy,
                        style: TextStyle(color: AppColors.black),
                      ),
                    ),
                    Container(
                      width: AppSpacing.xs / 2,
                      height: AppSpacing.iconLarge,
                      color: AppColors.black.withValues(alpha: 0.12),
                    ),
                    TextButton(
                      onPressed: _deleteSelectedLocalAnchor,
                      child: Text(
                        UITextConstants.imageEditorProAnchorDelete,
                        style: TextStyle(color: AppColors.black),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        );
      }
    }
    return widgets;
  }

  Widget _buildLocalAnchorNode({
    required LocalAnchor anchor,
    required bool selected,
    required double size,
  }) {
    final value = (anchor.values[anchor.selectedParam] ?? 0).clamp(-100.0, 100.0);
    return SizedBox(
      width: size,
      height: size,
      child: CustomPaint(
        painter: _LocalAnchorRingPainter(
          value: value,
          selected: selected,
        ),
        child: Center(
          child: Container(
            width: AppSpacing.iconMedium + AppSpacing.xs,
            height: AppSpacing.iconMedium + AppSpacing.xs,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: selected
                  ? AppColors.white.withValues(alpha: 0.95)
                  : AppColors.white.withValues(alpha: 0.55),
            ),
            alignment: Alignment.center,
            child: Text(
              localParamLetter(anchor.selectedParam),
              style: TextStyle(
                color: AppColors.black,
                fontSize: AppTypography.sm,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildLocalMagnifier(Offset point) {
    final diameter = MediaQuery.sizeOf(context).width / 3;
    final x = (point.dx - diameter / 2).clamp(
      AppSpacing.containerSm,
      MediaQuery.sizeOf(context).width - diameter - AppSpacing.containerSm,
    );
    return Positioned(
      left: x,
      top: AppSpacing.containerMd,
      child: IgnorePointer(
        child: Container(
          width: diameter,
          height: diameter,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: AppColors.black.withValues(alpha: 0.28),
            border: Border.all(
              color: AppColors.white.withValues(alpha: 0.9),
              width: AppSpacing.xs / 2,
            ),
          ),
          alignment: Alignment.center,
          child: Icon(
            Icons.add,
            color: AppColors.white,
            size: AppSpacing.iconLarge,
          ),
        ),
      ),
    );
  }

  Future<void> _handleHslPickerTap(Offset localPosition, Size imageSize) async {
    final imageRect = _resolveImageRect(imageSize);
    if (!imageRect.contains(localPosition)) {
      setState(() => _hslPickerPoint = null);
      return;
    }
    final nx = ((localPosition.dx - imageRect.left) / imageRect.width).clamp(0.0, 1.0);
    final ny = ((localPosition.dy - imageRect.top) / imageRect.height).clamp(0.0, 1.0);
    final hue = await _sampleImageHueAt(Offset(nx, ny));
    if (!mounted || hue == null) return;
    setState(() {
      _hslPickerPoint = localPosition;
      _selectedHslChannel = hslChannelKeyFromHue(hue);
    });
  }

  Future<double?> _sampleImageHueAt(Offset normalized) async {
    try {
      final bytes = await _loadImageBytes(_currentPath);
      if (bytes.isEmpty) return null;
      final codec = await ui.instantiateImageCodec(bytes);
      final frame = await codec.getNextFrame();
      final image = frame.image;
      final data = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
      if (data == null) return null;
      final x = (normalized.dx * (image.width - 1)).round().clamp(0, image.width - 1);
      final y = (normalized.dy * (image.height - 1)).round().clamp(0, image.height - 1);
      final offset = (y * image.width + x) * 4;
      final r = data.getUint8(offset);
      final g = data.getUint8(offset + 1);
      final b = data.getUint8(offset + 2);
      return HSVColor.fromColor(Color.fromARGB(255, r, g, b)).hue;
    } catch (_) {
      return null;
    }
  }

  /// 裁剪框与九宫格辅助线
  Widget _buildCropOverlay() {
    return LayoutBuilder(
      builder: (context, constraints) {
        final size = Size(constraints.maxWidth, constraints.maxHeight);
        final baseImageRect = _resolveImageRect(size);
        _cropLayoutSize = size;
        _cropImageRect = baseImageRect;
        final cropRect = _resolveCropRect(baseImageRect);
        return Stack(
          children: [
            IgnorePointer(child: _buildCropMask(size, cropRect)),
            Positioned.fromRect(
              rect: cropRect,
              child: IgnorePointer(child: _buildCropFrame()),
            ),
            if (_cropRatio == 'free')
              ..._buildCropHandles(cropRect, baseImageRect),
          ],
        );
      },
    );
  }

  Widget _buildCropMask(Size size, Rect rect) {
    final overlayColor = AppColors.overlayMedium;
    return Stack(
      children: [
        Positioned(
          left: 0,
          top: 0,
          right: 0,
          height: rect.top,
          child: ColoredBox(color: overlayColor),
        ),
        Positioned(
          left: 0,
          top: rect.top,
          width: rect.left,
          height: rect.height,
          child: ColoredBox(color: overlayColor),
        ),
        Positioned(
          right: 0,
          top: rect.top,
          width: size.width - rect.right,
          height: rect.height,
          child: ColoredBox(color: overlayColor),
        ),
        Positioned(
          left: 0,
          top: rect.bottom,
          right: 0,
          height: size.height - rect.bottom,
          child: ColoredBox(color: overlayColor),
        ),
      ],
    );
  }

  Widget _buildCropFrame() {
    // 与旋转宫格一致：内部线 xs/4、半透明白，外框略粗、同色，降低干扰
    const gridAlpha = 0.35;
    final gridColor = AppColors.white.withValues(alpha: gridAlpha);
    final lineWidth = AppSpacing.xs / 4;
    return Container(
      decoration: BoxDecoration(
        border: Border.all(
          color: gridColor,
          width: AppSpacing.xs / 2,
        ),
      ),
      child: Column(
        children: [
          Expanded(child: _buildCropGridRow(lineWidth, gridColor)),
          Container(height: lineWidth, color: gridColor),
          Expanded(child: _buildCropGridRow(lineWidth, gridColor)),
          Container(height: lineWidth, color: gridColor),
          Expanded(child: _buildCropGridRow(lineWidth, gridColor)),
        ],
      ),
    );
  }

  Widget _buildCropGridRow(double lineWidth, Color lineColor) {
    return Row(
      children: [
        const Expanded(child: SizedBox.shrink()),
        Container(width: lineWidth, color: lineColor),
        const Expanded(child: SizedBox.shrink()),
        Container(width: lineWidth, color: lineColor),
        const Expanded(child: SizedBox.shrink()),
      ],
    );
  }

  Rect _resolveImageRect(Size size) {
    final ratio = _imageAspectRatio;
    if (ratio == null || ratio == 0) {
      return Offset.zero & size;
    }
    final containerRatio = size.width / size.height;
    double width;
    double height;
    if (ratio > containerRatio) {
      width = size.width;
      height = width / ratio;
    } else {
      height = size.height;
      width = height * ratio;
    }
    final left = (size.width - width) / 2;
    final top = (size.height - height) / 2;
    return Rect.fromLTWH(left, top, width, height);
  }

  List<Widget> _buildCropHandles(Rect rect, Rect imageRect) {
    final hitSize = AppSpacing.lg;
    return [
      Positioned(
        left: rect.left - hitSize / 2,
        top: rect.top,
        width: hitSize,
        height: rect.height,
        child: GestureDetector(
          behavior: HitTestBehavior.translucent,
          onPanUpdate: (details) =>
              _updateCropRect(_CropEdge.left, details.delta, imageRect),
        ),
      ),
      Positioned(
        right: imageRect.right - rect.right - hitSize / 2,
        top: rect.top,
        width: hitSize,
        height: rect.height,
        child: GestureDetector(
          behavior: HitTestBehavior.translucent,
          onPanUpdate: (details) =>
              _updateCropRect(_CropEdge.right, details.delta, imageRect),
        ),
      ),
      Positioned(
        left: rect.left,
        top: rect.top - hitSize / 2,
        width: rect.width,
        height: hitSize,
        child: GestureDetector(
          behavior: HitTestBehavior.translucent,
          onPanUpdate: (details) =>
              _updateCropRect(_CropEdge.top, details.delta, imageRect),
        ),
      ),
      Positioned(
        left: rect.left,
        top: rect.bottom - hitSize / 2,
        width: rect.width,
        height: hitSize,
        child: GestureDetector(
          behavior: HitTestBehavior.translucent,
          onPanUpdate: (details) =>
              _updateCropRect(_CropEdge.bottom, details.delta, imageRect),
        ),
      ),
    ];
  }

  Rect _resolveCropRect(Rect imageRect) {
    if (_cropRatio == 'free') {
      return Rect.fromLTRB(
        imageRect.left + _cropRect.left * imageRect.width,
        imageRect.top + _cropRect.top * imageRect.height,
        imageRect.left + _cropRect.right * imageRect.width,
        imageRect.top + _cropRect.bottom * imageRect.height,
      );
    }
    final ratio = _ratioForCrop(_cropRatio) ??
        (imageRect.width / imageRect.height);
    double width = imageRect.width;
    double height = width / ratio;
    if (height > imageRect.height) {
      height = imageRect.height;
      width = height * ratio;
    }
    final left = imageRect.left + (imageRect.width - width) / 2;
    final top = imageRect.top + (imageRect.height - height) / 2;
    return Rect.fromLTWH(left, top, width, height);
  }

  double? _ratioForCrop(String ratio) {
    switch (ratio) {
      case 'original':
        return _imageAspectRatio;
      case '1x1':
        return 1;
      case '2x3':
        return 2 / 3;
      case '3x2':
        return 3 / 2;
      case '3x4':
        return 3 / 4;
      case '4x3':
        return 4 / 3;
      case '9x16':
        return 9 / 16;
      case '16x9':
        return 16 / 9;
      default:
        return null;
    }
  }

  void _updateCropRect(_CropEdge edge, Offset delta, Rect imageRect) {
    final minSize = AppSpacing.bottomNavHeight;
    final minWidth = minSize / imageRect.width;
    final minHeight = minSize / imageRect.height;
    var left = _cropRect.left;
    var top = _cropRect.top;
    var right = _cropRect.right;
    var bottom = _cropRect.bottom;
    final dx = delta.dx / imageRect.width;
    final dy = delta.dy / imageRect.height;
    switch (edge) {
      case _CropEdge.left:
        left = (left + dx).clamp(0.0, right - minWidth);
        break;
      case _CropEdge.right:
        right = (right + dx).clamp(left + minWidth, 1.0);
        break;
      case _CropEdge.top:
        top = (top + dy).clamp(0.0, bottom - minHeight);
        break;
      case _CropEdge.bottom:
        bottom = (bottom + dy).clamp(top + minHeight, 1.0);
        break;
    }
    setState(() {
      _cropRect = Rect.fromLTRB(left, top, right, bottom);
      _cropEdited = _isCropStateDirty();
    });
  }

  void _updateCropImageOffset(Offset delta) {
    if (_cropRatio == 'free') return;
    final baseRect = _cropImageRect;
    if (baseRect.isEmpty) {
      setState(() {
        _cropImageOffset += delta;
        _cropEdited = _isCropStateDirty();
      });
      return;
    }
    final cropRect = _resolveCropRect(baseRect);
    final maxDx = cropRect.left - baseRect.left;
    final minDx = cropRect.right - baseRect.right;
    final maxDy = cropRect.top - baseRect.top;
    final minDy = cropRect.bottom - baseRect.bottom;
    final next = _cropImageOffset + delta;
    final clamped = Offset(
      next.dx.clamp(minDx, maxDx),
      next.dy.clamp(minDy, maxDy),
    );
    setState(() {
      _cropImageOffset = clamped;
      _cropEdited = _isCropStateDirty();
    });
  }

  Offset _clampCropOffset(Offset offset) {
    final baseRect = _cropImageRect;
    if (baseRect.isEmpty) return offset;
    final cropRect = _resolveCropRect(baseRect);
    final maxDx = cropRect.left - baseRect.left;
    final minDx = cropRect.right - baseRect.right;
    final maxDy = cropRect.top - baseRect.top;
    final minDy = cropRect.bottom - baseRect.bottom;
    return Offset(
      offset.dx.clamp(minDx, maxDx),
      offset.dy.clamp(minDy, maxDy),
    );
  }

  Widget _buildRotateGridOverlay() {
    return ImageEditorRotateOverlay(
      rotateFineDegrees: _rotateFineDegrees,
      isRotateEdited: _isRotateEdited,
      imageAspectRatio: _imageAspectRatio ?? 1,
      onFineDragUpdate: _setRotateFineDegrees,
    );
  }

  void _onDone() async {
    if (_hasProBaseAdjustments ||
        _hasProHslAdjustments ||
        _hasBwLevelsAdjustments ||
        _hasLocalAdjustments) {
      final adjustedPath = await _applyProAdjustmentsToCurrentImage();
      if (adjustedPath != null) {
        _paths[_currentIndex] = adjustedPath;
        _clearFilterPreviewCache();
      }
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
    if (_isMultiImage) {
      result = <String, dynamic>{'index': _currentIndex, 'path': _currentPath};
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
    final bg = AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary);
    final fg = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: bg,
      builder: (context) {
        return SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Padding(
                padding: EdgeInsets.all(
                  AppSpacing.semantic[DesignSemanticConstants.container]
                          ?[DesignSemanticConstants.md] ??
                      AppSpacing.containerMd,
                ),
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
                    IconButton(
                      icon: Icon(Icons.close, color: fgSecondary),
                      onPressed: () => Navigator.of(context).pop(),
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
                        _stepTypeLabel(step.type, step.params),
                        style: TextStyle(color: fg),
                      ),
                      trailing: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          IconButton(
                            icon: Icon(
                              Icons.refresh,
                              color: fgSecondary,
                              size: AppSpacing.iconSmall,
                            ),
                            onPressed: () {
                              Navigator.of(context).pop();
                              _redoStepAt(index);
                            },
                            tooltip: UITextConstants.imageEditorRedoStep,
                          ),
                          IconButton(
                            icon: Icon(
                              Icons.delete_outline,
                              color: fgSecondary,
                              size: AppSpacing.iconSmall,
                            ),
                            onPressed: () {
                              _removeStepAt(index);
                              Navigator.of(context).pop();
                            },
                            tooltip: UITextConstants.imageEditorRemoveStep,
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

class _LocalAnchorRingPainter extends CustomPainter {
  const _LocalAnchorRingPainter({
    required this.value,
    required this.selected,
  });

  final double value;
  final bool selected;

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = (math.min(size.width, size.height) / 2) - AppSpacing.xs / 2;
    final basePaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = AppSpacing.xs / 2
      ..color = AppColors.white.withValues(alpha: selected ? 0.25 : 0.14);
    canvas.drawCircle(center, radius, basePaint);

    final t = (value.abs() / 100).clamp(0.0, 1.0);
    if (t <= 0) return;
    final sweep = math.pi * 2 * t;
    final arcPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = AppSpacing.xs / 2
      ..strokeCap = StrokeCap.round
      ..color = (value >= 0 ? AppColors.white : AppColors.black)
          .withValues(alpha: selected ? 0.95 : 0.60);
    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      -math.pi / 2,
      value >= 0 ? sweep : -sweep,
      false,
      arcPaint,
    );
  }

  @override
  bool shouldRepaint(covariant _LocalAnchorRingPainter oldDelegate) {
    return oldDelegate.value != value || oldDelegate.selected != selected;
  }
}

class _ProToolboxEntry {
  const _ProToolboxEntry({
    required this.icon,
    required this.label,
    required this.category,
    this.placeholderTitle,
    this.semanticIconKey,
  });

  final IconData icon;
  final String label;
  final int category;
  final String? placeholderTitle;
  final String? semanticIconKey;
}

enum _CropEdge { left, right, top, bottom }
