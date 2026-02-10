import 'dart:io';
import 'dart:math' as math;
import 'dart:typed_data';
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
import 'package:quwoquan_app/components/media/image/editor/panels/image_editor_curve_overlay_bar.dart';
import 'package:quwoquan_app/components/media/image/editor/panels/image_editor_operation_panel.dart';
import 'package:quwoquan_app/components/media/image/editor/panels/image_editor_rotate_overlay.dart';
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
  List<String> _paths = const [];

  int _currentIndex = 0;
  PageController? _pageController;
  ScrollController? _thumbScrollController;

  @override
  void initState() {
    super.initState();
    _syncPaths(resetIndex: true);
    _loadImageAspectRatio(_currentPath);
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

  /// 是否在图片下方展示曲线调节蒙皮（专业修图-曲线子工具选中时）
  bool get _showCurveOverlayBelowImage =>
      _selectedToolIndex == kImageEditorToolPro &&
      _selectedProToolIndex != null &&
      kImageEditorProToolEntries[_selectedProToolIndex!].type == 'curve';

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
          _scrollToProToolIndex(i);
        }
      } else {
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
  /// 滤镜：分类索引、模板索引、强度 0~1
  int _filterCategoryIndex = 0;
  int _filterTemplateIndex = 0;
  double _filterIntensity = 0.5;
  /// 美颜：模板索引、强度 0~1
  int _beautyTemplateIndex = 0;
  double _beautyIntensity = 0.6;
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

  /// 专业修图：当前二级分组（曝光/色彩/光影/质感）
  int _selectedProCategory = kImageEditorProCategoryExposure;
  /// 专业修图：当前选中的工具索引（为空表示停留在工具列表面板）
  int? _selectedProToolIndex;
  /// 专业修图工具横向滚动控制器
  final ScrollController _proToolScrollController = ScrollController();
  /// 剪裁比例列表横向滚动，重置时滚回「原始」
  final ScrollController _cropRatioScrollController = ScrollController();

  /// 曲线参数（简化：亮度/对比度占位）
  double _curveBrightness = 0.5;
  double _curveContrast = 0.5;
  /// 白平衡参数（色温占位）
  double _whiteBalanceTemp = 0.5;
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
        child: Column(
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
                onDone: _onDone,
                doneEnabled: _steps.isNotEmpty,
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
                proToolScrollController: _proToolScrollController,
                onSelectProTool: (index) => setState(() {
                  _selectedProToolIndex = index;
                }),
                onSelectProCategory: (index) {
                  setState(() => _selectedProCategory = index);
                  _scrollToProCategory(index);
                },
                onProToolScrollSync: _syncProCategoryWithScroll,
                onExitProPanel: _closePanel,
                onConfirmProPanel: _closePanel,
                onCancelProTool: () =>
                    setState(() => _selectedProToolIndex = null),
                onConfirmProTool: _confirmProTool,
                onCancelPanel: _selectedToolIndex == kImageEditorToolCrop
                    ? _cancelCropAndExit
                    : _selectedToolIndex == kImageEditorToolRotate
                        ? _cancelRotateAndExit
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
                onFilterCategoryChanged: (i) =>
                    setState(() => _filterCategoryIndex = i),
                onFilterTemplateChanged: (i) =>
                    setState(() => _filterTemplateIndex = i),
                onFilterIntensityChanged: (v) =>
                    setState(() => _filterIntensity = v),
                beautyTemplateIndex: _beautyTemplateIndex,
                beautyIntensity: _beautyIntensity,
                onBeautyTemplateChanged: (i) =>
                    setState(() => _beautyTemplateIndex = i),
                onBeautyIntensityChanged: (v) =>
                    setState(() => _beautyIntensity = v),
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
              ),
            if (_selectedToolIndex == null)
              ImageEditorBottomBar(
                backgroundColor: panelBg,
                foregroundColor: fg,
                foregroundSecondary: fgSecondary,
                bottomPadding: bottomPad,
                selectedToolIndex: _selectedToolIndex,
                onToolSelected: (index) => setState(() {
                  _selectedToolIndex = index;
                  _selectedProToolIndex = null;
                  if (index == kImageEditorToolCrop) {
                    _prepareCropSnapshot();
                  }
                  if (index == kImageEditorToolRotate) {
                    _applyRotateReset();
                  }
                  if (index == kImageEditorToolPro) {
                    _selectedProCategory = kImageEditorProCategoryExposure;
                    _scrollToProCategory(_selectedProCategory);
                  }
                }),
              ),
          ],
        ),
      ),
    );
  }

  void _handleBack() {
    if (widget.onBack != null) {
      widget.onBack!();
    } else {
      context.pop();
    }
  }

  void _closePanel() {
    setState(() {
      _selectedToolIndex = null;
      _selectedProToolIndex = null;
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
      onError: (_, __) => stream.removeListener(listener),
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
      final absCos = math.cos(radians).abs();
      final absSin = math.sin(radians).abs();
      final newWidth =
          (image.width * absCos + image.height * absSin).ceilToDouble();
      final newHeight =
          (image.width * absSin + image.height * absCos).ceilToDouble();
      final recorder = ui.PictureRecorder();
      final canvas = Canvas(recorder);
      canvas.translate(newWidth / 2, newHeight / 2);
      canvas.rotate(radians);
      canvas.scale(
        _flipHorizontal ? -1.0 : 1.0,
        _flipVertical ? -1.0 : 1.0,
      );
      canvas.translate(-image.width / 2, -image.height / 2);
      canvas.drawImage(image, Offset.zero, Paint());
      final rotatedImage = await recorder
          .endRecording()
          .toImage(newWidth.round(), newHeight.round());
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

  void _confirmProTool() {
    if (_selectedProToolIndex == null) return;
    final entry = kImageEditorProToolEntries[_selectedProToolIndex!];
    _pushStep(ImageEditorStep(
      type: 'proTools',
      params: {
        'subType': entry.type,
        'curveBrightness': _curveBrightness,
        'curveContrast': _curveContrast,
        'whiteBalanceTemp': _whiteBalanceTemp,
      },
    ));
    setState(() => _selectedProToolIndex = null);
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
        _prepareCropSnapshot();
        params['ratio'] = _cropRatio;
        params['path'] = croppedPath;
      } else {
        return;
      }
    }
    if (toolIndex == kImageEditorToolFilter) {
      params['category'] = _filterCategoryIndex;
      params['template'] = _filterTemplateIndex;
      params['intensity'] = _filterIntensity;
    }
    if (toolIndex == kImageEditorToolBeauty) {
      params['template'] = _beautyTemplateIndex;
      params['intensity'] = _beautyIntensity;
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
    _prepareCropSnapshot();
    _pushStep(ImageEditorStep(type: 'crop', params: {
      'ratio': _cropRatio,
      'path': croppedPath,
    }));
    if (!mounted) return;
    setState(() => _selectedToolIndex = null);
  }

  /// 顶栏「完成」在剪裁模式下调用（VoidCallback 兼容）
  void _confirmCropAndExitFromTopBar() {
    _confirmCropAndExit();
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

  void _scrollToProCategory(int categoryIndex) {
    final firstIndex = _firstProToolIndexForCategory(categoryIndex);
    _scrollToProToolIndex(firstIndex);
  }

  int _firstProToolIndexForCategory(int categoryIndex) {
    final index = kImageEditorProToolEntries.indexWhere(
      (entry) => entry.categoryIndex == categoryIndex,
    );
    return index >= 0 ? index : 0;
  }

  void _scrollToProToolIndex(int index) {
    if (!_proToolScrollController.hasClients) return;
    final itemWidth = AppSpacing.buttonHeight + AppSpacing.sm;
    _proToolScrollController.animateTo(
      index * itemWidth,
      duration: Duration(
        milliseconds: (AppSpacing.buttonSize * 4).round(),
      ),
      curve: Curves.easeOut,
    );
  }

  void _syncProCategoryWithScroll(double viewportWidth, double itemWidth) {
    if (!_proToolScrollController.hasClients) return;
    final center = _proToolScrollController.offset + viewportWidth / 2;
    final index = (center / itemWidth).floor().clamp(0, kImageEditorProToolEntries.length - 1);
    final categoryIndex = kImageEditorProToolEntries[index].categoryIndex;
    if (categoryIndex != _selectedProCategory) {
      setState(() => _selectedProCategory = categoryIndex);
    }
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
        errorBuilder: (_, __, ___) => Icon(
          Icons.broken_image_outlined,
          size: AppSpacing.largeAvatarSize,
          color: fgSecondary,
        ),
      );
    } else if (!isFile) {
      imageWidget = Image.network(
        path,
        fit: BoxFit.contain,
        errorBuilder: (_, __, ___) => Icon(
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
    final previewWidget = _selectedToolIndex == kImageEditorToolRotate
        ? _buildRotatePreview(imageWidget)
        : imageWidget;
    final content = _selectedToolIndex == kImageEditorToolCrop
        ? _buildCropImageLayer(previewWidget)
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
        errorBuilder: (_, __, ___) => Icon(
          Icons.broken_image_outlined,
          size: AppSpacing.largeAvatarSize,
          color: fgSecondary,
        ),
      );
    } else if (!isFile) {
      imageWidget = Image.network(
        _currentPath,
        fit: BoxFit.contain,
        errorBuilder: (_, __, ___) => Icon(
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
    final previewWidget = _selectedToolIndex == kImageEditorToolRotate
        ? _buildRotatePreview(imageWidget)
        : imageWidget;
    final content = _selectedToolIndex == kImageEditorToolCrop
        ? _buildCropImageLayer(previewWidget)
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
    final lineWidth = AppSpacing.xs / 4;
    return Container(
      decoration: BoxDecoration(
        border: Border.all(
          color: AppColors.white,
          width: AppSpacing.xs / 2,
        ),
      ),
      child: Column(
        children: [
          Expanded(child: _buildCropGridRow(lineWidth)),
          Container(height: lineWidth, color: AppColors.white),
          Expanded(child: _buildCropGridRow(lineWidth)),
          Container(height: lineWidth, color: AppColors.white),
          Expanded(child: _buildCropGridRow(lineWidth)),
        ],
      ),
    );
  }

  Widget _buildCropGridRow(double lineWidth) {
    return Row(
      children: [
        const Expanded(child: SizedBox.shrink()),
        Container(width: lineWidth, color: AppColors.white),
        const Expanded(child: SizedBox.shrink()),
        Container(width: lineWidth, color: AppColors.white),
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

  void _onDone() {
    final Object? result;
    if (_isMultiImage) {
      result = <String, dynamic>{'index': _currentIndex, 'path': _currentPath};
    } else {
      result = _currentPath;
    }
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

enum _CropEdge { left, right, top, bottom }
