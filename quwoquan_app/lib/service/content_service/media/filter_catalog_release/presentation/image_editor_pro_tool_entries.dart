import 'package:flutter/material.dart';
import 'package:quwoquan_app/design_system/media/image_editor_semantic_icon.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/presentation/image_editor_tool_constants.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';

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
        label: MediaText.imageEditorProTabOverall,
      ),
      ImageEditorProToolEntry(
        type: 'local',
        categoryIndex: kImageEditorProCategoryLocal,
        icon: Icons.place_outlined,
        label: MediaText.imageEditorProTabLocal,
      ),
      ImageEditorProToolEntry(
        type: 'hsl',
        categoryIndex: kImageEditorProCategoryHsl,
        icon: Icons.circle_outlined,
        label: MediaText.imageEditorProHsl,
        semanticIconKey: kEditorIconHslSolid,
      ),
      ImageEditorProToolEntry(
        type: 'bwLevels',
        categoryIndex: kImageEditorProCategoryBwLevels,
        icon: Icons.crop_16_9_outlined,
        label: MediaText.imageEditorProBwLevels,
        semanticIconKey: kEditorIconBwLevels,
      ),
      ImageEditorProToolEntry(
        type: 'curves',
        categoryIndex: kImageEditorProCategoryCurve,
        icon: Icons.show_chart,
        label: MediaText.imageEditorProCurve,
      ),
      ImageEditorProToolEntry(
        type: 'whiteBalance',
        categoryIndex: kImageEditorProCategoryWhiteBalance,
        icon: Icons.wb_sunny_outlined,
        label: MediaText.imageEditorProWhiteBalance,
      ),
      ImageEditorProToolEntry(
        type: 'perspective',
        categoryIndex: kImageEditorProCategoryPerspective,
        icon: Icons.transform_outlined,
        label: MediaText.imageEditorProPerspective,
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
    label: MediaText.imageEditorProLightSense,
  ),
  ImageEditorProToolEntry(
    type: 'brightness',
    categoryIndex: kImageEditorProCategoryOverall,
    icon: Icons.light_mode_outlined,
    label: MediaText.imageEditorProBrightness,
  ),
  ImageEditorProToolEntry(
    type: 'exposure',
    categoryIndex: kImageEditorProCategoryOverall,
    icon: Icons.brightness_6_outlined,
    label: MediaText.imageEditorProExposure,
  ),
  ImageEditorProToolEntry(
    type: 'contrast',
    categoryIndex: kImageEditorProCategoryOverall,
    icon: Icons.contrast_outlined,
    label: MediaText.imageEditorProContrast,
  ),
  ImageEditorProToolEntry(
    type: 'saturation',
    categoryIndex: kImageEditorProCategoryOverall,
    icon: Icons.water_drop_outlined,
    label: MediaText.imageEditorProSaturation,
  ),
  ImageEditorProToolEntry(
    type: 'vibrance',
    categoryIndex: kImageEditorProCategoryOverall,
    icon: Icons.opacity_outlined,
    label: MediaText.imageEditorProNaturalSaturation,
  ),
  ImageEditorProToolEntry(
    type: 'texture',
    categoryIndex: kImageEditorProCategoryOverall,
    icon: Icons.texture,
    label: MediaText.imageEditorProTexture,
  ),
  ImageEditorProToolEntry(
    type: 'sharpen',
    categoryIndex: kImageEditorProCategoryOverall,
    icon: Icons.change_history_outlined,
    label: MediaText.imageEditorProSharpen,
  ),
  ImageEditorProToolEntry(
    type: 'structure',
    categoryIndex: kImageEditorProCategoryOverall,
    icon: Icons.details_outlined,
    label: MediaText.imageEditorProStructure,
  ),
  ImageEditorProToolEntry(
    type: 'highlight',
    categoryIndex: kImageEditorProCategoryOverall,
    icon: Icons.timelapse_outlined,
    label: MediaText.imageEditorProHighlight,
    semanticIconKey: kEditorIconHighlightRing,
  ),
  ImageEditorProToolEntry(
    type: 'shadow',
    categoryIndex: kImageEditorProCategoryOverall,
    icon: Icons.brightness_2_outlined,
    label: MediaText.imageEditorProShadow,
    semanticIconKey: kEditorIconShadowRing,
  ),
  ImageEditorProToolEntry(
    type: 'temperature',
    categoryIndex: kImageEditorProCategoryOverall,
    icon: Icons.thermostat_outlined,
    label: MediaText.imageEditorProColorTemp,
  ),
  ImageEditorProToolEntry(
    type: 'tint',
    categoryIndex: kImageEditorProCategoryOverall,
    icon: Icons.join_full_outlined,
    label: MediaText.imageEditorProTone,
  ),
  ImageEditorProToolEntry(
    type: 'denoise',
    categoryIndex: kImageEditorProCategoryOverall,
    icon: Icons.blur_on_outlined,
    label: MediaText.imageEditorProDenoise,
  ),
  ImageEditorProToolEntry(
    type: 'grain',
    categoryIndex: kImageEditorProCategoryOverall,
    icon: Icons.grain,
    label: MediaText.imageEditorProGrain,
  ),
  ImageEditorProToolEntry(
    type: 'vignette',
    categoryIndex: kImageEditorProCategoryOverall,
    icon: Icons.vignette_outlined,
    label: MediaText.imageEditorProVignette,
  ),
  ImageEditorProToolEntry(
    type: 'fade',
    categoryIndex: kImageEditorProCategoryOverall,
    icon: Icons.contrast,
    label: MediaText.imageEditorProFade,
    semanticIconKey: kEditorIconFadeBands,
  ),
];
