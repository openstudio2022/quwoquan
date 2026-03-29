import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_models.dart';
import 'package:quwoquan_app/components/media/image/editor/icons/image_editor_semantic_icon.dart';
import 'package:quwoquan_app/components/media/image/editor/panels/hsl/image_editor_hsl_models.dart';
import 'package:quwoquan_app/components/media/image/editor/tool_list/image_editor_pro_tool_entries.dart';
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
    required this.proPlaceholderTitle,
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
    required this.filterCategories,
    required this.filterCategoryAnchors,
    required this.filterPresets,
    required this.filterTemplatePreviewBytes,
    required this.filterTemplatePreviewLoadingIndices,
    required this.filterTemplateScrollController,
    required this.onFilterVisibleRangeChanged,
    required this.onFilterRemove,
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
    required this.bwWhiteLevel,
    required this.bwBlackLevel,
    required this.onBwWhiteLevelChanged,
    required this.onBwBlackLevelChanged,
    required this.proBaseSelectedIndex,
    required this.proBaseValues,
    required this.onProBaseSelectedIndexChanged,
    required this.onProBaseValueChanged,
    required this.hslSelectedChannel,
    required this.hslValues,
    required this.hslPickerActive,
    required this.onSelectHslChannel,
    required this.onHslValueChanged,
    required this.onToggleHslPicker,
    required this.localValues,
    required this.hasSelectedLocalAnchor,
    required this.localShowAllAnchors,
    required this.localAddMode,
    required this.onToggleLocalAddMode,
    required this.onToggleLocalShowAll,
    required this.localRangeVisible,
    required this.onToggleLocalRangeVisible,
    required this.onCopyLocalAnchor,
    required this.onDeleteLocalAnchor,
  });

  final Color backgroundColor;
  final Color foregroundColor;
  final Color foregroundSecondary;
  final double bottomInset;
  final int toolIndex;
  final int? selectedProToolIndex;
  final int selectedProCategory;
  final String? proPlaceholderTitle;
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
  final List<ImageEditorFilterCategory> filterCategories;
  final List<int> filterCategoryAnchors;
  final List<ImageEditorFilterPreset> filterPresets;
  final Map<int, Uint8List> filterTemplatePreviewBytes;
  final Set<int> filterTemplatePreviewLoadingIndices;
  final ScrollController filterTemplateScrollController;
  final void Function(int start, int end) onFilterVisibleRangeChanged;
  final VoidCallback onFilterRemove;
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
  final double bwWhiteLevel;
  final double bwBlackLevel;
  final ValueChanged<double> onBwWhiteLevelChanged;
  final ValueChanged<double> onBwBlackLevelChanged;
  final int proBaseSelectedIndex;
  final Map<String, double> proBaseValues;
  final ValueChanged<int> onProBaseSelectedIndexChanged;
  final void Function(String toolType, double value) onProBaseValueChanged;
  final String hslSelectedChannel;
  final Map<String, Map<String, double>> hslValues;
  final bool hslPickerActive;
  final ValueChanged<String> onSelectHslChannel;
  final void Function(String axis, double value) onHslValueChanged;
  final VoidCallback onToggleHslPicker;
  final Map<String, double> localValues;
  final bool hasSelectedLocalAnchor;
  final bool localShowAllAnchors;
  final bool localAddMode;
  final bool localRangeVisible;
  final VoidCallback onToggleLocalAddMode;
  final VoidCallback onToggleLocalShowAll;
  final VoidCallback onToggleLocalRangeVisible;
  final VoidCallback onCopyLocalAnchor;
  final VoidCallback onDeleteLocalAnchor;

  @override
  Widget build(BuildContext context) {
    final borderColor = AppColorsFunctional.getColor(
      true,
      ColorType.borderPrimary,
    ).withValues(alpha: 0.3);
    final panelBg = toolIndex == kImageEditorToolCrop
        ? AppColors.black
        : backgroundColor;
    return Container(
      decoration: BoxDecoration(
        color: panelBg,
        border: Border(top: BorderSide(color: borderColor)),
      ),
      child: toolIndex == kImageEditorToolPro
          ? _buildProToolsPanel(context)
          : Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                _buildPanelTopContent(),
                _buildPanelMiddleContent(),
                _buildPanelBottomBar(context),
              ],
            ),
    );
  }

  Widget _buildEntryIcon(
    ImageEditorProToolEntry entry,
    Color color, {
    required double iconSize,
  }) {
    if (entry.semanticIconKey != null) {
      return ImageEditorSemanticIcon(
        iconKey: entry.semanticIconKey!,
        size: iconSize,
        color: color,
      );
    }
    return Icon(
      entry.icon,
      color: color,
      size: iconSize,
    );
  }

  Widget _buildProToolsPanel(BuildContext context) {
    final isOverall = selectedProCategory == kImageEditorProCategoryOverall;
    final isLocal = selectedProCategory == kImageEditorProCategoryLocal;
    final isHsl = selectedProCategory == kImageEditorProCategoryHsl;
    final isBwLevels = selectedProCategory == kImageEditorProCategoryBwLevels;
    final placeholder = proPlaceholderTitle ??
        (selectedProCategory == kImageEditorProCategoryCurve
            ? UITextConstants.imageEditorProCurve
            : selectedProCategory == kImageEditorProCategoryWhiteBalance
                ? UITextConstants.imageEditorProWhiteBalance
                : UITextConstants.imageEditorProPerspective);
    if (isOverall || isLocal) {
      return Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          _buildProAdjustPanelContent(
            context,
            showLocalControls: isLocal,
          ),
          _buildProPanelExitBar(),
        ],
      );
    }
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        isHsl
            ? _buildProHslPanelContent()
            : isBwLevels
                ? _buildProBwLevelsPanelContent()
            : _buildProPlaceholderPanel(placeholder),
        _buildProPanelExitBar(),
      ],
    );
  }

  Widget _buildProBwLevelsPanelContent() {
    return Padding(
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
      child: Column(
        children: [
          SizedBox(height: AppSpacing.sm),
          _buildHslAxisRow(
            UITextConstants.imageEditorProWhiteLevel,
            bwWhiteLevel,
            gradient: <Color>[
              AppColors.white.withValues(alpha: 0.08),
              AppColors.white.withValues(alpha: 0.95),
            ],
            onChanged: onBwWhiteLevelChanged,
          ),
          SizedBox(height: AppSpacing.xs),
          _buildHslAxisRow(
            UITextConstants.imageEditorProBlackLevel,
            bwBlackLevel,
            gradient: <Color>[
              AppColors.white.withValues(alpha: 0.95),
              AppColors.white.withValues(alpha: 0.12),
            ],
            onChanged: onBwBlackLevelChanged,
          ),
          SizedBox(height: AppSpacing.xs),
        ],
      ),
    );
  }

  Widget _buildProAdjustPanelContent(
    BuildContext context, {
    required bool showLocalControls,
  }) {
    return Padding(
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (showLocalControls) _buildLocalControlButtonsRow(),
          if (showLocalControls) SizedBox(height: AppSpacing.xs / 2),
          SizedBox(
            height: AppSpacing.bottomNavHeight + AppSpacing.sm * 2,
            child: _buildProBasePanelContent(context),
          ),
        ],
      ),
    );
  }

  Widget _buildProPlaceholderPanel(String title) {
    return Center(
      child: Text(
        '$title ${UITextConstants.imageEditorPanelPlaceholder}',
        style: TextStyle(
          color: foregroundSecondary.withValues(alpha: 0.85),
          fontSize: AppTypography.md,
        ),
      ),
    );
  }

  Widget _buildLocalControlButtonsRow() {
    final items = <_LocalControlButtonItem>[
      _LocalControlButtonItem(
        icon: Icons.add_circle_outline,
        selected: localAddMode,
        label: UITextConstants.imageEditorProAnchorAdd,
        onTap: onToggleLocalAddMode,
      ),
      _LocalControlButtonItem(
        icon: localShowAllAnchors ? Icons.visibility_outlined : Icons.visibility,
        selected: !localShowAllAnchors,
        label: localShowAllAnchors
            ? UITextConstants.imageEditorProAnchorHide
            : UITextConstants.imageEditorProAnchorShow,
        onTap: onToggleLocalShowAll,
      ),
      _LocalControlButtonItem(
        icon: localRangeVisible ? Icons.radar : Icons.radar_outlined,
        selected: localRangeVisible,
        label: localRangeVisible
            ? UITextConstants.imageEditorProAnchorRangeHide
            : UITextConstants.imageEditorProAnchorRangeShow,
        onTap: onToggleLocalRangeVisible,
      ),
    ];
    return SizedBox(
      height: AppSpacing.bottomNavHeight,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceEvenly,
        children: items.asMap().entries.map((entry) {
          final index = entry.key;
          final item = entry.value;
          final color = item.selected
              ? (index == 0 ? AppColors.primaryColor : foregroundColor)
              : foregroundSecondary.withValues(alpha: 0.8);
          return CupertinoButton(
            padding: EdgeInsets.symmetric(
              horizontal: AppSpacing.sm,
              vertical: AppSpacing.xs,
            ),
            minimumSize: Size.zero,
            onPressed: item.onTap,
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  item.icon,
                  color: color,
                  size: AppSpacing.toolPanelItemIconSize,
                ),
                SizedBox(width: AppSpacing.toolPanelItemIconLabelGap),
                Text(
                  item.label,
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
          );
        }).toList(growable: false),
      ),
    );
  }

  Widget _buildProHslPanelContent() {
    final channelValues = hslValues[hslSelectedChannel] ?? const <String, double>{};
    final hue = channelValues[kHslAxisHue] ?? 0;
    final saturation = channelValues[kHslAxisSaturation] ?? 0;
    final luminance = channelValues[kHslAxisLuminance] ?? 0;
    final selectedChannel = kImageEditorHslChannels.firstWhere(
      (channel) => channel.key == hslSelectedChannel,
      orElse: () => kImageEditorHslChannels.first,
    );
    return Padding(
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
      child: Column(
        children: [
          SizedBox(height: AppSpacing.xs),
          SizedBox(
            height: AppSpacing.bottomNavHeight,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              itemCount: kImageEditorHslChannels.length,
              separatorBuilder: (context, index) =>
                  SizedBox(width: AppSpacing.intraGroupSm),
              itemBuilder: (context, index) =>
                  _buildHslChannelItem(kImageEditorHslChannels[index]),
            ),
          ),
          SizedBox(height: AppSpacing.sm),
          _buildHslAxisRow(
            UITextConstants.imageEditorProHue,
            hue,
            gradient: _buildHslAxisGradient(selectedChannel.color, kHslAxisHue),
            onChanged: (v) => onHslValueChanged(kHslAxisHue, v),
          ),
          SizedBox(height: AppSpacing.xs),
          _buildHslAxisRow(
            UITextConstants.imageEditorProSaturation,
            saturation,
            gradient:
                _buildHslAxisGradient(selectedChannel.color, kHslAxisSaturation),
            onChanged: (v) => onHslValueChanged(kHslAxisSaturation, v),
          ),
          SizedBox(height: AppSpacing.xs),
          _buildHslAxisRow(
            UITextConstants.imageEditorProLuminance,
            luminance,
            gradient:
                _buildHslAxisGradient(selectedChannel.color, kHslAxisLuminance),
            onChanged: (v) => onHslValueChanged(kHslAxisLuminance, v),
          ),
          SizedBox(height: AppSpacing.xs),
        ],
      ),
    );
  }

  Widget _buildHslChannelItem(ImageEditorHslChannel channel) {
    final selected = hslSelectedChannel == channel.key;
    return GestureDetector(
      onTap: () => onSelectHslChannel(channel.key),
      child: SizedBox(
        width: AppSpacing.bottomNavHeight - AppSpacing.xs,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: AppSpacing.iconLarge,
              height: AppSpacing.iconLarge,
              margin: EdgeInsets.only(top: AppSpacing.xs),
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: channel.color,
                border: Border.all(
                  color: selected
                      ? AppColors.white
                      : AppColors.white.withValues(alpha: 0.35),
                  width: selected ? AppSpacing.xs / 2 : AppSpacing.xs / 4,
                ),
              ),
              child: selected
                  ? Center(
                      child: Container(
                        width: AppSpacing.iconLarge / 2,
                        height: AppSpacing.iconLarge / 2,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          border: Border.all(
                            color: AppColors.black.withValues(alpha: 0.7),
                            width: AppSpacing.xs / 3,
                          ),
                        ),
                      ),
                    )
                  : null,
            ),
            SizedBox(height: AppSpacing.xs / 2),
            Text(
              channel.label,
              style: TextStyle(
                color: selected
                    ? foregroundColor
                    : foregroundSecondary.withValues(alpha: 0.75),
                fontSize: AppTypography.sm,
              ),
            ),
          ],
        ),
      ),
    );
  }

  List<Color> _buildHslAxisGradient(Color selectedColor, String axis) {
    final hsv = HSVColor.fromColor(selectedColor);
    if (axis == kHslAxisHue) {
      return <Color>[
        hsv.withHue((hsv.hue - 60 + 360) % 360).withSaturation(1).withValue(1).toColor(),
        hsv.withSaturation(1).withValue(1).toColor(),
        hsv.withHue((hsv.hue + 60) % 360).withSaturation(1).withValue(1).toColor(),
      ];
    }
    if (axis == kHslAxisSaturation) {
      return <Color>[
        HSLColor.fromColor(selectedColor).withSaturation(0).toColor(),
        HSLColor.fromColor(selectedColor).withSaturation(0.5).toColor(),
        HSLColor.fromColor(selectedColor).withSaturation(1).toColor(),
      ];
    }
    return <Color>[
      AppColors.black,
      HSLColor.fromColor(selectedColor).withLightness(0.5).toColor(),
      AppColors.white,
    ];
  }

  Widget _buildHslAxisRow(
    String label,
    double value, {
    required List<Color> gradient,
    required ValueChanged<double> onChanged,
  }) {
    return Row(
      children: [
        SizedBox(
          width: AppSpacing.bottomNavHeight,
          child: Text(
            label,
            style: TextStyle(
              color: foregroundColor,
              fontSize: AppTypography.sm,
            ),
          ),
        ),
        Expanded(
          child: _ProAdjustmentLine(
            value: value,
            min: -100,
            max: 100,
            trackHeight: AppSpacing.xs,
            trackGradient: LinearGradient(colors: gradient),
            onChanged: onChanged,
          ),
        ),
        SizedBox(width: AppSpacing.sm),
        SizedBox(
          width: AppSpacing.bottomNavHeight,
          child: Text(
            value.round().toString(),
            textAlign: TextAlign.right,
            style: TextStyle(
              color: foregroundColor,
              fontSize: AppTypography.sm,
              fontWeight: FontWeight.w500,
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildProBasePanelContent(BuildContext context) {
    final gap = AppSpacing.intraGroupSm;
    final itemWidth = AppSpacing.buttonHeight * 1.4;
    final itemIconSize = AppTypography.responsive(
      context,
      compact: AppSpacing.iconSmall,
      regular: AppSpacing.toolPanelItemIconSize,
      expanded: AppSpacing.toolPanelItemIconSize,
    );
    final itemLabelFontSize = AppTypography.responsive(
      context,
      compact: AppTypography.sm,
      regular: AppTypography.toolPanelItemLabel,
      expanded: AppTypography.toolPanelItemLabel,
    );
    final itemLabelLineHeight = AppTypography.responsive(
      context,
      compact: AppTypography.sm,
      regular: AppSpacing.toolPanelItemLabelLineHeight,
      expanded: AppSpacing.toolPanelItemLabelLineHeight,
    );
    final itemIconLabelGap = AppTypography.responsive(
      context,
      compact: AppSpacing.intraGroupXs,
      regular: AppSpacing.toolPanelItemIconLabelGap,
      expanded: AppSpacing.toolPanelItemIconLabelGap,
    );
    return SizedBox(
      height: AppSpacing.bottomNavHeight + AppSpacing.sm * 2,
      child: ListView.separated(
        controller: proToolScrollController,
        scrollDirection: Axis.horizontal,
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
        itemCount: kImageEditorProBaseEntries.length,
        separatorBuilder: (context, index) => SizedBox(width: gap),
        itemBuilder: (context, index) {
          final entry = kImageEditorProBaseEntries[index];
          final selected = proBaseSelectedIndex == index;
          final value = (proBaseValues[entry.type] ?? 0).round();
          return SizedBox(
            width: itemWidth,
            child: GestureDetector(
              onTap: () => onProBaseSelectedIndexChanged(index),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                mainAxisSize: MainAxisSize.min,
                children: [
                  _buildEntryIcon(
                    entry,
                    selected
                        ? foregroundColor
                        : foregroundSecondary.withValues(alpha: 0.75),
                    iconSize: itemIconSize,
                  ),
                  SizedBox(height: itemIconLabelGap),
                  Text(
                    entry.label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: selected
                          ? foregroundColor
                          : foregroundSecondary.withValues(alpha: 0.75),
                      fontSize: itemLabelFontSize,
                      height: itemLabelLineHeight / itemLabelFontSize,
                      fontWeight: selected ? FontWeight.w600 : FontWeight.normal,
                    ),
                  ),
                  SizedBox(height: itemIconLabelGap),
                  Text(
                    value.toString(),
                    style: TextStyle(
                      color: selected
                          ? foregroundColor
                          : foregroundSecondary.withValues(alpha: 0.75),
                      fontSize: itemLabelFontSize,
                      height: itemLabelLineHeight / itemLabelFontSize,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _buildProPanelExitBar() {
    final isAdjustPanel = selectedProCategory == kImageEditorProCategoryOverall ||
        selectedProCategory == kImageEditorProCategoryLocal;
    final centerTitle = selectedProCategory == kImageEditorProCategoryHsl
        ? UITextConstants.imageEditorProTabHsl
        : selectedProCategory == kImageEditorProCategoryBwLevels
            ? UITextConstants.imageEditorProTabBwLevels
        : selectedProCategory == kImageEditorProCategoryLocal
            ? UITextConstants.imageEditorProTabLocal
        : selectedProCategory == kImageEditorProCategoryCurve
            ? UITextConstants.imageEditorProCurve
            : selectedProCategory == kImageEditorProCategoryWhiteBalance
                ? UITextConstants.imageEditorProWhiteBalance
                : selectedProCategory == kImageEditorProCategoryPerspective
                    ? (proPlaceholderTitle ?? UITextConstants.imageEditorProPerspective)
                    : UITextConstants.imageEditorProAdjustImage;
    final safeIndex = proBaseSelectedIndex.clamp(0, kImageEditorProBaseEntries.length - 1);
    final selectedEntry = kImageEditorProBaseEntries[safeIndex];
    final currentValue = selectedProCategory == kImageEditorProCategoryLocal &&
            hasSelectedLocalAnchor
        ? (localValues[selectedEntry.type] ?? 0)
        : (proBaseValues[selectedEntry.type] ?? 0);
    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerMd,
        vertical: AppSpacing.sm,
      ),
      child: Row(
        children: [
          CupertinoButton(
            padding: EdgeInsets.zero,
            minimumSize: Size.square(AppSpacing.iconButtonMinSizeMd),
            onPressed: onExitProPanel,
            child: Icon(
              CupertinoIcons.xmark,
              color: AppColors.white,
              size: AppSpacing.iconLarge,
            ),
          ),
          if (isAdjustPanel)
            Expanded(
              child: Padding(
                padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
                child: _ProAdjustmentLine(
                  value: currentValue,
                  min: -100,
                  max: 100,
                  onChanged: (v) => onProBaseValueChanged(selectedEntry.type, v),
                ),
              ),
            )
          else
            Expanded(
              child: Center(
                child: Text(
                  centerTitle,
                  style: TextStyle(
                    color: AppColors.white.withValues(alpha: 0.92),
                    fontSize: AppTypography.md,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ),
          CupertinoButton(
            padding: EdgeInsets.zero,
            minimumSize: Size.square(AppSpacing.iconButtonMinSizeMd),
            onPressed: onConfirmProPanel,
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

  Widget _buildPanelTopContent() {
    if (toolIndex == kImageEditorToolCrop) {
      return const SizedBox.shrink();
    }
    if (toolIndex == kImageEditorToolFilter) {
      return SizedBox(
        height: AppSpacing.subTabNavigationHeight,
        child: ListView(
          scrollDirection: Axis.horizontal,
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.containerSm,
            vertical: AppSpacing.xs,
          ),
          children: [
            _buildFilterRemoveChip(),
            ...List.generate(filterCategories.length, (i) {
              return Padding(
                padding: EdgeInsets.only(left: AppSpacing.filterCategoryChipGap),
                child: _buildFilterCategoryChip(i),
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
      final itemWidth = AppSpacing.filterTemplateItemWidth;
      final itemExtent = AppSpacing.filterTemplateItemExtent;
      final previewSide = AppSpacing.filterTemplatePreviewSize;
      final labelBarHeight = AppSpacing.filterTemplateLabelBarHeight;
      final listVerticalPadding = AppSpacing.xs;
      final maxCardBorderInset = AppSpacing.toolPanelItemBorderWidthSelected * 2;
      final filterCardHeight = previewSide + labelBarHeight + maxCardBorderInset;
      final filterRowHeight =
          filterCardHeight + listVerticalPadding * 2 + AppSpacing.intraGroupXs;
      return LayoutBuilder(
        builder: (context, constraints) {
          final viewport = constraints.maxWidth;
          WidgetsBinding.instance.addPostFrameCallback((_) {
            _notifyFilterVisibleRange(viewport, itemExtent);
          });
          return SizedBox(
            height: filterRowHeight,
            child: NotificationListener<ScrollUpdateNotification>(
              onNotification: (_) {
                _notifyFilterVisibleRange(viewport, itemExtent);
                _syncFilterCategoryWithScroll(itemExtent);
                return false;
              },
              child: ListView.builder(
                controller: filterTemplateScrollController,
                scrollDirection: Axis.horizontal,
                padding: EdgeInsets.symmetric(
                    horizontal: AppSpacing.containerSm,
                    vertical: listVerticalPadding),
                itemCount: filterPresets.length,
                itemBuilder: (context, i) {
                  final preset = filterPresets[i];
                  final selected = filterTemplateIndex == i;
                  final isCategoryStart = i > 0 && filterCategoryAnchors.contains(i);
                  final borderWidth = selected
                      ? AppSpacing.toolPanelItemBorderWidthSelected
                      : AppSpacing.toolPanelItemBorderWidthUnselected;
                  final preview = filterTemplatePreviewBytes[i];
                  final loading =
                      filterTemplatePreviewLoadingIndices.contains(i);
                  final labelBarColor = _resolveFilterLabelBarColor(
                    preset,
                    selected: selected,
                  );
                  return Padding(
                    padding: EdgeInsets.only(
                      left: isCategoryStart
                          ? AppSpacing.filterTemplateCategoryGap
                          : 0,
                      right: AppSpacing.filterTemplateItemGap,
                    ),
                    child: SizedBox(
                      width: itemWidth,
                      child: GestureDetector(
                        onTap: () => onFilterTemplateChanged(i),
                        child: Container(
                          width: previewSide,
                          height: filterCardHeight,
                          decoration: BoxDecoration(
                            borderRadius:
                                BorderRadius.circular(AppSpacing.smallBorderRadius),
                            border: Border.all(
                              color: selected
                                  ? foregroundColor
                                  : foregroundSecondary.withValues(alpha: 0.30),
                              width: borderWidth,
                            ),
                            color: AppColors.white.withValues(alpha: 0.04),
                          ),
                          child: ClipRRect(
                            borderRadius:
                                BorderRadius.circular(AppSpacing.smallBorderRadius),
                            child: Column(
                              mainAxisSize: MainAxisSize.max,
                              children: [
                                Expanded(
                                  child: _buildFilterPreviewContent(
                                    preview: preview,
                                    loading: loading,
                                  ),
                                ),
                                SizedBox(
                                  width: double.infinity,
                                  height: labelBarHeight,
                                  child: Container(
                                    alignment: Alignment.center,
                                    color: labelBarColor,
                                    padding: EdgeInsets.symmetric(
                                      horizontal: AppSpacing.intraGroupXs,
                                    ),
                                    child: Text(
                                      preset.name,
                                      maxLines: 1,
                                      overflow: TextOverflow.ellipsis,
                                      textAlign: TextAlign.center,
                                      style: TextStyle(
                                        fontSize: AppTypography.xs,
                                        color: selected
                                            ? AppColors.white.withValues(alpha: 0.96)
                                            : AppColors.white.withValues(alpha: 0.72),
                                        fontWeight: selected
                                            ? FontWeight.w600
                                            : FontWeight.w500,
                                      ),
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                    ),
                  );
                },
              ),
            ),
          );
        },
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
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.intraGroupSm,
      ),
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
                    fontSize: AppTypography.sm,
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

  Widget _buildFilterRemoveChip() {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.square(AppSpacing.subTabNavigationHeight),
      onPressed: onFilterRemove,
      child: Icon(
        CupertinoIcons.clear_circled,
        color: foregroundSecondary.withValues(alpha: 0.82),
        size: AppSpacing.iconMedium,
      ),
    );
  }

  Widget _buildFilterCategoryChip(int categoryIndex) {
    final selected = filterCategoryIndex == categoryIndex;
    final chip = _panelChip(
      filterCategories[categoryIndex].label,
      selected,
      onTap: () => _onTapFilterCategory(categoryIndex),
      fontSize: AppTypography.md,
    );
    if (!selected) return chip;
    return Builder(
      builder: (context) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (!context.mounted) return;
          Scrollable.ensureVisible(
            context,
            duration: const Duration(milliseconds: 220),
            curve: Curves.easeOut,
            alignment: 0.5,
          );
        });
        return chip;
      },
    );
  }

  void _onTapFilterCategory(int categoryIndex) {
    onFilterCategoryChanged(categoryIndex);
    if (!filterTemplateScrollController.hasClients ||
        categoryIndex < 0 ||
        categoryIndex >= filterCategoryAnchors.length) {
      return;
    }
    final itemExtent = AppSpacing.filterTemplateItemExtent;
    final targetIndex = filterCategoryAnchors[categoryIndex].clamp(
      0,
      math.max(0, filterPresets.length - 1),
    ).toInt();
    final target = _offsetForTemplateIndex(targetIndex, itemExtent);
    filterTemplateScrollController.animateTo(
      target.clamp(0.0, filterTemplateScrollController.position.maxScrollExtent),
      duration: const Duration(milliseconds: 220),
      curve: Curves.easeOut,
    );
  }

  void _notifyFilterVisibleRange(double viewportWidth, double itemWidth) {
    if (itemWidth <= 0 || filterPresets.isEmpty) return;
    final offset = filterTemplateScrollController.hasClients
        ? filterTemplateScrollController.offset
        : 0.0;
    final start = _indexForOffset(offset, itemWidth);
    final visibleCount = (viewportWidth / itemWidth).ceil() + 1;
    final end = (start + visibleCount).clamp(0, filterPresets.length - 1);
    onFilterVisibleRangeChanged(start, end);
  }

  void _syncFilterCategoryWithScroll(double itemWidth) {
    if (!filterTemplateScrollController.hasClients ||
        filterCategoryAnchors.isEmpty ||
        filterPresets.isEmpty ||
        itemWidth <= 0) {
      return;
    }
    final index = _indexForOffset(filterTemplateScrollController.offset, itemWidth);
    var category = 0;
    for (var i = 0; i < filterCategoryAnchors.length; i++) {
      final anchor = filterCategoryAnchors[i];
      if (index >= anchor) {
        category = i;
      } else {
        break;
      }
    }
    if (category != filterCategoryIndex) {
      onFilterCategoryChanged(category);
    }
  }

  double _offsetForTemplateIndex(int index, double itemWidth) {
    final safeIndex = index.clamp(0, math.max(0, filterPresets.length - 1));
    var extra = 0.0;
    for (final anchor in filterCategoryAnchors) {
      if (anchor > 0 && anchor < safeIndex + 1) {
        extra += AppSpacing.filterTemplateCategoryGap;
      }
    }
    return safeIndex * itemWidth + extra;
  }

  int _indexForOffset(double offset, double itemWidth) {
    if (filterPresets.isEmpty) return 0;
    var best = 0;
    for (var i = 0; i < filterPresets.length; i++) {
      final start = _offsetForTemplateIndex(i, itemWidth);
      final end = start + itemWidth;
      if (offset < end) {
        best = i;
        break;
      }
      best = i;
    }
    return best.clamp(0, filterPresets.length - 1);
  }

  Widget _buildFilterPreviewContent({
    required Uint8List? preview,
    required bool loading,
  }) {
    if (preview != null) {
      return Image.memory(
        preview,
        fit: BoxFit.cover,
        filterQuality: FilterQuality.low,
      );
    }
    if (loading) {
      return Center(
        child: SizedBox(
          width: AppSpacing.iconSmall,
          height: AppSpacing.iconSmall,
          child: CupertinoActivityIndicator(),
        ),
      );
    }
    return Center(
      child: Icon(
        Icons.image_outlined,
        size: AppSpacing.iconMedium,
        color: foregroundSecondary.withValues(alpha: 0.6),
      ),
    );
  }

  Color _resolveFilterLabelBarColor(
    ImageEditorFilterPreset preset, {
    required bool selected,
  }) {
    final params = preset.params;
    final name = preset.name;
    final alpha = selected ? 0.88 : 0.72;
    final temperature = (params['temperature'] ?? 0).clamp(-100, 100);
    final tint = (params['tint'] ?? 0).clamp(-100, 100);
    final saturationValue = (params['saturation'] ?? 0).clamp(-100, 100);
    final brightness = (params['brightness'] ?? 0).clamp(-100, 100);
    final fade = (params['fade'] ?? 0).clamp(-100, 100);
    final contrast = (params['contrast'] ?? 0).clamp(-100, 100);
    final lightSense = (params['lightSense'] ?? 0).clamp(-100, 100);
    final highlight = (params['highlight'] ?? 0).clamp(-100, 100);
    final shadow = (params['shadow'] ?? 0).clamp(-100, 100);

    final calibrated = _filterPresetHslOverrides[preset.id];
    if (calibrated != null) {
      return HSLColor.fromAHSL(
        alpha,
        calibrated[0],
        calibrated[1],
        calibrated[2],
      ).toColor();
    }

    if (preset.categoryId == 'bw_art') {
      final bwLightness = (0.40 +
              contrast / 320 +
              brightness / 320 +
              highlight / 420 +
              shadow / 520)
          .clamp(0.28, 0.64);
      return HSLColor.fromAHSL(alpha, 0, 0, bwLightness).toColor();
    }

    final profile = _filterCategoryHslProfiles[preset.categoryId] ??
        const <double>[214, 0.54, 0.46];
    var hue = profile[0];
    var saturation = profile[1];
    var lightness = profile[2];

    // 参数驱动：温度偏暖 -> 偏橙；偏冷 -> 偏蓝（摄影常见色温方向）
    if (temperature > 0) {
      hue = _blendHue(hue, 34, (temperature / 100) * 0.55);
    } else if (temperature < 0) {
      hue = _blendHue(hue, 210, (-temperature / 100) * 0.55);
    }
    // 色调偏移：正向洋红，负向青绿
    if (tint > 0) {
      hue = _blendHue(hue, 326, (tint / 100) * 0.42);
    } else if (tint < 0) {
      hue = _blendHue(hue, 170, (-tint / 100) * 0.42);
    }

    // 名称语义覆盖：保证视觉与命名一致（奶油/冷霜/粉雾等）
    if (_containsAny(name, const ['奶油', '暖', '琥珀', '金', '日落'])) {
      hue = _blendHue(hue, 34, 0.70);
      saturation += 0.03;
      lightness += 0.04;
    } else if (_containsAny(name, const ['冷', '蓝', '海', '雪', '霜', '冰'])) {
      hue = _blendHue(hue, 208, 0.68);
      saturation += 0.02;
      lightness += 0.01;
    } else if (_containsAny(name, const ['粉', '樱', '柔', '梦'])) {
      hue = _blendHue(hue, 332, 0.62);
      saturation += 0.03;
      lightness += 0.03;
    } else if (_containsAny(name, const ['绿', '薄荷', '新芽'])) {
      hue = _blendHue(hue, 145, 0.62);
      saturation += 0.02;
    }

    // 摄影审校模式：禁用扰动，保证色块值稳定可复核

    saturation = (saturation +
            saturationValue / 220 +
            (contrast > 0 ? contrast / 520 : 0) -
            (fade > 0 ? fade / 620 : 0))
        .clamp(0.34, 0.76);
    lightness = (lightness +
            brightness / 240 +
            lightSense / 560 +
            highlight / 520 +
            shadow / 760 +
            fade / 280 -
            (contrast > 0 ? contrast / 560 : 0))
        .clamp(0.30, 0.66);
    return HSLColor.fromAHSL(alpha, hue, saturation, lightness).toColor();
  }

  static const Map<String, List<double>> _filterCategoryHslProfiles =
      <String, List<double>>{
    'texture': <double>[170, 0.48, 0.43],
    'portrait': <double>[336, 0.45, 0.53],
    'fresh_natural': <double>[138, 0.46, 0.50],
    'landscape_travel': <double>[196, 0.54, 0.48],
    'food': <double>[28, 0.60, 0.48],
    'film_retro': <double>[30, 0.42, 0.42],
    'movie_dream': <double>[290, 0.50, 0.50],
    'bw_art': <double>[0, 0.00, 0.44],
    'seasons': <double>[36, 0.58, 0.52],
  };

  // 摄影师视角精调：关键滤镜使用精准 HSL 标定，优先级最高
  static const Map<String, List<double>> _filterPresetHslOverrides =
      <String, List<double>>{
    // texture
    'texture_clear': <double>[178, 0.40, 0.44],
    'texture_soft': <double>[26, 0.22, 0.60],
    'texture_depth': <double>[176, 0.34, 0.38],
    // beauty
    'beauty_softskin': <double>[20, 0.38, 0.62],
    'beauty_clean': <double>[28, 0.32, 0.60],
    'beauty_milky': <double>[38, 0.42, 0.64],
    // portrait
    'portrait_softlight': <double>[344, 0.42, 0.60],
    'portrait_cool': <double>[210, 0.42, 0.54],
    'portrait_movie': <double>[200, 0.34, 0.42],
    // blue
    'blue_light': <double>[202, 0.66, 0.54],
    'blue_deep': <double>[210, 0.60, 0.36],
    'blue_ice': <double>[196, 0.52, 0.56],
    // food
    'food_fresh': <double>[24, 0.70, 0.52],
    'food_warm': <double>[30, 0.64, 0.50],
    'food_dessert': <double>[22, 0.68, 0.56],
    // retro
    'retro_oldtime': <double>[30, 0.36, 0.42],
    'retro_hk': <double>[346, 0.42, 0.42],
    'retro_brown': <double>[26, 0.46, 0.38],
    // film
    'film_n': <double>[30, 0.34, 0.42],
    'film_warm': <double>[34, 0.42, 0.45],
    'film_green': <double>[146, 0.34, 0.40],
    // natural
    'natural_origin': <double>[122, 0.32, 0.44],
    'natural_air': <double>[126, 0.28, 0.52],
    'natural_balance': <double>[124, 0.30, 0.46],
    // landscape
    'landscape_mountain': <double>[136, 0.48, 0.40],
    'landscape_coast': <double>[192, 0.54, 0.44],
    'landscape_sunset': <double>[26, 0.66, 0.50],
    // dream
    'dream_haze': <double>[318, 0.34, 0.62],
    'dream_pink': <double>[334, 0.58, 0.62],
    'dream_focus': <double>[328, 0.42, 0.64],
    // oil
    'oil_canvas': <double>[34, 0.50, 0.44],
    'oil_thick': <double>[30, 0.56, 0.40],
    'oil_vintage': <double>[34, 0.42, 0.48],
    // movie
    'movie_teal_orange': <double>[188, 0.56, 0.40],
    'movie_lowsat': <double>[196, 0.22, 0.40],
    'movie_dark': <double>[224, 0.34, 0.32],
    // fresh
    'fresh_mint': <double>[146, 0.56, 0.52],
    'fresh_morning': <double>[148, 0.42, 0.54],
    'fresh_white': <double>[150, 0.30, 0.60],
    // bw
    'bw_classic': <double>[0, 0.00, 0.42],
    'bw_silver': <double>[0, 0.00, 0.48],
    'bw_matte': <double>[0, 0.00, 0.40],
    // seasons
    'seasons_spring_blossom': <double>[334, 0.58, 0.62],
    'seasons_spring_green': <double>[94, 0.56, 0.52],
    'seasons_spring_sunny': <double>[46, 0.68, 0.56],
    'seasons_summer_breeze': <double>[202, 0.62, 0.50],
    'seasons_summer_soda': <double>[198, 0.62, 0.56],
    'seasons_summer_sun': <double>[190, 0.56, 0.50],
    'seasons_autumn_gold': <double>[34, 0.64, 0.52],
    'seasons_autumn_amber': <double>[24, 0.58, 0.46],
    'seasons_autumn_mist': <double>[30, 0.40, 0.50],
    'seasons_winter_frost': <double>[210, 0.52, 0.44],
    'seasons_winter_snow': <double>[202, 0.34, 0.60],
    'seasons_winter_morning': <double>[208, 0.44, 0.46],
  };

  bool _containsAny(String text, List<String> patterns) {
    for (final pattern in patterns) {
      if (text.contains(pattern)) return true;
    }
    return false;
  }

  double _normalizeHue(double hue) {
    var value = hue % 360;
    if (value < 0) value += 360;
    return value;
  }

  double _blendHue(double from, double to, double amount) {
    final a = _normalizeHue(from);
    final b = _normalizeHue(to);
    final t = amount.clamp(0.0, 1.0);
    var delta = b - a;
    if (delta.abs() > 180) {
      delta -= 360 * delta.sign;
    }
    return _normalizeHue(a + delta * t);
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
                                    UITextConstants.imageEditorCropReset,
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
                                    UITextConstants.imageEditorCropReset,
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

  Widget _panelChip(
    String label,
    bool selected, {
    VoidCallback? onTap,
    double? fontSize,
  }) {
    return CupertinoButton(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.intraGroupSm,
      ),
      minimumSize: Size.zero,
      onPressed: onTap ?? () {},
      child: Column(
        mainAxisSize: MainAxisSize.min,
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Text(
            label,
            style: TextStyle(
              color: selected
                  ? foregroundColor
                  : foregroundSecondary.withValues(alpha: 0.75),
              fontSize: fontSize ?? AppTypography.toolPanelCategoryLabel,
              fontWeight: selected ? FontWeight.w600 : FontWeight.normal,
            ),
          ),
          Container(
            margin: EdgeInsets.only(top: AppSpacing.xs / 2),
            height: AppSpacing.xs / 2,
            width: AppSpacing.iconSmall,
            decoration: BoxDecoration(
              color: selected ? foregroundColor : AppColors.transparent,
              borderRadius: BorderRadius.circular(AppSpacing.xs / 4),
            ),
          ),
        ],
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
        : ((widget.value - widget.min) / (widget.max - widget.min))
            .clamp(0.0, 1.0);
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
                color: AppColors.white.withValues(alpha: _dragging ? 0.10 : 0.06),
                borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
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
                    left: (centerX - AppSpacing.xs / 4)
                        .clamp(0.0, math.max(0.0, width - AppSpacing.xs / 2)),
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
                    left: (knobX - AppSpacing.xs)
                        .clamp(0.0, math.max(0.0, width - AppSpacing.xs * 2)),
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
