import 'dart:io';
import 'dart:math' as math;
import 'dart:async';
import 'dart:ui' as ui;

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:path_provider/path_provider.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/components/media/image/editor/models/image_editor_step.dart';
import 'package:quwoquan_app/components/media/image/editor/image_editor_page_params.dart';
import 'package:quwoquan_app/components/media/image/editor/top_bar/image_editor_top_bar.dart';
import 'package:quwoquan_app/components/media/image/editor/bottom_bar/image_editor_bottom_bar.dart';
import 'package:quwoquan_app/components/media/image/editor/icons/image_editor_semantic_icon.dart';
import 'package:quwoquan_app/components/media/image/editor/panels/image_editor_curve_overlay_bar.dart';
import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_models.dart';
import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_feature_extractor.dart';
import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_recommendation_models.dart';
import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_recommender.dart';
import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_repository.dart';
import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_matrix.dart';
import 'package:quwoquan_app/components/media/image/editor/panels/hsl/image_editor_hsl_models.dart';
import 'package:quwoquan_app/components/media/image/editor/panels/local/image_editor_local_models.dart';
import 'package:quwoquan_app/components/media/image/editor/panels/image_editor_operation_panel.dart';
import 'package:quwoquan_app/components/media/image/editor/panels/image_editor_rotate_overlay.dart';
import 'package:quwoquan_app/components/media/image/editor/shared/editor_session_ops_strip.dart';
import 'package:quwoquan_app/components/media/reorderable/media_reorderable_view.dart';
import 'package:quwoquan_app/components/media/image/editor/tool_list/image_editor_tool_constants.dart';
import 'package:quwoquan_app/components/media/image/editor/tool_list/image_editor_pro_tool_entries.dart';

