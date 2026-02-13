import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/components/media/image/editor/icons/image_editor_semantic_icon.dart';
import 'package:quwoquan_app/components/media/image/editor/tool_list/image_editor_tool_constants.dart';

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

// 兼容已有调用（后续可统一替换为 kImageEditorProBaseEntries）
const List<ImageEditorProToolEntry> kImageEditorProToolEntries =
    kImageEditorProBaseEntries;
