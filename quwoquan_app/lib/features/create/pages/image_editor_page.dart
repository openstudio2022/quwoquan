import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/features/create/models/image_editor_step.dart';

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
  List<String> get _paths {
    final list = widget.imagePaths;
    if (list != null && list.isNotEmpty) return list;
    return widget.initialPath.isNotEmpty ? [widget.initialPath] : [];
  }

  late int _currentIndex;
  PageController? _pageController;
  ScrollController? _thumbScrollController;

  @override
  void initState() {
    super.initState();
    _currentIndex = widget.index.clamp(0, (_paths.length - 1).clamp(0, 0x7fffffff));
    if (_paths.length > 1) {
      _pageController = PageController(initialPage: _currentIndex);
      _thumbScrollController = ScrollController();
    }
  }

  @override
  void dispose() {
    _pageController?.dispose();
    _thumbScrollController?.dispose();
    super.dispose();
  }

  String get _currentPath {
    if (_paths.isEmpty) return widget.initialPath;
    final i = _currentIndex.clamp(0, _paths.length - 1);
    return _paths[i];
  }

  bool get _isMultiImage => _paths.length > 1;

  /// 是否在图片下方展示曲线调节蒙皮（专业修图-曲线子工具选中时）
  bool get _showCurveOverlayBelowImage =>
      _proToolsSubMode && _selectedProSubTool == 0;

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
        final i = _proSubToolTypes.indexOf(sub ?? '');
        if (i >= 0) {
          _proToolsSubMode = true;
          _selectedProSubTool = i;
          _curveBrightness = (step.params['curveBrightness'] as num?)?.toDouble() ?? _curveBrightness;
          _curveContrast = (step.params['curveContrast'] as num?)?.toDouble() ?? _curveContrast;
          _whiteBalanceTemp = (step.params['whiteBalanceTemp'] as num?)?.toDouble() ?? _whiteBalanceTemp;
        }
      } else {
        _selectedToolIndex = _toolIndexForType(step.type);
      }
    });
  }

  int _toolIndexForType(String type) {
    const types = ['rotate', 'crop', 'filter', 'proTools', 'frame', 'text', 'doodle', 'mosaic'];
    final i = types.indexOf(type);
    return i >= 0 ? i : 0;
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
        case 'heal':
          return UITextConstants.imageEditorProHeal;
        case 'glamourGlow':
          return UITextConstants.imageEditorProGlamourGlow;
        case 'toneContrast':
          return UITextConstants.imageEditorProToneContrast;
        case 'hsl':
          return UITextConstants.imageEditorProHsl;
      }
    }
    switch (type) {
      case 'rotate':
        return UITextConstants.imageEditorRotate;
      case 'crop':
        return UITextConstants.imageEditorCrop;
      case 'filter':
        return UITextConstants.imageEditorFilter;
      case 'proTools':
        return UITextConstants.imageEditorProTools;
      case 'frame':
        return UITextConstants.imageEditorFrame;
      case 'text':
        return UITextConstants.imageEditorText;
      case 'doodle':
        return UITextConstants.imageEditorDoodle;
      case 'mosaic':
        return UITextConstants.imageEditorMosaic;
      default:
        return type;
    }
  }

  int? _selectedToolIndex;

  /// 裁剪比例：free|original|square|3x2
  String _cropRatio = 'free';
  /// 滤镜：分类索引、模板索引、强度 0~1
  int _filterCategoryIndex = 0;
  int _filterTemplateIndex = 0;
  double _filterIntensity = 0.5;
  /// 旋转：当前角度（度）
  int _rotateDegrees = 0;

  /// 专业修图子模式（进入后底栏展示子工具）
  bool _proToolsSubMode = false;
  /// 专业修图选中的子工具索引 0-6：曲线、白平衡、局部、修复、美丽光晕、色调对比度、HSL
  int? _selectedProSubTool;
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
    final isDark = ref.watch(isDarkProvider);
    final bg = AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary);
    final fg = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    final topPad = MediaQuery.paddingOf(context).top;
    final bottomPad = MediaQuery.paddingOf(context).bottom;

    return Scaffold(
      backgroundColor: bg,
      body: SafeArea(
        top: false,
        bottom: false,
        child: Column(
          children: [
            // 1. 顶栏：固定在上
            _buildTopBar(bg, fg, topPad),
            // 2. 中部：占满剩余空间；选中曲线时图片下方展示曲线蒙皮
            Expanded(
              child: _showCurveOverlayBelowImage
                  ? Column(
                      children: [
                        Expanded(
                          child: _isMultiImage && _pageController != null
                              ? PageView.builder(
                                  controller: _pageController,
                                  itemCount: _paths.length,
                                  onPageChanged: (int index) {
                                    setState(() => _currentIndex = index);
                                    _scrollThumbToIndex(index);
                                  },
                                  itemBuilder: (context, index) {
                                    return _buildMiddleImageForPath(
                                        _paths[index], fgSecondary);
                                  },
                                )
                              : _buildMiddleImage(fgSecondary),
                        ),
                        _buildCurveOverlayBar(bg, fg, fgSecondary),
                      ],
                    )
                  : _isMultiImage && _pageController != null
                      ? PageView.builder(
                          controller: _pageController,
                          itemCount: _paths.length,
                          onPageChanged: (int index) {
                            setState(() => _currentIndex = index);
                            _scrollThumbToIndex(index);
                          },
                          itemBuilder: (context, index) {
                            return _buildMiddleImageForPath(
                                _paths[index], fgSecondary);
                          },
                        )
                      : _buildMiddleImage(fgSecondary),
            ),
            // 多图时：缩略图列表，选中项与当前大图联动
            if (_isMultiImage) _buildThumbnailStrip(bg, fgSecondary),
            // 操作面板（选中非专业修图时 或 专业修图子工具选中且非曲线时；曲线由图片下方蒙皮单独承载）
            if ((_selectedToolIndex != null && _selectedToolIndex != 3) ||
                (_proToolsSubMode &&
                    _selectedProSubTool != null &&
                    _selectedProSubTool != 0))
              _buildOperationPanel(bg, fg, fgSecondary),
            // 3. 底栏：固定在下，编辑功能入口
            _buildBottomToolBar(bg, fg, fgSecondary, bottomPad),
          ],
        ),
      ),
    );
  }

  void _scrollThumbToIndex(int index) {
    final c = _thumbScrollController;
    if (c == null || !c.hasClients) return;
    final thumbWidth = 56.0 + (AppSpacing.intraGroupSm);
    final offset = (index * thumbWidth) - c.position.viewportDimension / 2 + thumbWidth / 2;
    c.animateTo(
      offset.clamp(0.0, c.position.maxScrollExtent),
      duration: const Duration(milliseconds: 200),
      curve: Curves.easeOut,
    );
  }

  /// 曲线调节蒙皮：图片下方区域展示曲线图/通道选择/亮度对比度等，底部取消/保存
  Widget _buildCurveOverlayBar(Color bg, Color fg, Color fgSecondary) {
    final borderColor = AppColorsFunctional.getColor(
      ref.read(isDarkProvider),
      ColorType.borderPrimary,
    ).withValues(alpha: 0.3);
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.semantic[DesignSemanticConstants.container]
                ?[DesignSemanticConstants.sm] ??
            AppSpacing.containerSm,
        vertical: AppSpacing.sm,
      ),
      decoration: BoxDecoration(
        color: bg,
        border: Border(top: BorderSide(color: borderColor)),
      ),
      child: SafeArea(
        top: false,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              UITextConstants.imageEditorProCurve,
              style: TextStyle(
                color: fg,
                fontSize: AppTypography.sm,
                fontWeight: FontWeight.w600,
              ),
            ),
            SizedBox(height: AppSpacing.xs),
            Row(
              children: [
                Expanded(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        UITextConstants.imageEditorProBrightness,
                        style: TextStyle(
                            fontSize: AppTypography.xs, color: fgSecondary),
                      ),
                      SliderTheme(
                        data: SliderThemeData(
                          activeTrackColor: AppColors.primaryColor,
                          thumbColor: AppColors.primaryColor,
                        ),
                        child: Slider(
                          value: _curveBrightness,
                          onChanged: (v) =>
                              setState(() => _curveBrightness = v),
                        ),
                      ),
                    ],
                  ),
                ),
                Expanded(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        UITextConstants.imageEditorProContrast,
                        style: TextStyle(
                            fontSize: AppTypography.xs, color: fgSecondary),
                      ),
                      SliderTheme(
                        data: SliderThemeData(
                          activeTrackColor: AppColors.primaryColor,
                          thumbColor: AppColors.primaryColor,
                        ),
                        child: Slider(
                          value: _curveContrast,
                          onChanged: (v) =>
                              setState(() => _curveContrast = v),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                IconButton(
                  icon: Icon(Icons.close, color: fg),
                  onPressed: () => setState(() => _selectedProSubTool = null),
                  tooltip: UITextConstants.cancel,
                ),
                IconButton(
                  icon: Icon(Icons.check, color: AppColors.primaryColor),
                  onPressed: () {
                    _pushStep(ImageEditorStep(
                      type: 'proTools',
                      params: {
                        'subType': 'curve',
                        'curveBrightness': _curveBrightness,
                        'curveContrast': _curveContrast,
                      },
                    ));
                    setState(() => _selectedProSubTool = null);
                  },
                  tooltip: UITextConstants.confirm,
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildThumbnailStrip(Color bg, Color fgSecondary) {
    const thumbSize = 56.0;
    final borderColor = AppColorsFunctional.getColor(
      ref.read(isDarkProvider),
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
                    color: isSelected ? AppColors.primaryColor : fgSecondary.withValues(alpha: 0.3),
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
    return Icon(Icons.broken_image_outlined, size: 24, color: fgSecondary);
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
          size: 64,
          color: fgSecondary,
        ),
      );
    } else if (!isFile) {
      imageWidget = Image.network(
        path,
        fit: BoxFit.contain,
        errorBuilder: (_, __, ___) => Icon(
          Icons.broken_image_outlined,
          size: 64,
          color: fgSecondary,
        ),
      );
    } else {
      imageWidget = Icon(Icons.broken_image_outlined, size: 64, color: fgSecondary);
    }
    final content = InteractiveViewer(
      minScale: 0.5,
      maxScale: 4,
      child: Center(child: imageWidget),
    );
    if (_selectedToolIndex == 1) {
      return Stack(
        alignment: Alignment.center,
        children: [
          content,
          _buildCropOverlay(),
        ],
      );
    }
    if (_selectedToolIndex == 0) {
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

  Widget _buildTopBar(Color bg, Color fg, double topPad) {
    final topBarHeight = AppSpacing.tabNavigationHeight;
    return Container(
      height: topPad + topBarHeight,
      padding: EdgeInsets.only(top: topPad),
      color: bg,
      child: Row(
        children: [
          // 左侧：返回
          SizedBox(
            width: AppSpacing.buttonHeight,
            height: topBarHeight,
            child: IconButton(
              icon: Icon(Icons.arrow_back_ios_new, color: fg, size: AppSpacing.iconMedium),
              onPressed: () {
                if (widget.onBack != null) {
                  widget.onBack!();
                } else {
                  context.pop();
                }
              },
              style: IconButton.styleFrom(
                padding: EdgeInsets.zero,
                minimumSize: Size.zero,
                tapTargetSize: MaterialTapTargetSize.shrinkWrap,
              ),
            ),
          ),
          // 历史入口（完成前可查看/删除/重做步骤）
          SizedBox(
            width: AppSpacing.buttonHeight,
            height: topBarHeight,
            child: IconButton(
              icon: Icon(Icons.history, color: fg, size: AppSpacing.iconMedium),
              onPressed: _steps.isEmpty ? null : _showHistorySheet,
              style: IconButton.styleFrom(
                padding: EdgeInsets.zero,
                minimumSize: Size.zero,
                tapTargetSize: MaterialTapTargetSize.shrinkWrap,
              ),
            ),
          ),
          // 中间：图片序号 当前/总数（多图时随滑动更新）
          Expanded(
            child: Center(
              child: Text(
                '${_currentIndex + 1}/${_paths.isEmpty ? widget.total : _paths.length}',
                style: TextStyle(
                  color: fg,
                  fontSize: AppTypography.sm,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ),
          ),
          // 右侧：完成按钮（蓝色）
          Padding(
            padding: EdgeInsets.only(
              right: AppSpacing.semantic[DesignSemanticConstants.container]
                      ?[DesignSemanticConstants.sm] ??
                  AppSpacing.sm,
            ),
            child: Material(
              color: AppColors.primaryColor,
              borderRadius: BorderRadius.circular(
                AppSpacing.semantic[DesignSemanticConstants.button]
                        ?[DesignSemanticConstants.sm] ??
                    AppSpacing.sm,
              ),
              child: InkWell(
                onTap: _onDone,
                borderRadius: BorderRadius.circular(
                  AppSpacing.semantic[DesignSemanticConstants.button]
                          ?[DesignSemanticConstants.sm] ??
                      AppSpacing.sm,
                ),
                child: Padding(
                  padding: EdgeInsets.symmetric(
                    horizontal: AppSpacing.md,
                    vertical: AppSpacing.sm,
                  ),
                  child: Center(
                    child: Text(
                      UITextConstants.imageEditDone,
                      style: TextStyle(
                        color: AppColors.white,
                        fontSize: AppTypography.sm,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
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
          size: 64,
          color: fgSecondary,
        ),
      );
    } else if (!isFile) {
      imageWidget = Image.network(
        _currentPath,
        fit: BoxFit.contain,
        errorBuilder: (_, __, ___) => Icon(
          Icons.broken_image_outlined,
          size: 64,
          color: fgSecondary,
        ),
      );
    } else {
      imageWidget = Icon(Icons.broken_image_outlined, size: 64, color: fgSecondary);
    }
    final content = InteractiveViewer(
      minScale: 0.5,
      maxScale: 4,
      child: Center(child: imageWidget),
    );
    if (_selectedToolIndex == 1) {
      return Stack(
        alignment: Alignment.center,
        children: [
          content,
          _buildCropOverlay(),
        ],
      );
    }
    if (_selectedToolIndex == 0) {
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

  /// 裁剪框与九宫格辅助线
  Widget _buildCropOverlay() {
    return LayoutBuilder(
      builder: (context, constraints) {
        final w = constraints.maxWidth;
        final h = constraints.maxHeight;
        final side = (w < h ? w : h) * 0.85;
        return Stack(
          children: [
            Positioned.fill(
              child: ColoredBox(
                color: AppColors.black.withValues(alpha: 0.4),
              ),
            ),
            Center(
              child: SizedBox(
                width: side,
                height: side,
                child: Container(
                  decoration: BoxDecoration(
                    border: Border.all(color: AppColors.white, width: 2),
                  ),
                  child: Column(
                    children: [
                      Expanded(
                        child: Row(
                          children: [
                            Expanded(child: _cropGridCell()),
                            Container(width: 1, color: AppColors.white),
                            Expanded(child: _cropGridCell()),
                            Container(width: 1, color: AppColors.white),
                            Expanded(child: _cropGridCell()),
                          ],
                        ),
                      ),
                      Container(height: 1, color: AppColors.white),
                      Expanded(
                        child: Row(
                          children: [
                            Expanded(child: _cropGridCell()),
                            Container(width: 1, color: AppColors.white),
                            Expanded(child: _cropGridCell()),
                            Container(width: 1, color: AppColors.white),
                            Expanded(child: _cropGridCell()),
                          ],
                        ),
                      ),
                      Container(height: 1, color: AppColors.white),
                      Expanded(
                        child: Row(
                          children: [
                            Expanded(child: _cropGridCell()),
                            Container(width: 1, color: AppColors.white),
                            Expanded(child: _cropGridCell()),
                            Container(width: 1, color: AppColors.white),
                            Expanded(child: _cropGridCell()),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ],
        );
      },
    );
  }

  Widget _cropGridCell() => const SizedBox.shrink();

  /// 旋转调节时图片上叠加的对齐网格（等分网格，便于对齐主体与角度）
  Widget _buildRotateGridOverlay() {
    return LayoutBuilder(
      builder: (context, constraints) {
        const int gridCount = 6;
        final w = constraints.maxWidth;
        final h = constraints.maxHeight;
        return IgnorePointer(
          child: Column(
            children: List.generate(gridCount, (row) {
              return Expanded(
                child: Row(
                  children: List.generate(gridCount, (col) {
                    return Expanded(
                      child: Container(
                        decoration: BoxDecoration(
                          border: Border(
                            right: col < gridCount - 1
                                ? BorderSide(
                                    color: AppColors.white.withValues(alpha: 0.5),
                                    width: 1,
                                  )
                                : BorderSide.none,
                            bottom: row < gridCount - 1
                                ? BorderSide(
                                    color: AppColors.white.withValues(alpha: 0.5),
                                    width: 1,
                                  )
                                : BorderSide.none,
                          ),
                        ),
                      ),
                    );
                  }),
                ),
              );
            }),
          ),
        );
      },
    );
  }

  static const List<String> _proSubToolTypes = [
    'curve', 'whiteBalance', 'local', 'heal', 'glamourGlow', 'toneContrast', 'hsl',
  ];

  static const List<(IconData icon, String label)> _proSubToolEntries = [
    (Icons.show_chart, UITextConstants.imageEditorProCurve),
    (Icons.wb_sunny_outlined, UITextConstants.imageEditorProWhiteBalance),
    (Icons.radar, UITextConstants.imageEditorProLocal),
    (Icons.healing, UITextConstants.imageEditorProHeal),
    (Icons.blur_on, UITextConstants.imageEditorProGlamourGlow),
    (Icons.contrast, UITextConstants.imageEditorProToneContrast),
    (Icons.palette_outlined, UITextConstants.imageEditorProHsl),
  ];

  Widget _buildBottomToolBar(
    Color bg,
    Color fg,
    Color fgSecondary,
    double bottomPad,
  ) {
    const toolEntries = [
      (icon: Icons.rotate_right, labelKey: UITextConstants.imageEditorRotate),
      (icon: Icons.crop, labelKey: UITextConstants.imageEditorCrop),
      (icon: Icons.filter, labelKey: UITextConstants.imageEditorFilter),
      (icon: Icons.tune, labelKey: UITextConstants.imageEditorProTools),
      (icon: Icons.crop_free, labelKey: UITextConstants.imageEditorFrame),
      (icon: Icons.text_fields, labelKey: UITextConstants.imageEditorText),
      (icon: Icons.brush_outlined, labelKey: UITextConstants.imageEditorDoodle),
      (icon: Icons.grid_on, labelKey: UITextConstants.imageEditorMosaic),
    ];
    final barHeight = AppSpacing.bottomNavHeight;
    final borderColor = AppColorsFunctional.getColor(
      ref.read(isDarkProvider),
      ColorType.borderPrimary,
    ).withValues(alpha: 0.3);

    return Container(
      height: bottomPad + barHeight,
      padding: EdgeInsets.only(bottom: bottomPad),
      decoration: BoxDecoration(
        color: bg,
        border: Border(top: BorderSide(color: borderColor)),
      ),
      child: _proToolsSubMode
          ? Row(
              children: [
                Padding(
                  padding: EdgeInsets.only(left: AppSpacing.sm),
                  child: IconButton(
                    icon: Icon(Icons.arrow_back, color: fg),
                    onPressed: () => setState(() {
                      _proToolsSubMode = false;
                      _selectedProSubTool = null;
                    }),
                    tooltip: UITextConstants.cancel,
                  ),
                ),
                Expanded(
                  child: ListView.separated(
                    scrollDirection: Axis.horizontal,
                    padding: EdgeInsets.symmetric(vertical: AppSpacing.xs),
                    itemCount: _proSubToolEntries.length,
                    separatorBuilder: (_, __) => SizedBox(
                      width: AppSpacing.intraGroupMd,
                    ),
                    itemBuilder: (context, index) {
                      final entry = _proSubToolEntries[index];
                      return _ToolEntryChip(
                        icon: entry.$1,
                        label: entry.$2,
                        isSelected: _selectedProSubTool == index,
                        onTap: () => setState(() => _selectedProSubTool = index),
                      );
                    },
                  ),
                ),
              ],
            )
          : ListView.separated(
              scrollDirection: Axis.horizontal,
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.containerSm,
                vertical: AppSpacing.xs,
              ),
              itemCount: toolEntries.length,
              separatorBuilder: (_, __) => SizedBox(width: AppSpacing.intraGroupMd),
              itemBuilder: (context, index) {
                final entry = toolEntries[index];
                return _ToolEntryChip(
                  icon: entry.icon,
                  label: entry.labelKey,
                  isSelected: _selectedToolIndex == index,
                  onTap: () => setState(() {
                    if (index == 3) {
                      _proToolsSubMode = true;
                      _selectedToolIndex = null;
                    } else {
                      _selectedToolIndex = index;
                    }
                  }),
                );
              },
            ),
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

  static const List<String> _toolTypes = [
    'rotate', 'crop', 'filter', 'proTools', 'frame', 'text', 'doodle', 'mosaic',
  ];

  Widget _buildOperationPanel(Color bg, Color fg, Color fgSecondary) {
    final borderColor = AppColorsFunctional.getColor(
      ref.read(isDarkProvider),
      ColorType.borderPrimary,
    ).withValues(alpha: 0.3);
    return Container(
      height: 220,
      decoration: BoxDecoration(
        color: bg,
        border: Border(top: BorderSide(color: borderColor)),
      ),
      child: _proToolsSubMode && _selectedProSubTool != null
          ? _buildProToolsPanel(bg, fg, fgSecondary)
          : Column(
              children: [
                _buildPanelTopContent(_selectedToolIndex ?? 0, fg, fgSecondary),
                Expanded(
                  child: _buildPanelMiddleContent(_selectedToolIndex ?? 0, fgSecondary),
                ),
                _buildPanelBottomBar(_selectedToolIndex ?? 0, fg, fgSecondary),
              ],
            ),
    );
  }

  /// 专业修图子工具面板（曲线、白平衡等，与滤镜/裁剪一致结构）
  Widget _buildProToolsPanel(Color bg, Color fg, Color fgSecondary) {
    final subIndex = _selectedProSubTool ?? 0;
    final subType = _proSubToolTypes[subIndex];
    return Column(
      children: [
        SizedBox(height: 44),
        Expanded(
          child: _buildProSubToolContent(subIndex, fg, fgSecondary),
        ),
        Padding(
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.containerMd,
            vertical: AppSpacing.sm,
          ),
          child: Row(
            children: [
              IconButton(
                icon: Icon(Icons.close, color: fg),
                onPressed: () => setState(() {
                  _selectedProSubTool = null;
                }),
                tooltip: UITextConstants.cancel,
              ),
              const Spacer(),
              IconButton(
                icon: Icon(Icons.check, color: AppColors.primaryColor),
                onPressed: () {
                  _pushStep(ImageEditorStep(
                    type: 'proTools',
                    params: {
                      'subType': subType,
                      'curveBrightness': _curveBrightness,
                      'curveContrast': _curveContrast,
                      'whiteBalanceTemp': _whiteBalanceTemp,
                    },
                  ));
                  setState(() => _selectedProSubTool = null);
                },
                tooltip: UITextConstants.confirm,
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildProSubToolContent(int subIndex, Color fg, Color fgSecondary) {
    switch (subIndex) {
      case 0:
        return SingleChildScrollView(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(UITextConstants.imageEditorProBrightness, style: TextStyle(fontSize: AppTypography.sm, color: fgSecondary)),
              Slider(
                value: _curveBrightness,
                onChanged: (v) => setState(() => _curveBrightness = v),
                activeColor: AppColors.primaryColor,
              ),
              Text(UITextConstants.imageEditorProContrast, style: TextStyle(fontSize: AppTypography.sm, color: fgSecondary)),
              Slider(
                value: _curveContrast,
                onChanged: (v) => setState(() => _curveContrast = v),
                activeColor: AppColors.primaryColor,
              ),
            ],
          ),
        );
      case 1:
        return Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(UITextConstants.imageEditorProColorTemp, style: TextStyle(fontSize: AppTypography.sm, color: fgSecondary)),
              Slider(
                value: _whiteBalanceTemp,
                onChanged: (v) => setState(() => _whiteBalanceTemp = v),
                activeColor: AppColors.primaryColor,
              ),
            ],
          ),
        );
      default:
        return Center(
          child: Text(
            _proSubToolEntries[subIndex].$2,
            style: TextStyle(color: fgSecondary, fontSize: AppTypography.sm),
          ),
        );
    }
  }

  Widget _buildPanelTopContent(int toolIndex, Color fg, Color fgSecondary) {
    if (toolIndex == 1) {
      final ratios = [
        (UITextConstants.imageEditorCropFree, 'free'),
        (UITextConstants.imageEditorCropOriginal, 'original'),
        (UITextConstants.imageEditorCropSquare, 'square'),
        (UITextConstants.imageEditorCropRatio3x2, '3x2'),
      ];
      return SizedBox(
        height: 44,
        child: ListView(
          scrollDirection: Axis.horizontal,
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.containerSm,
            vertical: AppSpacing.xs,
          ),
          children: ratios
              .map((r) => Padding(
                    padding: EdgeInsets.only(right: AppSpacing.intraGroupSm),
                    child: _panelChip(
                      fg,
                      fgSecondary,
                      r.$1,
                      _cropRatio == r.$2,
                      onTap: () => setState(() => _cropRatio = r.$2),
                    ),
                  ))
              .toList(),
        ),
      );
    }
    if (toolIndex == 2) {
      final categories = [
        UITextConstants.imageEditorFilterRecommended,
        UITextConstants.imageEditorFilterQuality,
        UITextConstants.imageEditorFilterSpring,
      ];
      return SizedBox(
        height: 44,
        child: ListView(
          scrollDirection: Axis.horizontal,
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.containerSm,
            vertical: AppSpacing.xs,
          ),
          children: [
            _panelChip(fg, fgSecondary, UITextConstants.imageEditOriginal,
                _filterCategoryIndex == 0, onTap: () => setState(() => _filterCategoryIndex = 0)),
            ...List.generate(categories.length, (i) {
              return Padding(
                padding: EdgeInsets.only(left: AppSpacing.intraGroupSm),
                child: _panelChip(fg, fgSecondary, categories[i],
                    _filterCategoryIndex == i + 1,
                    onTap: () => setState(() => _filterCategoryIndex = i + 1)),
              );
            }),
          ],
        ),
      );
    }
    return SizedBox(height: 44);
  }

  Widget _buildPanelMiddleContent(int toolIndex, Color fgSecondary) {
    if (toolIndex == 0) {
      // 旋转仪表（约 ±45° 精细调节）+ 向左90°、向右90°、水平翻转、垂直翻转
      return Padding(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.semantic[DesignSemanticConstants.container]
                  ?[DesignSemanticConstants.sm] ??
              AppSpacing.containerSm,
          vertical: AppSpacing.xs,
        ),
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  IconButton(
                    icon: Icon(Icons.rotate_left, color: AppColors.primaryColor),
                    onPressed: () => setState(() => _rotateDegrees = (_rotateDegrees - 90) % 360),
                    tooltip: UITextConstants.imageEditorRotateLeft90,
                  ),
                  Padding(
                    padding: EdgeInsets.symmetric(horizontal: AppSpacing.sm),
                    child: Text(
                      '${_rotateDegrees + _rotateFineDegrees.round()}°',
                      style: TextStyle(
                        color: fgSecondary,
                        fontSize: AppTypography.lg,
                      ),
                    ),
                  ),
                  IconButton(
                    icon: Icon(Icons.rotate_right, color: AppColors.primaryColor),
                    onPressed: () => setState(() => _rotateDegrees = (_rotateDegrees + 90) % 360),
                    tooltip: UITextConstants.imageEditorRotateRight90,
                  ),
                ],
              ),
              SliderTheme(
                data: SliderThemeData(
                  activeTrackColor: AppColors.primaryColor,
                  thumbColor: AppColors.primaryColor,
                ),
                child: Slider(
                  value: _rotateFineDegrees,
                  min: -45,
                  max: 45,
                  onChanged: (v) => setState(() => _rotateFineDegrees = v),
                ),
              ),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  _panelChip(
                    fgSecondary,
                    fgSecondary,
                    UITextConstants.imageEditorFlipHorizontal,
                    _flipHorizontal,
                    onTap: () => setState(() => _flipHorizontal = !_flipHorizontal),
                  ),
                  SizedBox(width: AppSpacing.sm),
                  _panelChip(
                    fgSecondary,
                    fgSecondary,
                    UITextConstants.imageEditorFlipVertical,
                    _flipVertical,
                    onTap: () => setState(() => _flipVertical = !_flipVertical),
                  ),
                ],
              ),
            ],
          ),
        ),
      );
    }
    if (toolIndex == 2) {
      final templates = [
        UITextConstants.imageEditorFilterVivid,
        UITextConstants.imageEditorFilterHighSat,
        UITextConstants.imageEditorFilterDehaze,
        UITextConstants.imageEditVivid,
        UITextConstants.imageEditWarm,
        UITextConstants.imageEditCool,
      ];
      return ListView.builder(
        scrollDirection: Axis.horizontal,
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.sm, vertical: AppSpacing.xs),
        itemCount: templates.length,
        itemBuilder: (context, i) {
          final selected = _filterTemplateIndex == i;
          return Padding(
            padding: EdgeInsets.only(right: AppSpacing.sm),
            child: GestureDetector(
              onTap: () => setState(() => _filterTemplateIndex = i),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    width: 56,
                    height: 56,
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                      border: Border.all(
                        color: selected ? AppColors.primaryColor : fgSecondary.withValues(alpha: 0.3),
                        width: selected ? 2 : 1,
                      ),
                    ),
                  ),
                  SizedBox(height: AppSpacing.xs),
                  Text(
                    templates[i],
                    style: TextStyle(
                      fontSize: 11,
                      color: selected ? AppColors.primaryColor : fgSecondary,
                    ),
                  ),
                ],
              ),
            ),
          );
        },
      );
    }
    return Center(
      child: Text(
        UITextConstants.imageEditorPanelPlaceholder,
        style: TextStyle(color: fgSecondary, fontSize: AppTypography.sm),
      ),
    );
  }

  Widget _buildPanelBottomBar(int toolIndex, Color fg, Color fgSecondary) {
    final showSlider = toolIndex == 2;
    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerMd,
        vertical: AppSpacing.sm,
      ),
      child: Row(
        children: [
          IconButton(
            icon: Icon(Icons.close, color: fg),
            onPressed: () {
              setState(() {
                _selectedToolIndex = null;
              });
            },
            tooltip: UITextConstants.cancel,
          ),
          if (showSlider)
            Expanded(
              child: SliderTheme(
                data: SliderThemeData(
                  activeTrackColor: AppColors.primaryColor,
                  thumbColor: AppColors.primaryColor,
                ),
                child: Slider(
                  value: _filterIntensity,
                  onChanged: (v) => setState(() => _filterIntensity = v),
                ),
              ),
            )
          else
            const Spacer(),
          IconButton(
            icon: Icon(Icons.check, color: AppColors.primaryColor),
            onPressed: () {
              final type = _toolTypes[toolIndex];
              final params = <String, dynamic>{'index': toolIndex};
              if (toolIndex == 0) {
                params['degrees'] = _rotateDegrees;
                params['fineDegrees'] = _rotateFineDegrees;
                params['flipHorizontal'] = _flipHorizontal;
                params['flipVertical'] = _flipVertical;
              }
              if (toolIndex == 1) params['ratio'] = _cropRatio;
              if (toolIndex == 2) {
                params['category'] = _filterCategoryIndex;
                params['template'] = _filterTemplateIndex;
                params['intensity'] = _filterIntensity;
              }
              _pushStep(ImageEditorStep(type: type, params: params));
              setState(() {
                _selectedToolIndex = null;
              });
            },
            tooltip: UITextConstants.confirm,
          ),
        ],
      ),
    );
  }

  Widget _panelChip(
    Color fg,
    Color fgSecondary,
    String label,
    bool selected, {
    VoidCallback? onTap,
  }) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap ?? () {},
        borderRadius: BorderRadius.circular(AppSpacing.smallBorderRadius),
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.sm,
            vertical: AppSpacing.xs,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(
                label,
                style: TextStyle(
                  color: selected ? AppColors.primaryColor : fgSecondary,
                  fontSize: AppTypography.sm,
                  fontWeight: selected ? FontWeight.w600 : FontWeight.normal,
                ),
              ),
              if (selected)
                Container(
                  margin: EdgeInsets.only(top: 2),
                  height: 2,
                  width: 16,
                  color: AppColors.primaryColor,
                ),
            ],
          ),
        ),
      ),
    );
  }

  void _showHistorySheet() {
    final isDark = ref.read(isDarkProvider);
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
                            icon: Icon(Icons.refresh, color: fgSecondary, size: AppSpacing.iconSmall),
                            onPressed: () {
                              Navigator.of(context).pop();
                              _redoStepAt(index);
                            },
                            tooltip: UITextConstants.imageEditorRedoStep,
                          ),
                          IconButton(
                            icon: Icon(Icons.delete_outline, color: fgSecondary, size: AppSpacing.iconSmall),
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

/// 底栏单个工具入口（图标 + 文案）
class _ToolEntryChip extends StatelessWidget {
  const _ToolEntryChip({
    required this.icon,
    required this.label,
    required this.isSelected,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final bool isSelected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final fg = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    final color = isSelected ? AppColors.primaryColor : fg;
    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            icon,
            size: AppSpacing.iconMedium,
            color: color,
          ),
          SizedBox(
            height: AppSpacing.xs,
          ),
          Text(
            label,
            style: TextStyle(
              fontSize: 11,
              color: isSelected ? color : fgSecondary,
              fontWeight: isSelected ? FontWeight.w600 : FontWeight.normal,
            ),
          ),
        ],
      ),
    );
  }
}
