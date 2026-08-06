import 'dart:math' as math;
import 'dart:async';
import 'dart:ui' as ui;

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/observability/analytics.dart';
import 'package:quwoquan_app/runtime/observability/trackers/page_lifecycle_observability.dart';
import 'package:quwoquan_app/design_system/surfaces/app_action_sheet.dart';
import 'package:quwoquan_app/design_system/surfaces/app_modal_presenter.dart';
import 'package:quwoquan_app/design_system/surfaces/app_modal_surface.dart';
import 'package:quwoquan_app/design_system/layout/app_scaffold.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/design_system/semantics/design_semantic_constants.dart';
import 'package:quwoquan_app/design_system/semantics/settings_semantic_constants.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/platform/local_image_provider.dart';
import 'package:quwoquan_app/runtime/platform/temporary_file_writer.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/presentation/image_editor_step.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/presentation/image_editor_step_payload.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/presentation/image_editor_page_params.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/presentation/image_editor_export_engine.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/presentation/image_editor_step_stack.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/presentation/image_editor_top_bar.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/presentation/image_editor_bottom_bar.dart';
import 'package:quwoquan_app/design_system/media/image_editor_semantic_icon.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/application/public/image_editor_filter_catalog.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/application/public/image_editor_filter_models.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/adapters/image_editor_filter_feature_extractor.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/adapters/image_editor_filter_recommendation_models.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/adapters/image_editor_filter_recommender.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/application/public/image_editor_filter_matrix.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/presentation/image_editor_curve_models.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/presentation/image_editor_hsl_models.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/presentation/image_editor_local_models.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/presentation/image_editor_mosaic_models.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/presentation/image_editor_text_models.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/presentation/image_editor_operation_panel.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/presentation/image_editor_rotate_overlay.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/presentation/editor_session_ops_strip.dart';
import 'package:quwoquan_app/design_system/media/media_reorderable_view.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/presentation/image_editor_tool_constants.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/presentation/image_editor_pro_tool_entries.dart';

part 'image_editor_page_filter_logic.dart';
part 'image_editor_page_history_logic.dart';
part 'image_editor_page_pro_tools.dart';
part 'image_editor_page_pro_adjustments.dart';
part 'image_editor_page_crop_rotate.dart';
part 'image_editor_page_curve_wb.dart';
part 'image_editor_page_mosaic_text.dart';
part 'image_editor_page_preview_layers.dart';
part 'image_editor_page_completion.dart';
part 'image_editor_page_color_matrices.dart';
part 'image_editor_page_local_preview_layers.dart';
part 'image_editor_page_crop_overlay.dart';

/// 图片编辑器页面（三段式布局：顶栏、中部图片、底栏工具）
///
/// 路由：/create/edit-image?path=...&source=...&index=...&total=...
/// 返回：顶栏「完成」pop(editedPath / payload)；back 有修改时确认后 pop(null) 放弃。
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
    this.filterRepository,
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
  final ImageEditorFilterCatalog? filterRepository;

  /// 嵌入式时使用：返回/取消时调用，不执行 context.pop
  final VoidCallback? onBack;

  /// 嵌入式时使用：完成时传入结果（String 或 Map），不执行 context.pop
  final void Function(Object? result)? onDone;

  @override
  ConsumerState<ImageEditorPage> createState() => _ImageEditorPageState();
}

class _ImageEditorPageState extends ConsumerState<ImageEditorPage> {
  static const int _kLocalAnchorMaxCount = 10;
  static const String _kPageName = 'media.image_editor';
  static const String _kSurfaceId = 'imageEditor';

  List<String> _paths = const [];
  List<String> _initialPaths = const [];
  int _currentIndex = 0;
  PageController? _pageController;
  ScrollController? _thumbScrollController;

  late final PageLifecycleObservability _observability;
  late final AnalyticsService _analytics;
  DateTime? _pageEnterTime;

  void _setEditorState(VoidCallback fn) => setState(fn);

  Future<void> _showEditorActionFailure({
    required String title,
    String? message,
  }) async {
    _observability.recordPageState(
      pageName: _kPageName,
      phase: 'failure',
      surface: _kSurfaceId,
      copyKey: title,
    );
    if (!mounted) {
      return;
    }
    await showAppActionSheet<bool>(
      context,
      title: title,
      message: message ?? CreationText.operationFailed,
      sections: const <AppActionSheetSection<bool>>[
        AppActionSheetSection<bool>(
          items: <AppActionSheetItem<bool>>[
            AppActionSheetItem<bool>(
              label: FoundationText.confirm,
              value: true,
            ),
          ],
        ),
      ],
    );
  }

