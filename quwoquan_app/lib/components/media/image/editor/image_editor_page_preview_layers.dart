part of 'image_editor_page.dart';

extension _ImageEditorPagePreviewLayers on _ImageEditorPageState {
  double get _thumbnailStripHorizontalPadding =>
      AppSpacing.semantic[DesignSemanticConstants
          .container]?[DesignSemanticConstants.sm] ??
      AppSpacing.containerSm;

  void _reorderThumbnails(int oldIndex, int newIndex) {
    if (oldIndex < 0 ||
        oldIndex >= _paths.length ||
        newIndex < 0 ||
        newIndex > _paths.length ||
        oldIndex == newIndex) {
      return;
    }
    final currentPath = _currentPath;
    final next = List<String>.of(_paths);
    final moved = next.removeAt(oldIndex);
    final target = oldIndex < newIndex ? newIndex - 1 : newIndex;
    next.insert(target, moved);
    final nextCurrent = next.indexOf(currentPath);
    _setEditorState(() {
      _paths = next;
      _currentIndex = nextCurrent < 0 ? target : nextCurrent;
    });
    _pageController?.jumpToPage(_currentIndex);
    _scrollThumbToIndex(_currentIndex);
  }

  void _scrollThumbToIndex(int index) {
    final c = _thumbScrollController;
    if (c == null || !c.hasClients) return;
    final thumbSize = AppSpacing.bottomNavHeight;
    final thumbStride = thumbSize + AppSpacing.intraGroupSm;
    final horizontalPad = _thumbnailStripHorizontalPadding;
    final itemStart = horizontalPad + (index * thumbStride);
    final itemEnd = itemStart + thumbSize;
    final visibleStart = c.offset;
    final visibleEnd = c.offset + c.position.viewportDimension;
    double? targetOffset;
    if (itemStart < visibleStart + horizontalPad) {
      targetOffset = itemStart - horizontalPad;
    } else if (itemEnd > visibleEnd - horizontalPad) {
      targetOffset = itemEnd - c.position.viewportDimension + horizontalPad;
    }
    if (targetOffset == null) {
      return;
    }
    c.animateTo(
      targetOffset.clamp(0.0, c.position.maxScrollExtent),
      duration: Duration(milliseconds: (AppSpacing.buttonSize * 4).round()),
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
      // 统一拖拽重排：长按缩略图起拖 + 兄弟实时让位 + 松手提交，复用 MediaReorderableView。
      // tap 仍切换预览页；外部 _thumbScrollController 保留「切页自动滚动到选中缩略图」。
      child: MediaReorderableView(
        layout: MediaReorderableLayout.strip,
        controller: _thumbScrollController,
        itemCount: _paths.length,
        spacing: AppSpacing.intraGroupSm,
        itemSize: Size(thumbSize, thumbSize),
        padding: EdgeInsets.symmetric(
          horizontal: _thumbnailStripHorizontalPadding,
        ),
        onReorder: _reorderThumbnails,
        itemBuilder: (context, index, isDragging) {
          final path = _paths[index];
          final isSelected = index == _currentIndex;
          return GestureDetector(
            onTap: () {
              _pageController?.jumpToPage(index);
              _setEditorState(() => _currentIndex = index);
              _scrollThumbToIndex(index);
            },
            child: Container(
              key: ValueKey<String>('image-editor-thumb-$path'),
              width: thumbSize,
              height: thumbSize,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(
                  AppSpacing.semantic[DesignSemanticConstants
                          .button]?[DesignSemanticConstants.sm] ??
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
                  (AppSpacing.semantic[DesignSemanticConstants
                              .button]?[DesignSemanticConstants.sm] ??
                          AppSpacing.smallBorderRadius) -
                      1,
                ),
                child: _buildThumbnailImage(path, fgSecondary),
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _buildThumbnailImage(String path, Color fgSecondary) {
    final isFile = path.startsWith('/') || (path.length > 1 && path[1] == ':');
    if (isFile && File(path).existsSync()) {
      return Image.file(
        File(path),
        fit: BoxFit.cover,
        errorBuilder: (context, error, stackTrace) => Icon(
          Icons.broken_image_outlined,
          size: AppSpacing.iconMedium,
          color: fgSecondary,
        ),
      );
    }
    if (!isFile) {
      return AppCachedNetworkImage(
        imageUrl: path,
        fit: BoxFit.cover,
        cdnPreset: CdnImagePreset.thumbnail,
        errorWidget: Icon(
          Icons.broken_image_outlined,
          size: AppSpacing.iconMedium,
          color: fgSecondary,
        ),
      );
    }
    return Icon(
      Icons.broken_image_outlined,
      size: AppSpacing.iconMedium,
      color: fgSecondary,
    );
  }

  Widget _buildMiddleImage(Color fgSecondary) {
    return _buildMiddleImageForPath(_currentPath, fgSecondary);
  }

  Widget _buildMiddleImageForPath(String path, Color fgSecondary) {
    if (path.isEmpty) {
      return Center(
        child: Text(
          FoundationText.loadFailed,
          style: TextStyle(color: fgSecondary),
        ),
      );
    }
    final isFile = path.startsWith('/') || (path.length > 1 && path[1] == ':');
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
      imageWidget = AppCachedNetworkImage(
        imageUrl: path,
        fit: BoxFit.contain,
        cdnPreset: CdnImagePreset.full,
        errorWidget: Icon(
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
    imageWidget = _wrapWithProAdjustments(imageWidget);
    final previewWidget = _selectedToolIndex == kImageEditorToolRotate
        ? _buildRotatePreview(imageWidget)
        : imageWidget;
    final isHslEditing = _isEditingHsl;
    final isBwEditing = _isEditingBwLevels;
    final isLocalEditing = _isEditingLocal;
    final isCurveEditing = _isEditingCurve;
    final isWbEditing = _isEditingWhiteBalance;
    final isMosaicEditing = _isEditingMosaic;
    final isTextEditing = _isEditingText;
    final usesSessionLayer =
        isHslEditing ||
        isBwEditing ||
        isLocalEditing ||
        isCurveEditing ||
        isWbEditing ||
        isMosaicEditing ||
        isTextEditing;
    final content = _selectedToolIndex == kImageEditorToolCrop
        ? _buildCropImageLayer(previewWidget)
        : usesSessionLayer
        ? Center(child: previewWidget)
        : InteractiveViewer(
            minScale: 0.5,
            maxScale: 4,
            child: Center(child: previewWidget),
          );
    if (_selectedToolIndex == kImageEditorToolCrop) {
      return Stack(
        alignment: Alignment.center,
        children: [content, _buildCropOverlay()],
      );
    }
    if (_selectedToolIndex == kImageEditorToolRotate) {
      return Stack(
        fit: StackFit.expand,
        children: [content, _buildRotateGridOverlay()],
      );
    }
    if (isCurveEditing) {
      return _buildCurveSessionImageLayer(content);
    }
    if (isWbEditing) {
      return _buildWbSessionImageLayer(content);
    }
    if (isMosaicEditing) {
      return _buildMosaicSessionImageLayer(content);
    }
    if (isTextEditing) {
      return _buildTextSessionImageLayer(content);
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
      onPanUpdate: canDrag
          ? (details) => _updateCropImageOffset(details.delta)
          : null,
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
              ? (details) =>
                    _handleHslPickerTap(details.localPosition, imageSize)
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
                        color: AppColors.transparent,
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
                    onCompareStart: () => _setEditorState(
                      () => _isComparingSessionBaseline = true,
                    ),
                    onCompareEnd: () => _setEditorState(
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

  /// 白平衡编辑层：矩阵预览已在 _wrapWithProAdjustments 中生效，仅叠加对比条。
  Widget _buildWbSessionImageLayer(Widget content) {
    return _buildBwSessionImageLayer(content);
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
              _setEditorState(() => _localShowAnchorMenu = false);
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
                    onCompareStart: () => _setEditorState(
                      () => _isComparingSessionBaseline = true,
                    ),
                    onCompareEnd: () => _setEditorState(
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
}
