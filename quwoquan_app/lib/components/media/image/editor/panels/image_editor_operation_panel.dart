import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/components/media/image/editor/tool_list/image_editor_pro_tool_entries.dart';
import 'package:quwoquan_app/components/media/image/editor/tool_list/image_editor_pro_tool_list.dart';
import 'package:quwoquan_app/components/media/image/editor/tool_list/image_editor_tool_constants.dart';

class ImageEditorOperationPanel extends StatelessWidget {
  const ImageEditorOperationPanel({
    super.key,
    required this.backgroundColor,
    required this.foregroundColor,
    required this.foregroundSecondary,
    required this.bottomInset,
    required this.toolIndex,
    required this.selectedProToolIndex,
    required this.selectedProCategory,
    required this.proToolScrollController,
    required this.onSelectProTool,
    required this.onSelectProCategory,
    required this.onProToolScrollSync,
    required this.onExitProPanel,
    required this.onConfirmProPanel,
    required this.onCancelProTool,
    required this.onConfirmProTool,
    required this.onCancelPanel,
    required this.onConfirmPanel,
    required this.showCropReset,
    required this.onCropReset,
    this.cropRatioScrollController,
    required this.cropRatio,
    required this.onCropRatioChanged,
    required this.filterCategoryIndex,
    required this.filterTemplateIndex,
    required this.filterIntensity,
    required this.onFilterCategoryChanged,
    required this.onFilterTemplateChanged,
    required this.onFilterIntensityChanged,
    required this.beautyTemplateIndex,
    required this.beautyIntensity,
    required this.onBeautyTemplateChanged,
    required this.onBeautyIntensityChanged,
    required this.mosaicTypeIndex,
    required this.mosaicBrushSize,
    required this.onMosaicTypeChanged,
    required this.onMosaicBrushSizeChanged,
    required this.frameTemplateIndex,
    required this.onFrameTemplateChanged,
    required this.textStyleIndex,
    required this.textColorIndex,
    required this.onTextStyleChanged,
    required this.onTextColorChanged,
    required this.rotateDegrees,
    required this.rotateFineDegrees,
    required this.flipHorizontal,
    required this.flipVertical,
    required this.onRotateLeft,
    required this.onRotateRight,
    required this.onRotateFineChanged,
    required this.onFlipHorizontal,
    required this.onFlipVertical,
    required this.showRotateReset,
    required this.onRotateReset,
    required this.curveBrightness,
    required this.curveContrast,
    required this.whiteBalanceTemp,
    required this.onCurveBrightnessChanged,
    required this.onCurveContrastChanged,
    required this.onWhiteBalanceTempChanged,
  });

  final Color backgroundColor;
  final Color foregroundColor;
  final Color foregroundSecondary;
  final double bottomInset;
  final int toolIndex;
  final int? selectedProToolIndex;
  final int selectedProCategory;
  final ScrollController proToolScrollController;
  final ValueChanged<int> onSelectProTool;
  final ValueChanged<int> onSelectProCategory;
  final void Function(double viewportWidth, double itemWidth) onProToolScrollSync;
  final VoidCallback onExitProPanel;
  final VoidCallback onConfirmProPanel;
  final VoidCallback onCancelProTool;
  final VoidCallback onConfirmProTool;
  final VoidCallback onCancelPanel;
  final VoidCallback onConfirmPanel;
  final bool showCropReset;
  final VoidCallback onCropReset;
  final ScrollController? cropRatioScrollController;
  final String cropRatio;
  final ValueChanged<String> onCropRatioChanged;
  final int filterCategoryIndex;
  final int filterTemplateIndex;
  final double filterIntensity;
  final ValueChanged<int> onFilterCategoryChanged;
  final ValueChanged<int> onFilterTemplateChanged;
  final ValueChanged<double> onFilterIntensityChanged;
  final int beautyTemplateIndex;
  final double beautyIntensity;
  final ValueChanged<int> onBeautyTemplateChanged;
  final ValueChanged<double> onBeautyIntensityChanged;
  final int mosaicTypeIndex;
  final double mosaicBrushSize;
  final ValueChanged<int> onMosaicTypeChanged;
  final ValueChanged<double> onMosaicBrushSizeChanged;
  final int frameTemplateIndex;
  final ValueChanged<int> onFrameTemplateChanged;
  final int textStyleIndex;
  final int textColorIndex;
  final ValueChanged<int> onTextStyleChanged;
  final ValueChanged<int> onTextColorChanged;
  final int rotateDegrees;
  final double rotateFineDegrees;
  final bool flipHorizontal;
  final bool flipVertical;
  final VoidCallback onRotateLeft;
  final VoidCallback onRotateRight;
  final ValueChanged<double> onRotateFineChanged;
  final VoidCallback onFlipHorizontal;
  final VoidCallback onFlipVertical;
  final bool showRotateReset;
  final VoidCallback onRotateReset;
  final double curveBrightness;
  final double curveContrast;
  final double whiteBalanceTemp;
  final ValueChanged<double> onCurveBrightnessChanged;
  final ValueChanged<double> onCurveContrastChanged;
  final ValueChanged<double> onWhiteBalanceTempChanged;

