import 'dart:math' as math;
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/content/media/filter_catalog_release/adapters/image_editor_filter_models.dart';
import 'package:quwoquan_app/content/media/filter_catalog_release/presentation/image_editor_semantic_icon.dart';
import 'package:quwoquan_app/content/media/filter_catalog_release/presentation/image_editor_curve_models.dart';
import 'package:quwoquan_app/content/media/filter_catalog_release/presentation/image_editor_curve_panel.dart';
import 'package:quwoquan_app/content/media/filter_catalog_release/presentation/image_editor_hsl_models.dart';
import 'package:quwoquan_app/content/media/filter_catalog_release/presentation/image_editor_mosaic_models.dart';
import 'package:quwoquan_app/content/media/filter_catalog_release/presentation/image_editor_text_models.dart';
import 'package:quwoquan_app/content/media/filter_catalog_release/presentation/image_editor_pro_tool_entries.dart';
import 'package:quwoquan_app/content/media/filter_catalog_release/presentation/image_editor_tool_constants.dart';
import 'package:quwoquan_app/core/constants/design_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';

part 'image_editor_operation_panel_controls.dart';
part 'image_editor_operation_panel_filter.dart';
part 'image_editor_operation_panel_pro.dart';

class ImageEditorOperationPanel extends StatelessWidget {
  const ImageEditorOperationPanel({
    super.key,
    required this.backgroundColor,
    required this.foregroundColor,
    required this.foregroundSecondary,
    required this.bottomInset,
    required this.toolIndex,
    required this.selectedProCategory,
    required this.proToolScrollController,
    required this.onSelectProCategory,
    required this.onExitProPanel,
    required this.onConfirmProPanel,
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
    required this.filterCatalogLoading,
    required this.filterCatalogLoadFailed,
    required this.onFilterCatalogRetry,
    required this.mosaicType,
    required this.mosaicBrushSize,
    required this.onMosaicTypeChanged,
    required this.onMosaicBrushSizeChanged,
    required this.mosaicHasStrokes,
    required this.onMosaicUndoStroke,
    required this.textItems,
    required this.selectedTextItem,
    required this.onTextAdd,
    required this.onTextStyleChanged,
    required this.onTextColorChanged,
    required this.onTextDelete,
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
    required this.curvesState,
    required this.curveChannel,
    required this.curveHistogram,
    required this.onCurveChannelChanged,
    required this.onCurvesChanged,
    required this.onCurveResetChannel,
    required this.wbTemperature,
    required this.wbTint,
    required this.onWbTemperatureChanged,
    required this.onWbTintChanged,
    required this.onWbAuto,
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
  final int selectedProCategory;
  final ScrollController proToolScrollController;
  final ValueChanged<int> onSelectProCategory;
  final VoidCallback onExitProPanel;
  final VoidCallback onConfirmProPanel;
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
  final bool filterCatalogLoading;
  final bool filterCatalogLoadFailed;
  final VoidCallback onFilterCatalogRetry;
  final ImageEditorMosaicType mosaicType;
  final double mosaicBrushSize;
  final ValueChanged<ImageEditorMosaicType> onMosaicTypeChanged;
  final ValueChanged<double> onMosaicBrushSizeChanged;
  final bool mosaicHasStrokes;
  final VoidCallback onMosaicUndoStroke;
  final List<ImageEditorTextItem> textItems;
  final ImageEditorTextItem? selectedTextItem;
  final VoidCallback onTextAdd;
  final ValueChanged<ImageEditorTextStyleKind> onTextStyleChanged;
  final ValueChanged<int> onTextColorChanged;
  final VoidCallback onTextDelete;
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
  final ImageEditorCurvesState curvesState;
  final ImageEditorCurveChannel curveChannel;
  final List<int>? curveHistogram;
  final ValueChanged<ImageEditorCurveChannel> onCurveChannelChanged;
  final ValueChanged<ImageEditorCurvesState> onCurvesChanged;
  final VoidCallback onCurveResetChannel;
  final double wbTemperature;
  final double wbTint;
  final ValueChanged<double> onWbTemperatureChanged;
  final ValueChanged<double> onWbTintChanged;
  final VoidCallback onWbAuto;
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

  Widget _buildPanelTopContent() {
    if (toolIndex == kImageEditorToolCrop) {
      return const SizedBox.shrink();
    }
    if (toolIndex == kImageEditorToolFilter) {
      return _buildFilterCategoryBar();
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
          horizontal:
              AppSpacing.semantic[DesignSemanticConstants
                  .container]?[DesignSemanticConstants.sm] ??
              AppSpacing.containerSm,
          vertical: AppSpacing.xs,
        ),
        child: Row(
          children: [
            _buildRotateActionItem(
              icon: Icons.rotate_left,
              label: MediaText.imageEditorRotateLeft90,
              onTap: onRotateLeft,
            ),
            _buildRotateActionItem(
              icon: Icons.rotate_right,
              label: MediaText.imageEditorRotateRight90,
              onTap: onRotateRight,
            ),
            _buildRotateActionItem(
              icon: Icons.flip,
              label: MediaText.imageEditorFlipHorizontal,
              onTap: onFlipHorizontal,
            ),
            _buildRotateActionItem(
              icon: Icons.flip,
              rotateQuarterTurns: 1,
              label: MediaText.imageEditorFlipVertical,
              onTap: onFlipVertical,
            ),
          ],
        ),
      );
    }
    if (toolIndex == kImageEditorToolFilter) {
      return _buildFilterTemplateList();
    }
    if (toolIndex == kImageEditorToolText) {
      return _buildTextPanelContent();
    }
    if (toolIndex == kImageEditorToolMosaic) {
      return _buildMosaicPanelContent();
    }
    return const SizedBox.shrink();
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