part 'image_editor_page_filter_logic.dart';
part 'image_editor_page_history_logic.dart';
part 'image_editor_page_pro_tools.dart';
part 'image_editor_page_pro_adjustments.dart';
part 'image_editor_page_crop_rotate.dart';
part 'image_editor_page_preview_layers.dart';
part 'image_editor_page_completion.dart';
part 'image_editor_page_color_matrices.dart';
part 'image_editor_page_local_preview_layers.dart';
part 'image_editor_page_crop_overlay.dart';

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
    this.initialFilterPresetId,
    this.initialFilterStrength,
    this.onBack,
    this.onDone,
  });

  final String initialPath;
  final String source;
  final int index;
  final int total;

  /// 多图时传入全部路径，用于大图左右滑动与缩略图联动
  final List<String>? imagePaths;
  final String? initialFilterPresetId;
  final double? initialFilterStrength;

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

  Future<void> _showEditorActionFailure({
    required String title,
    String? message,
  }) async {
    if (!mounted) {
      return;
    }
    await AppActionErrorFeedback.show(
      context,
      semantic: UiErrorSemantic(
        category: UiErrorCategory.submit,
        scope: UiErrorScope.global,
        title: title,
        message: message ?? UITextConstants.operationFailed,
        primaryAction: const UiErrorAction(
          type: UiErrorActionType.dismiss,
          label: UITextConstants.confirm,
        ),
        dismissible: true,
      ),
    );
  }

  int _currentIndex = 0;
  PageController? _pageController;
  ScrollController? _thumbScrollController;

  void _setEditorState(VoidCallback fn) => setState(fn);

  @override
  void initState() {
    super.initState();
    _syncPaths(resetIndex: true);
    _primeInitialFilterSelection();
    _loadImageAspectRatio(_currentPath);
    _initFilterConfig();
  }

  void _primeInitialFilterSelection() {
    final presetId = widget.initialFilterPresetId?.trim();
    if (presetId == null || presetId.isEmpty || presetId == 'original') {
      return;
    }
    final strength = (widget.initialFilterStrength ?? 100).clamp(0, 100);
    _selectedFilterPresetId = presetId;
    _filterIntensity = strength.toDouble();
    _filterStrengthByPresetId[presetId] = strength.toDouble();
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
      _currentIndex = widget.index.clamp(
        0,
        (_paths.length - 1).clamp(0, 0x7fffffff),
      );
    } else {
      _currentIndex = _currentIndex.clamp(
        0,
        (_paths.length - 1).clamp(0, 0x7fffffff),
      );
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

  /// 是否在图片下方展示曲线调节蒙皮（专业修图-曲线子工具选中时）
  bool get _showCurveOverlayBelowImage => false;

  /// 编辑步骤栈（Snapseed 式记录）
  final List<ImageEditorStep> _steps = [];

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
  List<ImageEditorFilterCategory> _filterCategories =
      const <ImageEditorFilterCategory>[];
  List<ImageEditorFilterPreset> _filterPresets =
      const <ImageEditorFilterPreset>[];
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
  Map<String, Map<String, double>> _proHslSnapshotValues =
      createDefaultHslValues();

  /// HSL：会话基线（用于对比原图）
  Map<String, Map<String, double>> _hslSessionBaselineValues =
      createDefaultHslValues();

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
    final fg = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final topPad = MediaQuery.paddingOf(context).top;
    final bottomPad = MediaQuery.paddingOf(context).bottom;
    final isToolEditing = _selectedToolIndex != null;
    // 顶栏纯黑；状态栏纯黑且图标略降对比（通过深灰背景弱化白图标）
    final topBarBg = AppColors.black;
    SystemChrome.setEnabledSystemUIMode(
      SystemUiMode.manual,
      overlays: isToolEditing
          ? [SystemUiOverlay.bottom]
          : SystemUiOverlay.values,
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

    return AppScaffold(
      backgroundColor: baseBg,
      child: SafeArea(
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
                            Expanded(child: _buildMiddleImage(fgSecondary)),
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
                                _pushStep(
                                  ImageEditorStep(
                                    type: 'proTools',
                                    params: {
                                      'subType': 'curve',
                                      'curveBrightness': _curveBrightness,
                                      'curveContrast': _curveContrast,
                                    },
                                  ),
                                );
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
                              _paths[index],
                              fgSecondary,
                            );
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
                    onCancelProTool: () => _cancelProPanel(),
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
                    filterTemplatePreviewLoadingIndices:
                        _filterTemplatePreviewLoading,
                    filterTemplateScrollController:
                        _filterTemplateScrollController,
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
                    onTextStyleChanged: (i) =>
                        setState(() => _textStyleIndex = i),
                    onTextColorChanged: (i) =>
                        setState(() => _textColorIndex = i),
                    rotateDegrees: _rotateDegrees,
                    rotateFineDegrees: _rotateFineDegrees,
                    flipHorizontal: _flipHorizontal,
                    flipVertical: _flipVertical,
                    onRotateLeft: () => setState(
                      () => _rotateDegrees = (_rotateDegrees - 90) % 360,
                    ),
                    onRotateRight: () => setState(
                      () => _rotateDegrees = (_rotateDegrees + 90) % 360,
                    ),
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
                    onBwWhiteLevelChanged: (v) =>
                        _onBwLevelChanged(isWhite: true, value: v),
                    onBwBlackLevelChanged: (v) =>
                        _onBwLevelChanged(isWhite: false, value: v),
                    proBaseSelectedIndex: _selectedProBaseToolIndex,
                    proBaseValues: _proBaseValues,
                    onProBaseSelectedIndexChanged: (index) => setState(() {
                      _selectedProBaseToolIndex = index;
                      if (_selectedProCategory ==
                              kImageEditorProCategoryLocal &&
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
                    onSelectHslChannel: (channelKey) =>
                        setState(() => _selectedHslChannel = channelKey),
                    onHslValueChanged: _onProHslValueChanged,
                    onToggleHslPicker: () =>
                        setState(() => _hslPickerActive = !_hslPickerActive),
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
                    selectedToolIndex: _showProToolbox
                        ? kImageEditorToolPro
                        : _selectedToolIndex,
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
}

class _LocalAnchorRingPainter extends CustomPainter {
  const _LocalAnchorRingPainter({required this.value, required this.selected});

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
      ..color = (value >= 0 ? AppColors.white : AppColors.black).withValues(
        alpha: selected ? 0.95 : 0.60,
      );
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