  @override
  Widget build(BuildContext context) {
    final borderColor = AppColorsFunctional.getColor(
      true,
      ColorType.borderPrimary,
    ).withValues(alpha: 0.3);
    final panelBg = toolIndex == kImageEditorToolCrop
        ? AppColors.black
        : backgroundColor;
    final panelHeight = AppSpacing.bottomNavHeight * 4;
    return Container(
      height: panelHeight,
      decoration: BoxDecoration(
        color: panelBg,
        border: Border(top: BorderSide(color: borderColor)),
      ),
      child: toolIndex == kImageEditorToolPro
          ? _buildProToolsPanel()
          : Column(
              children: [
                _buildPanelTopContent(),
                Expanded(
                  child: _buildPanelMiddleContent(),
                ),
                _buildPanelBottomBar(context),
              ],
            ),
    );
  }

  Widget _buildProToolsPanel() {
    final activeToolIndex = selectedProToolIndex;
    final showToolDetail = activeToolIndex != null;
    if (showToolDetail) {
      final entry = kImageEditorProToolEntries[activeToolIndex];
      return Column(
        children: [
          SizedBox(height: AppSpacing.subTabNavigationHeight),
          Expanded(
            child: _buildProToolDetailContent(entry),
          ),
          _buildProToolBottomBar(),
        ],
      );
    }
    return Column(
      children: [
        ImageEditorProCategoryTabs(
          selectedCategory: selectedProCategory,
          onCategoryTap: onSelectProCategory,
        ),
        ImageEditorProToolList(
          selectedToolIndex: selectedProToolIndex,
          scrollController: proToolScrollController,
          onToolTap: onSelectProTool,
          onScrollSync: onProToolScrollSync,
        ),
        const Spacer(),
        _buildProPanelExitBar(),
      ],
    );
  }

