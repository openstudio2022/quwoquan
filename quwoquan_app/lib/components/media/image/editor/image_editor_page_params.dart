import 'package:flutter/material.dart';
import 'package:quwoquan_app/components/media/image/editor/panels/local/image_editor_local_models.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';

/// 非 `*_page.dart`：步骤标签与工具确认参数映射，避免页面扫描路径出现 `Map<String, dynamic>` / `dynamic`。

String imageEditorStepTypeLabel(String type, [Map<String, dynamic>? params]) {
  if (type == 'proTools' && params != null) {
    switch (params['subType'] as String?) {
      case 'curve':
        return UITextConstants.imageEditorProCurve;
      case 'baseAdjustments':
        return UITextConstants.imageEditorProTabOverall;
      case 'localAdjustments':
        return UITextConstants.imageEditorProTabLocal;
      case 'hslAdjustments':
        return UITextConstants.imageEditorProTabHsl;
      case 'bwLevelsAdjustments':
        return UITextConstants.imageEditorProTabBwLevels;
      case 'whiteBalance':
        return UITextConstants.imageEditorProWhiteBalance;
      case 'local':
        return UITextConstants.imageEditorProLocal;
      case 'hsl':
        return UITextConstants.imageEditorProHsl;
      case 'exposure':
        return UITextConstants.imageEditorProExposure;
      case 'brightness':
        return UITextConstants.imageEditorProBrightness;
      case 'contrast':
        return UITextConstants.imageEditorProContrast;
      case 'saturation':
        return UITextConstants.imageEditorProSaturation;
      case 'highlight':
        return UITextConstants.imageEditorProHighlight;
      case 'shadow':
        return UITextConstants.imageEditorProShadow;
      case 'tone':
        return UITextConstants.imageEditorProTone;
      case 'denoise':
        return UITextConstants.imageEditorProDenoise;
      case 'sharpen':
        return UITextConstants.imageEditorProSharpen;
      case 'unsharpen':
        return UITextConstants.imageEditorProUnsharpen;
    }
  }
  switch (type) {
    case 'rotate':
      return UITextConstants.imageEditorRotate;
    case 'crop':
      return UITextConstants.imageEditorCrop;
    case 'filter':
      return UITextConstants.imageEditorFilter;
    case 'beauty':
      return UITextConstants.imageEditorBeauty;
    case 'proTools':
      return UITextConstants.imageEditorProTools;
    case 'frame':
      return UITextConstants.imageEditorFrame;
    case 'text':
      return UITextConstants.imageEditorText;
    case 'mosaic':
      return UITextConstants.imageEditorMosaic;
    default:
      return type;
  }
}

Map<String, dynamic> imageEditorToolConfirmParamsBase(int toolIndex) {
  return <String, dynamic>{'index': toolIndex};
}

Map<String, dynamic> imageEditorMultiImageDonePopPayload({
  required int currentIndex,
  required String path,
}) {
  return <String, dynamic>{'index': currentIndex, 'path': path};
}

Map<String, dynamic> imageEditorLocalAnchorWireMap(LocalAnchor anchor) {
  return <String, dynamic>{
    'id': anchor.id,
    'x': anchor.center.dx,
    'y': anchor.center.dy,
    'radius': anchor.radius,
    'selectedParam': anchor.selectedParam,
    'values': Map<String, double>.from(anchor.values),
  };
}

List<LocalAnchor> imageEditorParseLocalAnchorsFromParams(
  Map<String, dynamic> params, {
  required int Function() allocateId,
}) {
  final anchorsRaw = (params['anchors'] as List?) ?? const [];
  final restored = <LocalAnchor>[];
  for (final raw in anchorsRaw) {
    if (raw is! Map) continue;
    final map = Map<Object?, Object?>.from(raw);
    final valuesObj = map['values'];
    final valuesRaw = valuesObj is Map
        ? Map<Object?, Object?>.from(valuesObj)
        : const <Object?, Object?>{};
    restored.add(
      LocalAnchor(
        id: (map['id'] as num?)?.toInt() ?? allocateId(),
        center: Offset(
          ((map['x'] as num?)?.toDouble() ?? 0.5).clamp(0.0, 1.0),
          ((map['y'] as num?)?.toDouble() ?? 0.5).clamp(0.0, 1.0),
        ),
        radius: ((map['radius'] as num?)?.toDouble() ?? 0.18).clamp(
          0.06,
          0.45,
        ),
        values: <String, double>{
          for (final key in kLocalParamOrder)
            key: (valuesRaw[key] as num?)?.toDouble() ?? 0,
        },
        selectedParam:
            (map['selectedParam'] as String?) ?? kLocalParamBrightness,
      ),
    );
  }
  return restored;
}
