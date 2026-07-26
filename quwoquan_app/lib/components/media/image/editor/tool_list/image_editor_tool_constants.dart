import 'package:flutter/material.dart';
import 'package:quwoquan_app/components/media/image/editor/icons/image_editor_semantic_icon.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';

const int kImageEditorToolFilter = 0;
const int kImageEditorToolCrop = 1;
const int kImageEditorToolRotate = 2;
const int kImageEditorToolPro = 3;
const int kImageEditorToolText = 4;
const int kImageEditorToolMosaic = 5;

const int kImageEditorProCategoryOverall = 0;
const int kImageEditorProCategoryLocal = 1;
const int kImageEditorProCategoryHsl = 2;
const int kImageEditorProCategoryCurve = 3;
const int kImageEditorProCategoryWhiteBalance = 4;
const int kImageEditorProCategoryBwLevels = 5;

class ImageEditorToolEntry {
  const ImageEditorToolEntry({
    required this.index,
    required this.type,
    required this.icon,
    required this.label,
    this.semanticIconKey,
  });

  final int index;
  final String type;
  final IconData icon;
  final String label;
  final String? semanticIconKey;
}

/// 图片编辑器一级工具的唯一有序定义。
///
/// 面板选择、埋点类型和底栏展示都消费此列表，避免索引、类型和文案各自维护。
const List<ImageEditorToolEntry> kImageEditorToolEntries =
    <ImageEditorToolEntry>[
      ImageEditorToolEntry(
        index: kImageEditorToolFilter,
        type: 'filter',
        icon: Icons.circle_outlined,
        label: UITextConstants.imageEditorFilter,
        semanticIconKey: kEditorIconFilterRings,
      ),
      ImageEditorToolEntry(
        index: kImageEditorToolCrop,
        type: 'crop',
        icon: Icons.crop,
        label: UITextConstants.imageEditorCrop,
      ),
      ImageEditorToolEntry(
        index: kImageEditorToolRotate,
        type: 'rotate',
        icon: Icons.rotate_right,
        label: UITextConstants.imageEditorRotate,
      ),
      ImageEditorToolEntry(
        index: kImageEditorToolPro,
        type: 'proTools',
        icon: Icons.auto_fix_high,
        label: UITextConstants.imageEditorProTools,
      ),
      ImageEditorToolEntry(
        index: kImageEditorToolText,
        type: 'text',
        icon: Icons.text_fields,
        label: UITextConstants.imageEditorText,
      ),
      ImageEditorToolEntry(
        index: kImageEditorToolMosaic,
        type: 'mosaic',
        icon: Icons.grid_on,
        label: UITextConstants.imageEditorMosaic,
      ),
    ];

ImageEditorToolEntry imageEditorToolEntryAt(int index) {
  return kImageEditorToolEntries.firstWhere((entry) => entry.index == index);
}

ImageEditorToolEntry? imageEditorToolEntryForType(String type) {
  for (final entry in kImageEditorToolEntries) {
    if (entry.type == type) {
      return entry;
    }
  }
  return null;
}
