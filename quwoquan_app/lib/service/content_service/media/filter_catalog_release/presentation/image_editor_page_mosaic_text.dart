part of 'image_editor_page.dart';

/// 马赛克与文字会话逻辑：图上涂抹/文字图层的交互、预览与清理。
/// 导出几何与 ImageEditorExportEngine 共用同一归一化坐标真相源。
extension _ImageEditorPageMosaicText on _ImageEditorPageState {
  bool get _isEditingMosaic => _selectedToolIndex == kImageEditorToolMosaic;

  bool get _isEditingText => _selectedToolIndex == kImageEditorToolText;

  void _disposeMosaicSessionResources() {
    _mosaicPreviewPixelated?.dispose();
    _mosaicPreviewPixelated = null;
    _mosaicPreviewBlurred?.dispose();
    _mosaicPreviewBlurred = null;
    _mosaicPreviewLoading = false;
  }

  // ---- 马赛克会话 ----

  void _prepareMosaicSession() {
    _mosaicStrokes.clear();
    _activeMosaicStroke = null;
    _disposeMosaicSessionResources();
    unawaited(_loadMosaicPreviewSources());
  }

  Future<void> _loadMosaicPreviewSources() async {
    if (_mosaicPreviewLoading) return;
    _mosaicPreviewLoading = true;
    try {
      final bytes = await _loadImageBytes(_currentPath);
      if (bytes.isEmpty || !mounted) return;
      final base = await ImageEditorExportEngine.decodeConstrained(
        bytes,
        maxDimension: ImageEditorExportEngine.kPreviewDecodeDimension,
      );
      final pixelated = await ImageEditorExportEngine.buildMosaicizedImage(
        base,
        ImageEditorMosaicType.pixelate,
      );
      final blurred = await ImageEditorExportEngine.buildMosaicizedImage(
        base,
        ImageEditorMosaicType.blur,
      );
      base.dispose();
      if (!mounted) {
        pixelated.dispose();
        blurred.dispose();
        return;
      }
      _setEditorState(() {
        _mosaicPreviewPixelated = pixelated;
        _mosaicPreviewBlurred = blurred;
      });
    } catch (error) {
      _observability.recordPageState(
        pageName: _ImageEditorPageState._kPageName,
        phase: 'failure',
        surface: _ImageEditorPageState._kSurfaceId,
        copyKey: 'mosaic_preview_load',
        error: error is Exception ? error : null,
      );
    } finally {
      _mosaicPreviewLoading = false;
    }
  }

  void _undoLastMosaicStroke() {
    if (_mosaicStrokes.isEmpty) return;
    _setEditorState(() => _mosaicStrokes.removeLast());
  }

  void _cancelMosaicAndExit() {
    _setEditorState(() {
      _mosaicStrokes.clear();
      _activeMosaicStroke = null;
      _selectedToolIndex = null;
    });
    _disposeMosaicSessionResources();
  }

  Offset? _normalizedPointInImage(Offset localPosition, Rect imageRect) {
    if (imageRect.isEmpty) return null;
    final nx = (localPosition.dx - imageRect.left) / imageRect.width;
    final ny = (localPosition.dy - imageRect.top) / imageRect.height;
    if (nx < 0 || nx > 1 || ny < 0 || ny > 1) return null;
    return Offset(nx.clamp(0.0, 1.0), ny.clamp(0.0, 1.0));
  }

  void _startMosaicStroke(Offset localPosition, Rect imageRect) {
    final point = _normalizedPointInImage(localPosition, imageRect);
    if (point == null) return;
    _setEditorState(() {
      _activeMosaicStroke = ImageEditorMosaicStroke(
        type: _mosaicType,
        brushRadiusOnShortSide: mosaicBrushRadiusFromSlider(_mosaicBrushSize),
        points: <Offset>[point],
      );
    });
  }

  void _extendMosaicStroke(Offset localPosition, Rect imageRect) {
    final active = _activeMosaicStroke;
    if (active == null) return;
    final point = _normalizedPointInImage(localPosition, imageRect);
    if (point == null) return;
    if (active.points.isNotEmpty &&
        (active.points.last - point).distance < 0.004) {
      return;
    }
    _setEditorState(() {
      _activeMosaicStroke = active.copyWithPoint(point);
    });
  }

