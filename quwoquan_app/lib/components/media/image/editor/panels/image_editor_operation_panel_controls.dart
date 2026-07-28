part of 'image_editor_operation_panel.dart';

extension _ImageEditorOperationPanelControls on ImageEditorOperationPanel {
  /// 马赛克面板：类型（像素化/模糊）+ 笔刷大小 + 笔画撤销。
  Widget _buildMosaicPanelContent() {
    return Padding(
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              _panelChip(
                MediaText.imageEditorMosaicPixel,
                mosaicType == ImageEditorMosaicType.pixelate,
                onTap: () =>
                    onMosaicTypeChanged(ImageEditorMosaicType.pixelate),
              ),
              SizedBox(width: AppSpacing.intraGroupSm),
              _panelChip(
                MediaText.imageEditorMosaicBlur,
                mosaicType == ImageEditorMosaicType.blur,
                onTap: () => onMosaicTypeChanged(ImageEditorMosaicType.blur),
              ),
              SizedBox(width: AppSpacing.interGroupSm),
              CupertinoButton(
                padding: EdgeInsets.zero,
                minimumSize: Size.square(AppSpacing.minInteractiveSize),
                onPressed: mosaicHasStrokes ? onMosaicUndoStroke : null,
                child: Icon(
                  CupertinoIcons.arrow_uturn_left,
                  size: AppSpacing.iconMedium,
                  color: mosaicHasStrokes
                      ? foregroundColor
                      : foregroundSecondary.withValues(alpha: 0.35),
                ),
              ),
            ],
          ),
          Row(
            children: [
              Text(
                MediaText.imageEditorMosaicSize,
                style: TextStyle(
                  color: foregroundSecondary,
                  fontSize: AppTypography.sm,
                ),
              ),
              Expanded(
                child: SliderTheme(
                  data: SliderThemeData(
                    activeTrackColor: AppColors.white.withValues(alpha: 0.92),
                    inactiveTrackColor: AppColors.white.withValues(alpha: 0.28),
                    thumbColor: AppColors.white,
                  ),
                  child: Slider(
                    value: mosaicBrushSize,
                    onChanged: onMosaicBrushSizeChanged,
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  /// 文字面板：添加按钮 + 选中项样式/颜色/删除。
  Widget _buildTextPanelContent() {
    final selected = selectedTextItem;
    final palette = imageEditorTextPalette();
    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.xs,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              CupertinoButton(
                padding: EdgeInsets.symmetric(horizontal: AppSpacing.sm),
                minimumSize: Size(
                  AppSpacing.minInteractiveSize,
                  AppSpacing.minInteractiveSize,
                ),
                onPressed: onTextAdd,
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      CupertinoIcons.plus_circle,
                      size: AppSpacing.iconMedium,
                      color: foregroundColor,
                    ),
                    SizedBox(width: AppSpacing.xs),
                    Text(
                      MediaText.imageEditorTextAdd,
                      style: TextStyle(
                        color: foregroundColor,
                        fontSize: AppTypography.md,
                      ),
                    ),
                  ],
                ),
              ),
              const Spacer(),
              CupertinoButton(
                padding: EdgeInsets.zero,
                minimumSize: Size.square(AppSpacing.minInteractiveSize),
                onPressed: selected != null ? onTextDelete : null,
                child: Icon(
                  CupertinoIcons.trash,
                  size: AppSpacing.iconMedium,
                  color: selected != null
                      ? foregroundColor
                      : foregroundSecondary.withValues(alpha: 0.35),
                ),
              ),
            ],
          ),
          Row(
            children: [
              _panelChip(
                MediaText.imageEditorTextStylePlain,
                selected?.style == ImageEditorTextStyleKind.plain,
                onTap: selected == null
                    ? null
                    : () => onTextStyleChanged(ImageEditorTextStyleKind.plain),
              ),
              _panelChip(
                MediaText.imageEditorTextStyleOutline,
                selected?.style == ImageEditorTextStyleKind.outline,
                onTap: selected == null
                    ? null
                    : () =>
                          onTextStyleChanged(ImageEditorTextStyleKind.outline),
              ),
              _panelChip(
                MediaText.imageEditorTextStyleBar,
                selected?.style == ImageEditorTextStyleKind.backgroundBar,
                onTap: selected == null
                    ? null
                    : () => onTextStyleChanged(
                        ImageEditorTextStyleKind.backgroundBar,
                      ),
              ),
              const Spacer(),
            ],
          ),
          SizedBox(
            height: AppSpacing.minInteractiveSize,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              itemCount: palette.length,
              separatorBuilder: (context, index) =>
                  SizedBox(width: AppSpacing.intraGroupSm),
              itemBuilder: (context, index) {
                final color = palette[index];
                final isSelected = selected?.colorIndex == index;
                return CupertinoButton(
                  padding: EdgeInsets.zero,
                  minimumSize: Size.square(AppSpacing.minInteractiveSize),
                  onPressed: selected == null
                      ? null
                      : () => onTextColorChanged(index),
                  child: Container(
                    width: AppSpacing.iconLarge,
                    height: AppSpacing.iconLarge,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: color,
                      border: Border.all(
                        color: isSelected
                            ? foregroundColor
                            : foregroundSecondary.withValues(alpha: 0.4),
                        width: isSelected
                            ? AppSpacing.xs / 2
                            : AppSpacing.xs / 4,
                      ),
                    ),
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildPanelBottomBar(BuildContext context) {
    final bottomInset = MediaQuery.paddingOf(context).bottom;
    if (toolIndex == kImageEditorToolCrop) {
      return Padding(
        padding: EdgeInsets.only(
          left: AppSpacing.containerMd,
          right: AppSpacing.containerMd,
          top: AppSpacing.sm,
          bottom: AppSpacing.sm + bottomInset,
        ),
        child: Row(
          children: [
            CupertinoButton(
              padding: EdgeInsets.zero,
              minimumSize: Size.square(AppSpacing.iconButtonMinSizeMd),
              onPressed: onCancelPanel,
              child: Icon(
                CupertinoIcons.xmark,
                color: AppColors.white,
                size: AppSpacing.iconLarge,
              ),
            ),
            Expanded(
              child: Center(
                child: AnimatedSwitcher(
                  duration: Duration(
                    milliseconds: (AppSpacing.buttonSize * 4).round(),
                  ),
                  child: showCropReset
                      ? SizedBox(
                          height: AppSpacing.buttonHeightForSize(
                            DesignSemanticConstants.md,
                          ),
                          child: CupertinoButton(
                            key: const ValueKey('crop-reset'),
                            padding: EdgeInsets.zero,
                            minimumSize: Size.zero,
                            onPressed: onCropReset,
                            child: Container(
                              padding: AppSpacing.buttonPadding(
                                context,
                                DesignSemanticConstants.md,
                              ),
                              decoration: BoxDecoration(
                                color: foregroundSecondary.withValues(
                                  alpha: 0.12,
                                ),
                                borderRadius: BorderRadius.circular(
                                  AppSpacing.largeBorderRadius,
                                ),
                              ),
                              child: Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  Icon(
                                    CupertinoIcons.refresh,
                                    size: AppSpacing.iconMedium,
                                    color: foregroundColor,
                                  ),
                                  SizedBox(width: AppSpacing.xs),
                                  Text(
                                    MediaText.imageEditorCropReset,
                                    style: TextStyle(
                                      color: foregroundColor,
                                      fontSize: AppTypography.md,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        )
                      : const SizedBox.shrink(),
                ),
              ),
            ),
            CupertinoButton(
              padding: EdgeInsets.zero,
              minimumSize: Size.square(AppSpacing.iconButtonMinSizeMd),
              onPressed: onConfirmPanel,
              child: Icon(
                CupertinoIcons.checkmark,
                color: AppColors.white,
                size: AppSpacing.iconLarge,
              ),
            ),
          ],
        ),
      );
    }
    final isFilter = toolIndex == kImageEditorToolFilter;
    final isRotate = toolIndex == kImageEditorToolRotate;
    final showSlider = isFilter;
    return Padding(
      padding: EdgeInsets.only(
        left: AppSpacing.containerMd,
        right: AppSpacing.containerMd,
        top: AppSpacing.sm,
        bottom: AppSpacing.sm + bottomInset,
      ),
      child: Row(
        children: [
          CupertinoButton(
            padding: EdgeInsets.zero,
            minimumSize: Size.square(AppSpacing.iconButtonMinSizeMd),
            onPressed: onCancelPanel,
            child: Icon(
              CupertinoIcons.xmark,
              color: AppColors.white,
              size: AppSpacing.iconLarge,
            ),
          ),
          if (showSlider)
            Expanded(
              child: SliderTheme(
                data: SliderThemeData(
                  activeTrackColor: AppColors.white.withValues(alpha: 0.92),
                  inactiveTrackColor: AppColors.white.withValues(alpha: 0.28),
                  thumbColor: AppColors.white,
                ),
                child: Slider(
                  value: filterIntensity,
                  min: 0,
                  max: 100,
                  onChanged: onFilterIntensityChanged,
                ),
              ),
            )
          else if (isRotate)
            Expanded(
              child: Center(
                child: AnimatedSwitcher(
                  duration: Duration(
                    milliseconds: (AppSpacing.buttonSize * 4).round(),
                  ),
                  child: showRotateReset
                      ? SizedBox(
                          height: AppSpacing.buttonHeightForSize(
                            DesignSemanticConstants.md,
                          ),
                          child: CupertinoButton(
                            key: const ValueKey('rotate-reset'),
                            padding: EdgeInsets.zero,
                            minimumSize: Size.zero,
                            onPressed: onRotateReset,
                            child: Container(
                              padding: AppSpacing.buttonPadding(
                                context,
                                DesignSemanticConstants.md,
                              ),
                              decoration: BoxDecoration(
                                color: AppColors.white.withValues(alpha: 0.12),
                                borderRadius: BorderRadius.circular(
                                  AppSpacing.largeBorderRadius,
                                ),
                              ),
                              child: Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  Icon(
                                    CupertinoIcons.refresh,
                                    size: AppSpacing.iconMedium,
                                    color: AppColors.white,
                                  ),
                                  SizedBox(width: AppSpacing.xs),
                                  Text(
                                    MediaText.imageEditorCropReset,
                                    style: TextStyle(
                                      color: AppColors.white,
                                      fontSize: AppTypography.md,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        )
                      : const SizedBox.shrink(),
                ),
              ),
            )
          else
            const Spacer(),
          CupertinoButton(
            padding: EdgeInsets.zero,
            minimumSize: Size.square(AppSpacing.iconButtonMinSizeMd),
            onPressed: onConfirmPanel,
            child: Icon(
              CupertinoIcons.checkmark,
              color: AppColors.white,
              size: AppSpacing.iconLarge,
            ),
          ),
        ],
      ),
    );
  }

  /// 与专业工具、裁剪比例一致：统一使用工具面板功能项语义（图标、字号、间距、默认色）
  Widget _buildRotateActionItem({
    required IconData icon,
    required String label,
    required VoidCallback onTap,
    int rotateQuarterTurns = 0,
  }) {
    final color = foregroundSecondary.withValues(alpha: 0.75);
    return Expanded(
      child: GestureDetector(
        onTap: onTap,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            RotatedBox(
              quarterTurns: rotateQuarterTurns,
              child: Icon(
                icon,
                color: color,
                size: AppSpacing.toolPanelItemIconSize,
              ),
            ),
            SizedBox(height: AppSpacing.toolPanelItemIconLabelGap),
            Text(
              label,
              textAlign: TextAlign.center,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: color,
                fontSize: AppTypography.toolPanelItemLabel,
                fontWeight: FontWeight.normal,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildCropRatioSelector() {
    final items = [
      _CropRatioEntry(
        label: MediaText.imageEditorCropOriginal,
        value: 'original',
      ),
      _CropRatioEntry(
        label: MediaText.imageEditorCropFree,
        value: 'free',
      ),
      _CropRatioEntry(
        label: MediaText.imageEditorCropRatio1x1,
        value: '1x1',
        previewRatio: 1,
      ),
      _CropRatioEntry(
        label: MediaText.imageEditorCropRatio2x3,
        value: '2x3',
        previewRatio: 2 / 3,
      ),
      _CropRatioEntry(
        label: MediaText.imageEditorCropRatio3x2,
        value: '3x2',
        previewRatio: 3 / 2,
      ),
      _CropRatioEntry(
        label: MediaText.imageEditorCropRatio3x4,
        value: '3x4',
        previewRatio: 3 / 4,
      ),
      _CropRatioEntry(
        label: MediaText.imageEditorCropRatio4x3,
        value: '4x3',
        previewRatio: 4 / 3,
      ),
      _CropRatioEntry(
        label: MediaText.imageEditorCropRatio9x16,
        value: '9x16',
        previewRatio: 9 / 16,
      ),
      _CropRatioEntry(
        label: MediaText.imageEditorCropRatio16x9,
        value: '16x9',
        previewRatio: 16 / 9,
      ),
    ];
    return LayoutBuilder(
      builder: (context, constraints) {
        final gap = AppSpacing.intraGroupSm;
        final sidePadding = AppSpacing.containerSm;
        final available = (constraints.maxWidth - sidePadding * 2).clamp(
          0.0,
          constraints.maxWidth,
        );
        final desiredItemWidth = AppSpacing.buttonHeight * 1.4;
        var count = ((available + gap) / (desiredItemWidth + gap)).floor();
        count = count.clamp(3, 7);
        final itemWidth =
            (available - gap * (count - 1)).clamp(0.0, available) / count;
        return ListView.separated(
          controller: cropRatioScrollController,
          scrollDirection: Axis.horizontal,
          padding: EdgeInsets.symmetric(horizontal: sidePadding, vertical: gap),
          itemBuilder: (context, index) {
            final entry = items[index];
            final selected = cropRatio == entry.value;
            return SizedBox(
              width: itemWidth,
              child: _buildCropRatioItem(entry, selected),
            );
          },
          separatorBuilder: (context, index) => SizedBox(width: gap),
          itemCount: items.length,
        );
      },
    );
  }

  Widget _buildCropRatioItem(_CropRatioEntry entry, bool selected) {
    final borderColor = selected
        ? foregroundColor
        : foregroundSecondary.withValues(alpha: 0.5);
    final labelColor = selected
        ? foregroundColor
        : foregroundSecondary.withValues(alpha: 0.75);
    final borderWidth = selected
        ? AppSpacing.toolPanelItemBorderWidthSelected
        : AppSpacing.toolPanelItemBorderWidthUnselected;
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.zero,
      onPressed: () => onCropRatioChanged(entry.value),
      child: SizedBox(
        width: double.infinity,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            SizedBox(
              height: AppSpacing.toolPanelItemIconSize,
              child: Center(
                child: _buildCropPreview(
                  entry,
                  AppSpacing.toolPanelItemIconSize,
                  borderColor,
                  borderWidth,
                  labelColor,
                ),
              ),
            ),
            SizedBox(height: AppSpacing.toolPanelItemIconLabelGap),
            Text(
              entry.label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: AppTypography.toolPanelItemLabel,
                fontWeight: selected ? FontWeight.w600 : FontWeight.normal,
                color: labelColor,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildCropPreview(
    _CropRatioEntry entry,
    double previewSize,
    Color borderColor,
    double borderWidth,
    Color labelColor,
  ) {
    final ratio = entry.previewRatio;
    if (ratio == null) {
      return Icon(
        entry.value == 'free' ? Icons.crop_free : Icons.crop,
        color: labelColor,
        size: previewSize,
      );
    }
    final width = ratio >= 1 ? previewSize : previewSize * ratio;
    final height = ratio >= 1 ? previewSize / ratio : previewSize;
    final minSide = AppSpacing.smallBorderRadius;
    return SizedBox(
      width: width,
      height: height,
      child: DecoratedBox(
        decoration: BoxDecoration(
          border: Border.all(color: borderColor, width: borderWidth),
          borderRadius: BorderRadius.circular(minSide),
        ),
      ),
    );
  }
}

class _ProAdjustmentLine extends StatefulWidget {
  const _ProAdjustmentLine({
    required this.value,
    required this.min,
    required this.max,
    required this.onChanged,
    this.trackHeight,
    this.trackGradient,
  });

  final double value;
  final double min;
  final double max;
  final ValueChanged<double> onChanged;
  final double? trackHeight;
  final Gradient? trackGradient;

  @override
  State<_ProAdjustmentLine> createState() => _ProAdjustmentLineState();
}

class _ProAdjustmentLineState extends State<_ProAdjustmentLine> {
  bool _dragging = false;
  double _dragValue = 0;

  @override
  Widget build(BuildContext context) {
    final range = (widget.max - widget.min).abs();
    final normalized = range == 0
        ? 0.5
        : ((widget.value - widget.min) / (widget.max - widget.min)).clamp(
            0.0,
            1.0,
          );
    return LayoutBuilder(
      builder: (context, constraints) {
        final width = constraints.maxWidth;
        final knobX = width * normalized;
        final centerX = width * 0.5;
        final range = (widget.max - widget.min).abs();
        final valuePerPixel = width <= 0 ? 0.0 : range / width;
        return GestureDetector(
          behavior: HitTestBehavior.opaque,
          onHorizontalDragStart: (_) {
            _dragValue = widget.value;
            setState(() => _dragging = true);
          },
          onHorizontalDragUpdate: (details) {
            if (valuePerPixel == 0) return;
            final next = (_dragValue + details.delta.dx * valuePerPixel)
                .clamp(widget.min, widget.max)
                .toDouble();
            _dragValue = next;
            widget.onChanged(next);
          },
          onHorizontalDragEnd: (_) => setState(() => _dragging = false),
          onHorizontalDragCancel: () => setState(() => _dragging = false),
          child: SizedBox(
            height: AppSpacing.buttonHeight + AppSpacing.xs * 2,
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: AppColors.white.withValues(
                  alpha: _dragging ? 0.10 : 0.06,
                ),
                borderRadius: BorderRadius.circular(
                  AppSpacing.largeBorderRadius,
                ),
              ),
              child: Stack(
                alignment: Alignment.center,
                children: [
                  Container(
                    height: widget.trackHeight ?? AppSpacing.xs / 2,
                    decoration: BoxDecoration(
                      color: widget.trackGradient == null
                          ? AppColors.white.withValues(alpha: 0.25)
                          : null,
                      gradient: widget.trackGradient,
                      borderRadius: BorderRadius.circular(AppSpacing.xs),
                    ),
                  ),
                  Positioned(
                    left: math.min(centerX, knobX),
                    right: width - math.max(centerX, knobX),
                    child: Container(
                      height: widget.trackHeight ?? AppSpacing.xs / 2,
                      decoration: BoxDecoration(
                        color: AppColors.white.withValues(
                          alpha: widget.trackGradient == null ? 0.85 : 0.45,
                        ),
                        borderRadius: BorderRadius.circular(AppSpacing.xs),
                      ),
                    ),
                  ),
                  Positioned(
                    left: (centerX - AppSpacing.xs / 4).clamp(
                      0.0,
                      math.max(0.0, width - AppSpacing.xs / 2),
                    ),
                    child: Container(
                      width: AppSpacing.xs / 2,
                      height: AppSpacing.sm,
                      decoration: BoxDecoration(
                        color: AppColors.white.withValues(alpha: 0.5),
                        borderRadius: BorderRadius.circular(AppSpacing.xs / 4),
                      ),
                    ),
                  ),
                  Positioned(
                    left: (knobX - AppSpacing.xs).clamp(
                      0.0,
                      math.max(0.0, width - AppSpacing.xs * 2),
                    ),
                    child: Container(
                      width: AppSpacing.xs * 2,
                      height: AppSpacing.sm + AppSpacing.xs,
                      decoration: BoxDecoration(
                        color: AppColors.white,
                        borderRadius: BorderRadius.circular(AppSpacing.xs),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}

class _LocalControlButtonItem {
  const _LocalControlButtonItem({
    required this.icon,
    required this.selected,
    required this.label,
    required this.onTap,
  });

  final IconData icon;
  final bool selected;
  final String label;
  final VoidCallback onTap;
}

class _CropRatioEntry {
  const _CropRatioEntry({
    required this.label,
    required this.value,
    this.previewRatio,
  });

  final String label;
  final String value;
  final double? previewRatio;
}