  Widget _buildProToolDetailContent(ImageEditorProToolEntry entry) {
    switch (entry.type) {
      case 'curve':
        return Center(
          child: Text(
            UITextConstants.imageEditorProCurve,
            style: TextStyle(
              color: foregroundSecondary,
              fontSize: AppTypography.sm,
            ),
          ),
        );
      case 'whiteBalance':
        return Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                UITextConstants.imageEditorProColorTemp,
                style: TextStyle(
                  fontSize: AppTypography.sm,
                  color: foregroundSecondary,
                ),
              ),
              Slider(
                value: whiteBalanceTemp,
                onChanged: onWhiteBalanceTempChanged,
                activeColor: AppColors.primaryColor,
              ),
            ],
          ),
        );
      case 'brightness':
        return _buildDualSliderPanel(
          leftLabel: UITextConstants.imageEditorProBrightness,
          leftValue: curveBrightness,
          onLeftChanged: onCurveBrightnessChanged,
          rightLabel: UITextConstants.imageEditorProContrast,
          rightValue: curveContrast,
          onRightChanged: onCurveContrastChanged,
        );
      default:
        return Center(
          child: Text(
            entry.label,
            style: TextStyle(
              color: foregroundSecondary,
              fontSize: AppTypography.sm,
            ),
          ),
        );
    }
  }

  Widget _buildDualSliderPanel({
    required String leftLabel,
    required double leftValue,
    required ValueChanged<double> onLeftChanged,
    required String rightLabel,
    required double rightValue,
    required ValueChanged<double> onRightChanged,
  }) {
    return SingleChildScrollView(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            leftLabel,
            style: TextStyle(fontSize: AppTypography.sm, color: foregroundSecondary),
          ),
          Slider(
            value: leftValue,
            onChanged: onLeftChanged,
            activeColor: AppColors.primaryColor,
          ),
          Text(
            rightLabel,
            style: TextStyle(fontSize: AppTypography.sm, color: foregroundSecondary),
          ),
          Slider(
            value: rightValue,
            onChanged: onRightChanged,
            activeColor: AppColors.primaryColor,
          ),
        ],
      ),
    );
  }

  Widget _buildProToolBottomBar() {
    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerMd,
        vertical: AppSpacing.sm,
      ),
      child: Row(
        children: [
          IconButton(
            icon: Icon(
              Icons.close,
              color: AppColors.white,
              weight: 700,
            ),
            onPressed: onCancelProTool,
            tooltip: UITextConstants.cancel,
          ),
          const Spacer(),
          IconButton(
            icon: Icon(
              Icons.check,
              color: AppColors.white,
              weight: 700,
            ),
            onPressed: onConfirmProTool,
            tooltip: UITextConstants.confirm,
          ),
        ],
      ),
    );
  }

  Widget _buildProPanelExitBar() {
    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerMd,
        vertical: AppSpacing.sm,
      ),
      child: Row(
        children: [
          IconButton(
            icon: Icon(
              Icons.close,
              color: AppColors.white,
              weight: 700,
            ),
            onPressed: onExitProPanel,
            tooltip: UITextConstants.cancel,
          ),
          const Spacer(),
          IconButton(
            icon: Icon(
              Icons.check,
              color: AppColors.white,
              weight: 700,
            ),
            onPressed: onConfirmProPanel,
            tooltip: UITextConstants.confirm,
          ),
        ],
      ),
    );
  }

  Widget _buildPanelTopContent() {
    if (toolIndex == kImageEditorToolCrop) {
      return const SizedBox.shrink();
    }
    if (toolIndex == kImageEditorToolFilter) {
      final categories = [
        UITextConstants.imageEditorFilterRecommended,
        UITextConstants.imageEditorFilterQuality,
        UITextConstants.imageEditorFilterSpring,
      ];
      return SizedBox(
        height: AppSpacing.subTabNavigationHeight,
        child: ListView(
          scrollDirection: Axis.horizontal,
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.containerSm,
            vertical: AppSpacing.xs,
          ),
          children: [
            _panelChip(
              UITextConstants.imageEditOriginal,
              filterCategoryIndex == 0,
              onTap: () => onFilterCategoryChanged(0),
            ),
            ...List.generate(categories.length, (i) {
              return Padding(
                padding: EdgeInsets.only(left: AppSpacing.intraGroupSm),
                child: _panelChip(
                  categories[i],
                  filterCategoryIndex == i + 1,
                  onTap: () => onFilterCategoryChanged(i + 1),
                ),
              );
            }),
          ],
        ),
      );
    }
    return SizedBox(height: AppSpacing.subTabNavigationHeight);
  }

  Widget _buildPanelMiddleContent() {
    if (toolIndex == kImageEditorToolCrop) {
      return Align(
        alignment: Alignment.bottomCenter,
        child: Padding(
          padding: EdgeInsets.only(bottom: AppSpacing.intraGroupSm),
          child: SizedBox(
            height: AppSpacing.bottomNavHeight * 1.6,
            child: _buildCropRatioSelector(),
          ),
        ),
      );
    }
    if (toolIndex == kImageEditorToolRotate) {
      // 旋转工具：四个功能项等间距居中对齐（向左90°/向右90°/水平翻转/垂直翻转）
      return Padding(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.semantic[DesignSemanticConstants.container]
                  ?[DesignSemanticConstants.sm] ??
              AppSpacing.containerSm,
          vertical: AppSpacing.xs,
        ),
        child: Row(
          children: [
            _buildRotateActionItem(
              icon: Icons.rotate_left,
              label: UITextConstants.imageEditorRotateLeft90,
              onTap: onRotateLeft,
            ),
            _buildRotateActionItem(
              icon: Icons.rotate_right,
              label: UITextConstants.imageEditorRotateRight90,
              onTap: onRotateRight,
            ),
            _buildRotateActionItem(
              icon: Icons.flip,
              label: UITextConstants.imageEditorFlipHorizontal,
              onTap: onFlipHorizontal,
            ),
            _buildRotateActionItem(
              icon: Icons.flip,
              rotateQuarterTurns: 1,
              label: UITextConstants.imageEditorFlipVertical,
              onTap: onFlipVertical,
            ),
          ],
        ),
      );
    }
    if (toolIndex == kImageEditorToolFilter) {
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
          final selected = filterTemplateIndex == i;
          return Padding(
            padding: EdgeInsets.only(right: AppSpacing.sm),
            child: GestureDetector(
              onTap: () => onFilterTemplateChanged(i),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    width: AppSpacing.bottomNavHeight,
                    height: AppSpacing.bottomNavHeight,
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                      border: Border.all(
                        color: selected
                            ? AppColors.primaryColor
                            : foregroundSecondary.withValues(alpha: 0.3),
                        width: selected ? AppSpacing.xs / 2 : AppSpacing.xs / 4,
                      ),
                    ),
                  ),
                  SizedBox(height: AppSpacing.xs),
                  Text(
                    templates[i],
                    style: TextStyle(
                      fontSize: AppTypography.xs,
                      color: selected ? AppColors.primaryColor : foregroundSecondary,
                    ),
                  ),
                ],
              ),
            ),
          );
        },
      );
    }
    if (toolIndex == kImageEditorToolBeauty) {
      final templates = [
        UITextConstants.imageEditorBeautyNatural,
        UITextConstants.imageEditorBeautySoft,
        UITextConstants.imageEditorBeautyClear,
      ];
      return _buildTemplateList(
        templates,
        selectedIndex: beautyTemplateIndex,
        onTap: onBeautyTemplateChanged,
      );
    }
    if (toolIndex == kImageEditorToolText) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            Text(
              UITextConstants.imageEditorTextPlaceholder,
              style: TextStyle(color: foregroundSecondary, fontSize: AppTypography.sm),
            ),
            SizedBox(height: AppSpacing.sm),
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                _panelChip(
                  UITextConstants.imageEditorTextStyle,
                  textStyleIndex == 0,
                  onTap: () => onTextStyleChanged(0),
                ),
                SizedBox(width: AppSpacing.intraGroupSm),
                _panelChip(
                  UITextConstants.imageEditorTextColor,
                  textColorIndex == 0,
                  onTap: () => onTextColorChanged(0),
                ),
              ],
            ),
          ],
        ),
      );
    }
    if (toolIndex == kImageEditorToolMosaic) {
      final types = [
        UITextConstants.imageEditorMosaicPixel,
        UITextConstants.imageEditorMosaicBlur,
        UITextConstants.imageEditorMosaicBrush,
      ];
      final listHeight = AppSpacing.bottomNavHeight + AppSpacing.sm * 2;
      return Column(
        children: [
          SizedBox(
            height: listHeight,
            child: _buildTemplateList(
              types,
              selectedIndex: mosaicTypeIndex,
              onTap: onMosaicTypeChanged,
              itemHeight: AppSpacing.buttonHeight,
            ),
          ),
          SizedBox(height: AppSpacing.sm),
          Text(
            UITextConstants.imageEditorMosaicSize,
            style: TextStyle(color: foregroundSecondary, fontSize: AppTypography.sm),
          ),
          Slider(
            value: mosaicBrushSize,
            onChanged: onMosaicBrushSizeChanged,
            activeColor: AppColors.primaryColor,
          ),
        ],
      );
    }
    if (toolIndex == kImageEditorToolFrame) {
      final templates = [
        UITextConstants.imageEditorFrameSimple,
        UITextConstants.imageEditorFrameFilm,
        UITextConstants.imageEditorFrameWhite,
      ];
      return _buildTemplateList(
        templates,
        selectedIndex: frameTemplateIndex,
        onTap: onFrameTemplateChanged,
      );
    }
    return const SizedBox.shrink();
  }

  Widget _buildTemplateList(
    List<String> labels, {
    required int selectedIndex,
    required ValueChanged<int> onTap,
    double? itemHeight,
  }) {
    final size = itemHeight ?? AppSpacing.bottomNavHeight;
    return ListView.builder(
      scrollDirection: Axis.horizontal,
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.sm, vertical: AppSpacing.xs),
      itemCount: labels.length,
      itemBuilder: (context, i) {
        final selected = selectedIndex == i;
        return Padding(
          padding: EdgeInsets.only(right: AppSpacing.sm),
          child: GestureDetector(
            onTap: () => onTap(i),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: size,
                  height: size,
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                    border: Border.all(
                      color: selected
                          ? AppColors.primaryColor
                          : foregroundSecondary.withValues(alpha: 0.3),
                      width: selected ? AppSpacing.xs / 2 : AppSpacing.xs / 4,
                    ),
                  ),
                ),
                SizedBox(height: AppSpacing.xs),
                Text(
                  labels[i],
                  style: TextStyle(
                    fontSize: AppTypography.xs,
                    color: selected ? AppColors.primaryColor : foregroundSecondary,
                  ),
                ),
              ],
            ),
          ),
        );
      },
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
            IconButton(
              icon: Icon(
                Icons.close,
                color: AppColors.white,
                size: AppSpacing.iconLarge,
                weight: 700,
              ),
              onPressed: onCancelPanel,
              tooltip: UITextConstants.cancel,
              style: IconButton.styleFrom(
                minimumSize: Size(
                  AppSpacing.iconButtonMinSizeMd,
                  AppSpacing.iconButtonMinSizeMd,
                ),
                iconSize: AppSpacing.iconLarge,
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
                          child: TextButton.icon(
                            key: const ValueKey('crop-reset'),
                            onPressed: onCropReset,
                            icon: Icon(
                              Icons.refresh,
                              size: AppSpacing.iconMedium,
                              color: foregroundColor,
                            ),
                            label: Text(
                              UITextConstants.imageEditorCropReset,
                              style: TextStyle(
                                color: foregroundColor,
                                fontSize: AppTypography.md,
                              ),
                            ),
                            style: TextButton.styleFrom(
                              padding: AppSpacing.buttonPadding(
                                context,
                                DesignSemanticConstants.md,
                              ),
                              backgroundColor:
                                  foregroundSecondary.withValues(alpha: 0.12),
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(
                                  AppSpacing.largeBorderRadius,
                                ),
                              ),
                            ),
                          ),
                        )
                      : const SizedBox.shrink(),
                ),
              ),
            ),
            IconButton(
              icon: Icon(
                Icons.check,
                color: AppColors.white,
                size: AppSpacing.iconLarge,
                weight: 700,
              ),
              onPressed: onConfirmPanel,
              tooltip: UITextConstants.confirm,
              style: IconButton.styleFrom(
                minimumSize: Size(
                  AppSpacing.iconButtonMinSizeMd,
                  AppSpacing.iconButtonMinSizeMd,
                ),
                iconSize: AppSpacing.iconLarge,
              ),
            ),
          ],
        ),
      );
    }
    final isFilter = toolIndex == kImageEditorToolFilter;
    final isBeauty = toolIndex == kImageEditorToolBeauty;
    final isRotate = toolIndex == kImageEditorToolRotate;
    final showSlider = isFilter || isBeauty;
    return Padding(
      padding: EdgeInsets.only(
        left: AppSpacing.containerMd,
        right: AppSpacing.containerMd,
        top: AppSpacing.sm,
        bottom: AppSpacing.sm + bottomInset,
      ),
      child: Row(
        children: [
          IconButton(
            icon: Icon(
              Icons.close,
              color: AppColors.white,
              size: AppSpacing.iconLarge,
              weight: 700,
            ),
            onPressed: onCancelPanel,
            tooltip: UITextConstants.cancel,
            style: IconButton.styleFrom(
              minimumSize: Size(
                AppSpacing.iconButtonMinSizeMd,
                AppSpacing.iconButtonMinSizeMd,
              ),
              iconSize: AppSpacing.iconLarge,
            ),
          ),
          if (showSlider)
            Expanded(
              child: SliderTheme(
                data: SliderThemeData(
                  activeTrackColor: AppColors.primaryColor,
                  thumbColor: AppColors.primaryColor,
                ),
                child: Slider(
                  value: isFilter ? filterIntensity : beautyIntensity,
                  onChanged: onFilterOrBeautyIntensityChanged,
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
                          child: TextButton.icon(
                            key: const ValueKey('rotate-reset'),
                            onPressed: onRotateReset,
                            icon: Icon(
                              Icons.refresh,
                              size: AppSpacing.iconMedium,
                              color: AppColors.white,
                            ),
                            label: Text(
                              UITextConstants.imageEditorCropReset,
                              style: TextStyle(
                                color: AppColors.white,
                                fontSize: AppTypography.md,
                              ),
                            ),
                            style: TextButton.styleFrom(
                              padding: AppSpacing.buttonPadding(
                                context,
                                DesignSemanticConstants.md,
                              ),
                              backgroundColor:
                                  AppColors.white.withValues(alpha: 0.12),
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(
                                  AppSpacing.largeBorderRadius,
                                ),
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
          IconButton(
            icon: Icon(
              Icons.check,
              color: AppColors.white,
              size: AppSpacing.iconLarge,
              weight: 700,
            ),
            onPressed: onConfirmPanel,
            tooltip: UITextConstants.confirm,
            style: IconButton.styleFrom(
              minimumSize: Size(
                AppSpacing.iconButtonMinSizeMd,
                AppSpacing.iconButtonMinSizeMd,
              ),
              iconSize: AppSpacing.iconLarge,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildRotateActionItem({
    required IconData icon,
    required String label,
    required VoidCallback onTap,
    int rotateQuarterTurns = 0,
  }) {
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
                color: AppColors.white,
                size: AppSpacing.iconLarge,
              ),
            ),
            SizedBox(height: AppSpacing.xs),
            Text(
              label,
              style: TextStyle(
                color: AppColors.white,
                fontSize: AppTypography.sm,
              ),
            ),
          ],
        ),
      ),
    );
  }

  void onFilterOrBeautyIntensityChanged(double v) {
    if (toolIndex == kImageEditorToolFilter) {
      onFilterIntensityChanged(v);
    } else if (toolIndex == kImageEditorToolBeauty) {
      onBeautyIntensityChanged(v);
    }
  }

  Widget _buildCropRatioSelector() {
    final items = [
      _CropRatioEntry(
        label: UITextConstants.imageEditorCropOriginal,
        value: 'original',
      ),
      _CropRatioEntry(
        label: UITextConstants.imageEditorCropFree,
        value: 'free',
      ),
      _CropRatioEntry(
        label: UITextConstants.imageEditorCropRatio1x1,
        value: '1x1',
        previewRatio: 1,
      ),
      _CropRatioEntry(
        label: UITextConstants.imageEditorCropRatio2x3,
        value: '2x3',
        previewRatio: 2 / 3,
      ),
      _CropRatioEntry(
        label: UITextConstants.imageEditorCropRatio3x2,
        value: '3x2',
        previewRatio: 3 / 2,
      ),
      _CropRatioEntry(
        label: UITextConstants.imageEditorCropRatio3x4,
        value: '3x4',
        previewRatio: 3 / 4,
      ),
      _CropRatioEntry(
        label: UITextConstants.imageEditorCropRatio4x3,
        value: '4x3',
        previewRatio: 4 / 3,
      ),
      _CropRatioEntry(
        label: UITextConstants.imageEditorCropRatio9x16,
        value: '9x16',
        previewRatio: 9 / 16,
      ),
      _CropRatioEntry(
        label: UITextConstants.imageEditorCropRatio16x9,
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
          padding: EdgeInsets.symmetric(
            horizontal: sidePadding,
            vertical: gap,
          ),
          itemBuilder: (context, index) {
            final entry = items[index];
            final selected = cropRatio == entry.value;
            return SizedBox(
              width: itemWidth,
              child: _buildCropRatioItem(entry, selected),
            );
          },
          separatorBuilder: (_, __) => SizedBox(width: gap),
          itemCount: items.length,
        );
      },
    );
  }

  /// 比例选项图标边长（1:1 正方形边长），原始/自由为同尺寸图标
  static const double _cropRatioIconSize = 20.0;

  Widget _buildCropRatioItem(_CropRatioEntry entry, bool selected) {
    final borderColor = selected
        ? foregroundColor
        : foregroundSecondary.withValues(alpha: 0.5);
    final labelColor = selected
        ? foregroundColor
        : foregroundSecondary.withValues(alpha: 0.7);
    final borderWidth = selected ? AppSpacing.xs / 2 : AppSpacing.xs / 4;
    return InkWell(
      onTap: () => onCropRatioChanged(entry.value),
      borderRadius: BorderRadius.circular(AppSpacing.smallBorderRadius),
      child: SizedBox(
        width: double.infinity,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            SizedBox(
              height: _cropRatioIconSize,
              child: Center(
                child: _buildCropPreview(
                  entry,
                  _cropRatioIconSize,
                  borderColor,
                  borderWidth,
                  labelColor,
                ),
              ),
            ),
            SizedBox(height: AppSpacing.xs),
            Text(
              entry.label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: AppTypography.sm,
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
    final minSide = math.max(AppSpacing.xs, AppSpacing.xs / 2);
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

  Widget _panelChip(
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
                  color: selected ? AppColors.primaryColor : foregroundSecondary,
                  fontSize: AppTypography.sm,
                  fontWeight: selected ? FontWeight.w600 : FontWeight.normal,
                ),
              ),
              if (selected)
                Container(
                  margin: EdgeInsets.only(top: AppSpacing.xs / 2),
                  height: AppSpacing.xs / 2,
                  width: AppSpacing.iconSmall,
                  color: AppColors.primaryColor,
                ),
            ],
          ),
        ),
      ),
    );
  }
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
