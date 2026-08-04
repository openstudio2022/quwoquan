import 'package:quwoquan_app/content/media/filter_catalog_release/presentation/image_editor_curve_models.dart';
import 'package:quwoquan_app/content/media/filter_catalog_release/presentation/image_editor_local_models.dart';
import 'package:quwoquan_app/content/media/filter_catalog_release/presentation/image_editor_mosaic_models.dart';
import 'package:quwoquan_app/content/media/filter_catalog_release/presentation/image_editor_text_models.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';

/// 图片编辑单步的强类型参数（R04：禁止弱类型 Map 穿透）。
///
/// 每个 payload 自带工具类型、埋点 subType 与历史面板展示标签。
sealed class ImageEditorStepPayload {
  const ImageEditorStepPayload();

  /// 工具类型（与 kImageEditorToolEntries.type / 埋点 tool 字段一致）。
  String get toolType;

  /// 埋点 subType（专业工具子类别；一级工具为 null）。
  String? get subType => null;

  /// 历史面板展示标签。
  String get label;
}

final class ImageEditorCropStepPayload extends ImageEditorStepPayload {
  const ImageEditorCropStepPayload({required this.ratio});

  final String ratio;

  @override
  String get toolType => 'crop';

  @override
  String get label => MediaText.imageEditorCrop;
}

final class ImageEditorRotateStepPayload extends ImageEditorStepPayload {
  const ImageEditorRotateStepPayload({
    required this.degrees,
    required this.fineDegrees,
    required this.flipHorizontal,
    required this.flipVertical,
  });

  final int degrees;
  final double fineDegrees;
  final bool flipHorizontal;
  final bool flipVertical;

  @override
  String get toolType => 'rotate';

  @override
  String get label => MediaText.imageEditorRotate;
}

final class ImageEditorFilterStepPayload extends ImageEditorStepPayload {
  const ImageEditorFilterStepPayload({
    required this.presetId,
    required this.presetName,
    required this.intensity,
  });

  final String presetId;
  final String presetName;
  final double intensity;

  @override
  String get toolType => 'filter';

  @override
  String get label => MediaText.imageEditorFilter;
}

final class ImageEditorMosaicStepPayload extends ImageEditorStepPayload {
  const ImageEditorMosaicStepPayload({required this.strokes});

  final List<ImageEditorMosaicStroke> strokes;

  @override
  String get toolType => 'mosaic';

  @override
  String get label => MediaText.imageEditorMosaic;
}

final class ImageEditorTextStepPayload extends ImageEditorStepPayload {
  const ImageEditorTextStepPayload({required this.items});

  final List<ImageEditorTextItem> items;

  @override
  String get toolType => 'text';

  @override
  String get label => MediaText.imageEditorText;
}

final class ImageEditorProBaseStepPayload extends ImageEditorStepPayload {
  const ImageEditorProBaseStepPayload({required this.values});

  final Map<String, double> values;

  @override
  String get toolType => 'proTools';

  @override
  String get subType => 'baseAdjustments';

  @override
  String get label => MediaText.imageEditorProTabOverall;
}

final class ImageEditorProLocalStepPayload extends ImageEditorStepPayload {
  const ImageEditorProLocalStepPayload({required this.anchors});

  final List<LocalAnchor> anchors;

  @override
  String get toolType => 'proTools';

  @override
  String get subType => 'localAdjustments';

  @override
  String get label => MediaText.imageEditorProTabLocal;
}

final class ImageEditorProHslStepPayload extends ImageEditorStepPayload {
  const ImageEditorProHslStepPayload({required this.values});

  final Map<String, Map<String, double>> values;

  @override
  String get toolType => 'proTools';

  @override
  String get subType => 'hslAdjustments';

  @override
  String get label => MediaText.imageEditorProTabHsl;
}

final class ImageEditorProBwLevelsStepPayload extends ImageEditorStepPayload {
  const ImageEditorProBwLevelsStepPayload({
    required this.whiteLevel,
    required this.blackLevel,
  });

  final double whiteLevel;
  final double blackLevel;

  @override
  String get toolType => 'proTools';

  @override
  String get subType => 'bwLevelsAdjustments';

  @override
  String get label => MediaText.imageEditorProTabBwLevels;
}

final class ImageEditorProCurvesStepPayload extends ImageEditorStepPayload {
  const ImageEditorProCurvesStepPayload({required this.curves});

  final ImageEditorCurvesState curves;

  @override
  String get toolType => 'proTools';

  @override
  String get subType => 'curves';

  @override
  String get label => MediaText.imageEditorProCurve;
}

final class ImageEditorProWhiteBalanceStepPayload
    extends ImageEditorStepPayload {
  const ImageEditorProWhiteBalanceStepPayload({
    required this.temperature,
    required this.tint,
  });

  final double temperature;
  final double tint;

  @override
  String get toolType => 'proTools';

  @override
  String get subType => 'whiteBalance';

  @override
  String get label => MediaText.imageEditorProWhiteBalance;
}