  @override
  void initState() {
    super.initState();
    _filterRepository =
        widget.filterRepository ??
        ref.read(imageEditorFilterRepositoryProvider);
    _observability = ref.read(pageLifecycleObservabilityProvider);
    _analytics = ref.read(analyticsProvider);
    _pageEnterTime = DateTime.now();
    _syncPaths(resetIndex: true);
    _initialPaths = List<String>.of(_paths);
    _primeInitialFilterSelection();
    _loadImageAspectRatio(_currentPath);
    _observability.recordPageState(
      pageName: _kPageName,
      phase: 'enter',
      surface: _kSurfaceId,
      itemCount: _paths.length,
    );
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
      _initialPaths = List<String>.of(_paths);
      _stepStack.clear();
    }
  }

  @override
  void dispose() {
    final enterTime = _pageEnterTime;
    _observability.recordPageState(
      pageName: _kPageName,
      phase: 'exit',
      surface: _kSurfaceId,
      durationMs: enterTime == null
          ? null
          : DateTime.now().difference(enterTime).inMilliseconds,
      itemCount: _stepStack.length,
    );
    _pageController?.dispose();
    _thumbScrollController?.dispose();
    _proToolScrollController.dispose();
    _cropRatioScrollController.dispose();
    _filterTemplateScrollController.dispose();
    _disposeCurveSessionResources();
    _disposeMosaicSessionResources();
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

  /// 已提交步骤 + 撤销/重做栈（文件快照语义）。
  final ImageEditorStepStack _stepStack = ImageEditorStepStack();

  /// 提交转码去重缓存与防重入标记。
  final Map<String, String> _deliveryJpegCache = <String, String>{};
  bool _submittingDone = false;

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
  late final ImageEditorFilterCatalog _filterRepository;
  bool _filterCatalogLoading = false;
  bool _filterCatalogLoadFailed = false;
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
  final Set<int> _filterTemplatePreviewFailed = <int>{};
  final Set<int> _filterVisibleIndices = <int>{};
  final List<int> _filterPreviewQueue = <int>[];
  bool _processingFilterPreviewQueue = false;
  ImageEditorFilterImageFeatures? _filterImageFeatures;
  String? _filterImageFeaturesPath;

  /// 马赛克会话：类型、笔刷大小（滑杆 0..1）、笔画列表与预览资源
  ImageEditorMosaicType _mosaicType = ImageEditorMosaicType.pixelate;
  double _mosaicBrushSize = 0.5;
  final List<ImageEditorMosaicStroke> _mosaicStrokes =
      <ImageEditorMosaicStroke>[];
  ImageEditorMosaicStroke? _activeMosaicStroke;
  ui.Image? _mosaicPreviewPixelated;
  ui.Image? _mosaicPreviewBlurred;
  bool _mosaicPreviewLoading = false;

  /// 文字会话：图上文字项与选中态
  final List<ImageEditorTextItem> _textItems = <ImageEditorTextItem>[];
  int? _selectedTextItemId;
  int _textIdSeed = 0;

  /// 旋转：当前角度（度）
  int _rotateDegrees = 0;

  /// 专业修图：当前二级分组（整体/局部/HSL/曲线/白平衡/黑白色阶）
  int _selectedProCategory = kImageEditorProCategoryOverall;

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

  /// 曲线会话：状态、通道、预览资源与直方图
  ImageEditorCurvesState _curvesState = ImageEditorCurvesState();
  ImageEditorCurvesState _curvesSnapshot = ImageEditorCurvesState();
  ImageEditorCurveChannel _curveChannel = ImageEditorCurveChannel.rgb;
  ui.Image? _curvePreviewBase;
  Uint8List? _curvePreviewBaseRgba;
  ui.Image? _curvePreviewImage;
  List<int>? _curveHistogram;
  bool _curvePreviewDirty = false;
  bool _curvePreviewComputing = false;

  /// 白平衡会话：色温/色调（-100..100）
  double _wbTemperature = 0;
  double _wbTint = 0;
  double _wbSnapshotTemperature = 0;
  double _wbSnapshotTint = 0;

  /// 专业修图工具横向滚动控制器
  final ScrollController _proToolScrollController = ScrollController();

  /// 剪裁比例列表横向滚动，重置时滚回「原始」
  final ScrollController _cropRatioScrollController = ScrollController();

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
    final bottomPad = math.max(
      MediaQuery.paddingOf(context).bottom,
      AppSpacing.containerMd,
    );
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
                    canUndo: _stepStack.canUndo,
                    canRedo: _stepStack.canRedo,
                    onUndo: _undoLastStep,
                    onRedo: _redoLastUndoneStep,
                    onHistory: _showHistorySheet,
                    historyEnabled: _stepStack.length > 0,
                    onDone: () => _onDone(),
                  )
                else
                  const SizedBox.shrink(),
                // 2. 中部：工具编辑页仅对当前图编辑、不可左右滑动；主界面可多图滑动
                Expanded(
                  child: _selectedToolIndex != null
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
                if (_selectedToolIndex != null)
                  ImageEditorOperationPanel(
                    backgroundColor: panelBg,
                    foregroundColor: fg,
                    foregroundSecondary: fgSecondary,
                    bottomInset: bottomPad,
                    toolIndex: _selectedToolIndex ?? kImageEditorToolCrop,
                    selectedProCategory: _selectedProCategory,
                    proToolScrollController: _proToolScrollController,
                    onSelectProCategory: (index) {
                      setState(() {
                        _selectedProCategory = index;
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
                        if (index == kImageEditorProCategoryCurve) {
                          _prepareCurveSession();
                        }
                      });
                    },
                    onExitProPanel: _cancelProPanel,
                    onConfirmProPanel: _confirmProPanel,
                    onCancelPanel: _selectedToolIndex == kImageEditorToolCrop
                        ? _cancelCropAndExit
                        : _selectedToolIndex == kImageEditorToolRotate
                        ? _cancelRotateAndExit
                        : _selectedToolIndex == kImageEditorToolFilter
                        ? _cancelFilterAndExit
                        : _selectedToolIndex == kImageEditorToolMosaic
                        ? _cancelMosaicAndExit
                        : _selectedToolIndex == kImageEditorToolText
                        ? _cancelTextAndExit
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
                    filterCatalogLoading: _filterCatalogLoading,
                    filterCatalogLoadFailed: _filterCatalogLoadFailed,
                    onFilterCatalogRetry: _initFilterConfig,
                    mosaicType: _mosaicType,
                    mosaicBrushSize: _mosaicBrushSize,
                    onMosaicTypeChanged: (type) =>
                        setState(() => _mosaicType = type),
                    onMosaicBrushSizeChanged: (v) =>
                        setState(() => _mosaicBrushSize = v),
                    mosaicHasStrokes: _mosaicStrokes.isNotEmpty,
                    onMosaicUndoStroke: _undoLastMosaicStroke,
                    textItems: _textItems,
                    selectedTextItem: _selectedTextItem,
                    onTextAdd: _promptAddTextItem,
                    onTextStyleChanged: _updateSelectedTextStyle,
                    onTextColorChanged: _updateSelectedTextColor,
                    onTextDelete: _deleteSelectedTextItem,
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
                    curvesState: _curvesState,
                    curveChannel: _curveChannel,
                    curveHistogram: _curveHistogram,
                    onCurveChannelChanged: (channel) =>
                        setState(() => _curveChannel = channel),
                    onCurvesChanged: _onCurvesChanged,
                    onCurveResetChannel: _resetCurrentCurveChannel,
                    wbTemperature: _wbTemperature,
                    wbTint: _wbTint,
                    onWbTemperatureChanged: (v) =>
                        setState(() => _wbTemperature = v.clamp(-100.0, 100.0)),
                    onWbTintChanged: (v) =>
                        setState(() => _wbTint = v.clamp(-100.0, 100.0)),
                    onWbAuto: _applyAutoWhiteBalance,
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
                    onNextStep: () => _onDone(action: 'continueToCreate'),
                    onToolSelected: _onBottomToolSelected,
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

  void _onBottomToolSelected(int index) {
    setState(() {
      _showProToolbox = false;
      _selectedToolIndex = index;
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
      if (index == kImageEditorToolMosaic) {
        _prepareMosaicSession();
      }
      if (index == kImageEditorToolText) {
        _prepareTextSession();
      }
      if (index == kImageEditorToolPro) {
        _selectedToolIndex = null;
        _selectedProCategory = kImageEditorProCategoryOverall;
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
      if (_filterConfig == null && !_filterCatalogLoading) {
        unawaited(_initFilterConfig());
      } else {
        unawaited(_rebuildFilterData());
      }
    }
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

enum _CropEdge { left, right, top, bottom }