  void _endMosaicStroke() {
    final active = _activeMosaicStroke;
    if (active == null) return;
    _setEditorState(() {
      _mosaicStrokes.add(active);
      _activeMosaicStroke = null;
    });
  }

  /// 马赛克编辑中的中部图层：底图 + 笔画蒙版预览 + 手势。
  Widget _buildMosaicSessionImageLayer(Widget content) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final viewport = Size(constraints.maxWidth, constraints.maxHeight);
        final imageRect = _resolveImageRect(viewport);
        final mosaicImage = _mosaicType == ImageEditorMosaicType.pixelate
            ? _mosaicPreviewPixelated
            : _mosaicPreviewBlurred;
        final strokes = <ImageEditorMosaicStroke>[
          ..._mosaicStrokes,
          ?_activeMosaicStroke,
        ];
        return GestureDetector(
          behavior: HitTestBehavior.opaque,
          onPanStart: (details) =>
              _startMosaicStroke(details.localPosition, imageRect),
          onPanUpdate: (details) =>
              _extendMosaicStroke(details.localPosition, imageRect),
          onPanEnd: (_) => _endMosaicStroke(),
          onPanCancel: _endMosaicStroke,
          child: Stack(
            fit: StackFit.expand,
            children: [
              content,
              if (strokes.isNotEmpty)
                Positioned.fill(
                  child: IgnorePointer(
                    child: CustomPaint(
                      painter: _MosaicStrokePreviewPainter(
                        imageRect: imageRect,
                        pixelated: _mosaicPreviewPixelated,
                        blurred: _mosaicPreviewBlurred,
                        strokes: strokes,
                      ),
                    ),
                  ),
                ),
              if (strokes.isEmpty && mosaicImage != null)
                Align(
                  alignment: Alignment.topCenter,
                  child: SafeArea(
                    bottom: false,
                    child: Padding(
                      padding: EdgeInsets.only(top: AppSpacing.containerSm),
                      child: Container(
                        padding: EdgeInsets.symmetric(
                          horizontal: AppSpacing.containerSm,
                          vertical: AppSpacing.xs,
                        ),
                        decoration: BoxDecoration(
                          color: AppColors.black.withValues(alpha: 0.55),
                          borderRadius: BorderRadius.circular(
                            AppSpacing.largeBorderRadius,
                          ),
                        ),
                        child: Text(
                          MediaText.imageEditorMosaicPaintHint,
                          style: TextStyle(
                            color: AppColors.white.withValues(alpha: 0.9),
                            fontSize: AppTypography.sm,
                          ),
                        ),
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

  // ---- 文字会话 ----

  void _prepareTextSession() {
    _textItems.clear();
    _selectedTextItemId = null;
  }

  ImageEditorTextItem? get _selectedTextItem {
    if (_selectedTextItemId == null) return null;
    for (final item in _textItems) {
      if (item.id == _selectedTextItemId) return item;
    }
    return null;
  }

  void _cancelTextAndExit() {
    _setEditorState(() {
      _textItems.clear();
      _selectedTextItemId = null;
      _selectedToolIndex = null;
    });
  }

  Future<void> _promptAddTextItem() async {
    final text = await _promptTextInput(initialText: '');
    if (text == null || text.trim().isEmpty || !mounted) return;
    _setEditorState(() {
      final item = ImageEditorTextItem(
        id: ++_textIdSeed,
        text: text.trim(),
        style: ImageEditorTextStyleKind.plain,
        colorIndex: 0,
        center: const Offset(0.5, 0.5),
        fontSizeOnShortSide: ImageEditorTextItem.defaultFontSizeOnShortSide,
        rotation: 0,
      );
      _textItems.add(item);
      _selectedTextItemId = item.id;
    });
  }

  Future<void> _promptEditTextItem(ImageEditorTextItem item) async {
    final text = await _promptTextInput(initialText: item.text);
    if (text == null || text.trim().isEmpty || !mounted) return;
    _updateTextItem(item.copyWith(text: text.trim()));
  }

  Future<String?> _promptTextInput({required String initialText}) {
    final controller = TextEditingController(text: initialText);
    return showCupertinoDialog<String>(
      context: context,
      barrierDismissible: true,
      builder: (dialogContext) {
        return CupertinoAlertDialog(
          title: Text(MediaText.imageEditorTextEditHint),
          content: Padding(
            padding: EdgeInsets.only(top: AppSpacing.sm),
            child: CupertinoTextField(
              controller: controller,
              autofocus: true,
              maxLines: 3,
              minLines: 1,
              textInputAction: TextInputAction.done,
              onSubmitted: (value) => Navigator.of(dialogContext).pop(value),
            ),
          ),
          actions: [
            CupertinoDialogAction(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: Text(FoundationText.cancel),
            ),
            CupertinoDialogAction(
              isDefaultAction: true,
              onPressed: () => Navigator.of(dialogContext).pop(controller.text),
              child: Text(FoundationText.confirm),
            ),
          ],
        );
      },
    );
  }

  void _updateTextItem(ImageEditorTextItem next) {
    final index = _textItems.indexWhere((item) => item.id == next.id);
    if (index < 0) return;
    _setEditorState(() {
      _textItems[index] = next;
      _selectedTextItemId = next.id;
    });
  }

  void _updateSelectedTextStyle(ImageEditorTextStyleKind style) {
    final selected = _selectedTextItem;
    if (selected == null) return;
    _updateTextItem(selected.copyWith(style: style));
  }

  void _updateSelectedTextColor(int colorIndex) {
    final selected = _selectedTextItem;
    if (selected == null) return;
    _updateTextItem(selected.copyWith(colorIndex: colorIndex));
  }

  void _deleteSelectedTextItem() {
    final selected = _selectedTextItem;
    if (selected == null) return;
    _setEditorState(() {
      _textItems.removeWhere((item) => item.id == selected.id);
      _selectedTextItemId = _textItems.isNotEmpty ? _textItems.last.id : null;
    });
  }

  /// 文字编辑中的中部图层：文字项渲染 + 拖动/缩放/旋转手势。
  Widget _buildTextSessionImageLayer(Widget content) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final viewport = Size(constraints.maxWidth, constraints.maxHeight);
        final imageRect = _resolveImageRect(viewport);
        return Stack(
          fit: StackFit.expand,
          children: [
            content,
            for (final item in _textItems)
              _buildTextItemWidget(item, imageRect),
            if (_textItems.isEmpty)
              Align(
                alignment: Alignment.center,
                child: IgnorePointer(
                  child: Container(
                    padding: EdgeInsets.symmetric(
                      horizontal: AppSpacing.containerSm,
                      vertical: AppSpacing.xs,
                    ),
                    decoration: BoxDecoration(
                      color: AppColors.black.withValues(alpha: 0.55),
                      borderRadius: BorderRadius.circular(
                        AppSpacing.largeBorderRadius,
                      ),
                    ),
                    child: Text(
                      MediaText.imageEditorTextEmptyHint,
                      style: TextStyle(
                        color: AppColors.white.withValues(alpha: 0.9),
                        fontSize: AppTypography.sm,
                      ),
                    ),
                  ),
                ),
              ),
          ],
        );
      },
    );
  }

  Widget _buildTextItemWidget(ImageEditorTextItem item, Rect imageRect) {
    if (imageRect.isEmpty) return const SizedBox.shrink();
    final shortSide = math.min(imageRect.width, imageRect.height);
    final fontSize = item.fontSizeOnShortSide * shortSide;
    final center = Offset(
      imageRect.left + item.center.dx * imageRect.width,
      imageRect.top + item.center.dy * imageRect.height,
    );
    final selected = item.id == _selectedTextItemId;
    final painter = ImageEditorExportEngine.buildTextPainter(
      item,
      fontSize,
      maxWidth: imageRect.width * 0.9,
    );
    final width = painter.width + fontSize * 0.8;
    final height = painter.height + fontSize * 0.8;
    return Positioned(
      left: center.dx - width / 2,
      top: center.dy - height / 2,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: () => _setEditorState(() => _selectedTextItemId = item.id),
        onDoubleTap: () => unawaited(_promptEditTextItem(item)),
        onScaleStart: (_) =>
            _setEditorState(() => _selectedTextItemId = item.id),
        onScaleUpdate: (details) {
          final current = _selectedTextItem;
          if (current == null || current.id != item.id) return;
          var next = current;
          if (details.pointerCount >= 2) {
            next = next.copyWith(
              fontSizeOnShortSide:
                  current.fontSizeOnShortSide * details.scale.clamp(0.6, 1.6),
              rotation: current.rotation + details.rotation,
            );
          }
          final delta = details.focalPointDelta;
          next = next.copyWith(
            center: Offset(
              (current.center.dx + delta.dx / imageRect.width).clamp(0.0, 1.0),
              (current.center.dy + delta.dy / imageRect.height).clamp(0.0, 1.0),
            ),
          );
          _updateTextItem(next);
        },
        child: Transform.rotate(
          angle: item.rotation,
          child: Container(
            width: width,
            height: height,
            alignment: Alignment.center,
            decoration: selected
                ? BoxDecoration(
                    border: Border.all(
                      color: AppColors.white.withValues(alpha: 0.85),
                      width: AppSpacing.xs / 4,
                    ),
                    borderRadius: BorderRadius.circular(
                      AppSpacing.smallBorderRadius,
                    ),
                  )
                : null,
            child: _buildTextItemVisual(item, fontSize),
          ),
        ),
      ),
    );
  }

  Widget _buildTextItemVisual(ImageEditorTextItem item, double fontSize) {
    final textWidget = Text(
      item.text,
      textAlign: TextAlign.center,
      style: TextStyle(
        fontSize: fontSize,
        fontWeight: FontWeight.w600,
        color: item.color,
        shadows: item.style == ImageEditorTextStyleKind.outline
            ? <Shadow>[
                for (final offset in const <Offset>[
                  Offset(1.2, 0),
                  Offset(-1.2, 0),
                  Offset(0, 1.2),
                  Offset(0, -1.2),
                ])
                  Shadow(color: item.outlineColor, offset: offset),
              ]
            : null,
      ),
    );
    if (item.style == ImageEditorTextStyleKind.backgroundBar) {
      return Container(
        padding: EdgeInsets.symmetric(
          horizontal: fontSize * 0.28,
          vertical: fontSize * 0.14,
        ),
        decoration: BoxDecoration(
          color: item.backgroundBarColor,
          borderRadius: BorderRadius.circular(fontSize * 0.24),
        ),
        child: textWidget,
      );
    }
    return textWidget;
  }
}

/// 马赛克笔画预览 painter：与导出引擎共用 buildMosaicStrokePath 的几何。
class _MosaicStrokePreviewPainter extends CustomPainter {
  const _MosaicStrokePreviewPainter({
    required this.imageRect,
    required this.pixelated,
    required this.blurred,
    required this.strokes,
  });

  final Rect imageRect;
  final ui.Image? pixelated;
  final ui.Image? blurred;
  final List<ImageEditorMosaicStroke> strokes;

  @override
  void paint(Canvas canvas, Size size) {
    if (imageRect.isEmpty || strokes.isEmpty) return;
    canvas.save();
    canvas.clipRect(imageRect);
    final byType = <ImageEditorMosaicType, List<ImageEditorMosaicStroke>>{};
    for (final stroke in strokes) {
      byType.putIfAbsent(stroke.type, () => []).add(stroke);
    }
    for (final entry in byType.entries) {
      final source = entry.key == ImageEditorMosaicType.pixelate
          ? pixelated
          : blurred;
      final localPath = ImageEditorExportEngine.buildMosaicStrokePath(
        entry.value,
        imageRect.size,
      ).shift(imageRect.topLeft);
      if (source == null) {
        // 预览资源未就绪时以半透明蒙层反馈笔画位置。
        canvas.drawPath(
          localPath,
          Paint()..color = AppColors.white.withValues(alpha: 0.4),
        );
        continue;
      }
      canvas.saveLayer(imageRect, Paint());
      canvas.drawPath(localPath, Paint()..color = AppColors.white);
      canvas.drawImageRect(
        source,
        Rect.fromLTWH(0, 0, source.width.toDouble(), source.height.toDouble()),
        imageRect,
        Paint()..blendMode = BlendMode.srcIn,
      );
      canvas.restore();
    }
    canvas.restore();
  }

  @override
  bool shouldRepaint(covariant _MosaicStrokePreviewPainter oldDelegate) {
    return oldDelegate.imageRect != imageRect ||
        oldDelegate.strokes != strokes ||
        !identical(oldDelegate.pixelated, pixelated) ||
        !identical(oldDelegate.blurred, blurred);
  }
}
