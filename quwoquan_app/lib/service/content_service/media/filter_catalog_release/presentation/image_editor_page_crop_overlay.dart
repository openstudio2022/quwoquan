part of 'image_editor_page.dart';

extension _ImageEditorPageCropOverlay on _ImageEditorPageState {
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
        border: Border.all(color: gridColor, width: AppSpacing.xs / 2),
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
    final ratio =
        _ratioForCrop(_cropRatio) ?? (imageRect.width / imageRect.height);
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
    _setEditorState(() {
      _cropRect = Rect.fromLTRB(left, top, right, bottom);
      _cropEdited = _isCropStateDirty();
    });
  }

  void _updateCropImageOffset(Offset delta) {
    if (_cropRatio == 'free') return;
    final baseRect = _cropImageRect;
    if (baseRect.isEmpty) {
      _setEditorState(() {
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
    _setEditorState(() {
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
    return Offset(offset.dx.clamp(minDx, maxDx), offset.dy.clamp(minDy, maxDy));
  }

  Widget _buildRotateGridOverlay() {
    return ImageEditorRotateOverlay(
      rotateFineDegrees: _rotateFineDegrees,
      isRotateEdited: _isRotateEdited,
      imageAspectRatio: _imageAspectRatio ?? 1,
      onFineDragUpdate: _setRotateFineDegrees,
    );
  }
}
