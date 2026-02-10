import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/components/media/image/editor/tool_list/image_editor_tool_constants.dart';

class ImageEditorProToolEntry {
  const ImageEditorProToolEntry({
    required this.type,
    required this.categoryIndex,
    required this.icon,
    required this.label,
  });

  final String type;
  final int categoryIndex;
  final IconData icon;
  final String label;
}

const List<ImageEditorProToolEntry> kImageEditorProToolEntries = [
  ImageEditorProToolEntry(
    type: 'exposure',
    categoryIndex: kImageEditorProCategoryExposure,
    icon: Icons.exposure,
    label: UITextConstants.imageEditorProExposure,
  ),
  ImageEditorProToolEntry(
    type: 'brightness',
    categoryIndex: kImageEditorProCategoryExposure,
    icon: Icons.brightness_6,
    label: UITextConstants.imageEditorProBrightness,
  ),
  ImageEditorProToolEntry(
    type: 'contrast',
    categoryIndex: kImageEditorProCategoryExposure,
    icon: Icons.contrast,
    label: UITextConstants.imageEditorProContrast,
  ),
  ImageEditorProToolEntry(
    type: 'whiteBalance',
    categoryIndex: kImageEditorProCategoryColor,
    icon: Icons.wb_sunny_outlined,
    label: UITextConstants.imageEditorProWhiteBalance,
  ),
  ImageEditorProToolEntry(
    type: 'saturation',
    categoryIndex: kImageEditorProCategoryColor,
    icon: Icons.palette_outlined,
    label: UITextConstants.imageEditorProSaturation,
  ),
  ImageEditorProToolEntry(
    type: 'hsl',
    categoryIndex: kImageEditorProCategoryColor,
    icon: Icons.color_lens_outlined,
    label: UITextConstants.imageEditorProHsl,
  ),
  ImageEditorProToolEntry(
    type: 'tone',
    categoryIndex: kImageEditorProCategoryColor,
    icon: Icons.tune,
    label: UITextConstants.imageEditorProTone,
  ),
  ImageEditorProToolEntry(
    type: 'highlight',
    categoryIndex: kImageEditorProCategoryLight,
    icon: Icons.wb_twilight_outlined,
    label: UITextConstants.imageEditorProHighlight,
  ),
  ImageEditorProToolEntry(
    type: 'shadow',
    categoryIndex: kImageEditorProCategoryLight,
    icon: Icons.nightlight_round,
    label: UITextConstants.imageEditorProShadow,
  ),
  ImageEditorProToolEntry(
    type: 'curve',
    categoryIndex: kImageEditorProCategoryLight,
    icon: Icons.show_chart,
    label: UITextConstants.imageEditorProCurve,
  ),
  ImageEditorProToolEntry(
    type: 'local',
    categoryIndex: kImageEditorProCategoryLight,
    icon: Icons.radar,
    label: UITextConstants.imageEditorProLocal,
  ),
  ImageEditorProToolEntry(
    type: 'denoise',
    categoryIndex: kImageEditorProCategoryTexture,
    icon: Icons.blur_on,
    label: UITextConstants.imageEditorProDenoise,
  ),
  ImageEditorProToolEntry(
    type: 'sharpen',
    categoryIndex: kImageEditorProCategoryTexture,
    icon: Icons.auto_awesome,
    label: UITextConstants.imageEditorProSharpen,
  ),
  ImageEditorProToolEntry(
    type: 'unsharpen',
    categoryIndex: kImageEditorProCategoryTexture,
    icon: Icons.blur_linear,
    label: UITextConstants.imageEditorProUnsharpen,
  ),
];
