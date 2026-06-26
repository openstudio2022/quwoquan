part of 'image_editor_page.dart';

extension _ImageEditorPageLocalPreviewLayers on _ImageEditorPageState {
  List<double> _buildLocalAnchorColorMatrix(LocalAnchor anchor) {
    return _buildBaseColorMatrixFromValues(anchor.values);
  }

  List<Widget> _buildLocalPreviewLayers(Widget content, Rect imageRect) {
    if (imageRect.isEmpty) return const [];
    final sourceAnchors = _isComparingSessionBaseline
        ? _localSnapshotAnchors
        : _localAnchors;
    final layers = <Widget>[];
    for (final anchor in sourceAnchors) {
      final hasEffect = anchor.values.values.any(
        (value) => value.abs() > 0.001,
      );
      if (!hasEffect) continue;
      final center = Offset(
        imageRect.left + anchor.center.dx * imageRect.width,
        imageRect.top + anchor.center.dy * imageRect.height,
      );
      final radius =
          (anchor.radius * math.min(imageRect.width, imageRect.height)).clamp(
            AppSpacing.iconLarge.toDouble(),
            imageRect.longestSide,
          );
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
                  AppColors.transparent,
                ],
                const <double>[0.0, 0.22, 0.56, 0.84, 1.0],
              ),
              child: ColorFiltered(
                colorFilter: ColorFilter.matrix(
                  _buildLocalAnchorColorMatrix(anchor),
                ),
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
      final radius =
          (anchor.radius * math.min(imageRect.width, imageRect.height)).clamp(
            AppSpacing.iconLarge.toDouble(),
            imageRect.longestSide,
          );
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
      final center =
          _draggingAnchorId == anchor.id && _draggingAnchorCenter != null
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
              _setEditorState(() {
                _selectedLocalAnchorId = anchor.id;
                _localShowAnchorMenu = true;
              });
            },
            onScaleStart: (_) {
              _setEditorState(() {
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
                (base.dx + details.focalPointDelta.dx).clamp(
                  imageRect.left,
                  imageRect.right,
                ),
                (base.dy + details.focalPointDelta.dy).clamp(
                  imageRect.top,
                  imageRect.bottom,
                ),
              );
              _setEditorState(() {
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
              _setEditorState(() {
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
            child: Container(
              decoration: BoxDecoration(
                color: AppColors.white,
                borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  CupertinoButton(
                    padding: EdgeInsets.symmetric(horizontal: AppSpacing.sm),
                    minimumSize: Size.zero,
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
                  CupertinoButton(
                    padding: EdgeInsets.symmetric(horizontal: AppSpacing.sm),
                    minimumSize: Size.zero,
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
    final value = (anchor.values[anchor.selectedParam] ?? 0).clamp(
      -100.0,
      100.0,
    );
    return SizedBox(
      width: size,
      height: size,
      child: CustomPaint(
        painter: _LocalAnchorRingPainter(value: value, selected: selected),
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
      _setEditorState(() => _hslPickerPoint = null);
      return;
    }
    final nx = ((localPosition.dx - imageRect.left) / imageRect.width).clamp(
      0.0,
      1.0,
    );
    final ny = ((localPosition.dy - imageRect.top) / imageRect.height).clamp(
      0.0,
      1.0,
    );
    final hue = await _sampleImageHueAt(Offset(nx, ny));
    if (!mounted || hue == null) return;
    _setEditorState(() {
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
      final x = (normalized.dx * (image.width - 1)).round().clamp(
        0,
        image.width - 1,
      );
      final y = (normalized.dy * (image.height - 1)).round().clamp(
        0,
        image.height - 1,
      );
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
}
