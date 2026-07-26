import 'package:flutter/material.dart';
import 'package:quwoquan_app/components/media/image/editor/icons/image_editor_semantic_icon.dart';
import 'package:quwoquan_app/components/media/image/editor/tool_list/image_editor_tool_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';

class ImageEditorProToolEntry {
  const ImageEditorProToolEntry({
    required this.type,
    required this.categoryIndex,
    required this.icon,
    required this.label,
    this.semanticIconKey,
  });

  final String type;
  final int categoryIndex;
  final IconData icon;
  final String label;
  final String? semanticIconKey;
}

/// 专业工具入口的唯一有序定义。
const List<ImageEditorProToolEntry> kImageEditorProCategoryEntries =
    <ImageEditorProToolEntry>[
      ImageEditorProToolEntry(
        type: 'overall',
        categoryIndex: kImageEditorProCategoryOverall,
        icon: Icons.tune,
        label: UITextConstants.imageEditorProTabOverall,
      ),
      ImageEditorProToolEntry(
        type: 'local',
        categoryIndex: kImageEditorProCategoryLocal,
        icon: Icons.place_outlined,
        label: UITextConstants.imageEditorProTabLocal,
      ),
      ImageEditorProToolEntry(
        type: 'hsl',
        categoryIndex: kImageEditorProCategoryHsl,
        icon: Icons.circle_outlined,
        label: UITextConstants.imageEditorProHsl,
        semanticIconKey: kEditorIconHslSolid,
      ),
      ImageEditorProToolEntry(
        type: 'bwLevels',
        categoryIndex: kImageEditorProCategoryBwLevels,
        icon: Icons.crop_16_9_outlined,
        label: UITextConstants.imageEditorProBwLevels,
        semanticIconKey: kEditorIconBwLevels,
      ),
      ImageEditorProToolEntry(
        type: 'curves',
        categoryIndex: kImageEditorProCategoryCurve,
        icon: Icons.show_chart,
        label: UITextConstants.imageEditorProCurve,
      ),
      ImageEditorProToolEntry(
        type: 'whiteBalance',
        categoryIndex: kImageEditorProCategoryWhiteBalance,
        icon: Icons.wb_sunny_outlined,
        label: UITextConstants.imageEditorProWhiteBalance,
      ),
    ];

ImageEditorProToolEntry? imageEditorProCategoryEntryForType(String type) {
  for (final entry in kImageEditorProCategoryEntries) {
    if (entry.type == type) {
      return entry;
    }
  }
  return null;
}

/// 整体/局部调节项的唯一有序定义。
const List<ImageEditorProToolEntry> kImageEditorProBaseEntries = [
  ImageEditorProToolEntry(
    type: 'lightSense',
    categoryIndex: kImageEditorProCategoryOverall,
    icon: Icons.wb_twilight_outlined,
    label: UITextConstants.imageEditorProLightSense,
  ),
  ImageEditorProToolEntry(
    type: 'brightness',
    categoryIndex: kImageEditorProCategoryOverall,
    icon: Icons.light_mode_outlined,
    label: UITextConstants.imageEditorProBrightness,
  ),
  ImageEditorProToolEntry(
    type: 'exposure',
    categoryIndex: kImageEditorProCategoryOverall,
    icon: Icons.brightness_6_outlined,
    label: UITextConstants.imageEditorProExposure,
  ),
  ImageEditorProToolEntry(
    type: 'contrast',
    categoryIndex: kImageEditorProCategoryOverall,
    icon: Icons.contrast_outlined,
    label: UITextConstants.imageEditorProContrast,
  ),
  ImageEditorProToolEntry(
    type: 'saturation',
    categoryIndex: kImageEditorProCategoryOverall,
    icon: Icons.water_drop_outlined,
    label: UITextConstants.imageEditorProSaturation,
  ),
  ImageEditorProToolEntry(
    type: 'vibrance',
    categoryIndex: kImageEditorProCategoryOverall,
    icon: Icons.opacity_outlined,
    label: UITextConstants.imageEditorProNaturalSaturation,
  ),
  ImageEditorProToolEntry(
    type: 'texture',
    categoryIndex: kImageEditorProCategoryOverall,
    icon: Icons.texture,
    label: UITextConstants.imageEditorProTexture,
  ),
  ImageEditorProToolEntry(
    type: 'sharpen',
    categoryIndex: kImageEditorProCategoryOverall,
    icon: Icons.change_history_outlined,
    label: UITextConstants.imageEditorProSharpen,
  ),
  ImageEditorProToolEntry(
    type: 'structure',
    categoryIndex: kImageEditorProCategoryOverall,
    icon: Icons.details_outlined,
    label: UITextConstants.imageEditorProStructure,
  ),
  ImageEditorProToolEntry(
    type: 'highlight',
    categoryIndex: kImageEditorProCategoryOverall,
    icon: Icons.timelapse_outlined,
    label: UITextConstants.imageEditorProHighlight,
    semanticIconKey: kEditorIconHighlightRing,
  ),
  ImageEditorProToolEntry(
    type: 'shadow',
    categoryIndex: kImageEditorProCategoryOverall,
    icon: Icons.brightness_2_outlined,
    label: UITextConstants.imageEditorProShadow,
    semanticIconKey: kEditorIconShadowRing,
  ),
  ImageEditorProToolEntry(
    type: 'temperature',
    categoryIndex: kImageEditorProCategoryOverall,
    icon: Icons.thermostat_outlined,
    label: UITextConstants.imageEditorProColorTemp,
  ),
  ImageEditorProToolEntry(
    type: 'tint',
    categoryIndex: kImageEditorProCategoryOverall,
    icon: Icons.join_full_outlined,
    label: UITextConstants.imageEditorProTone,
  ),
  ImageEditorProToolEntry(
    type: 'grain',
    categoryIndex: kImageEditorProCategoryOverall,
    icon: Icons.grain,
    label: UITextConstants.imageEditorProGrain,
  ),
  ImageEditorProToolEntry(
    type: 'fade',
    categoryIndex: kImageEditorProCategoryOverall,
    icon: Icons.contrast,
    label: UITextConstants.imageEditorProFade,
    semanticIconKey: kEditorIconFadeBands,
  ),
];
