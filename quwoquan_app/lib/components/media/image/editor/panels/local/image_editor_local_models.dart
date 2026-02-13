import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

const String kLocalParamLightSense = 'lightSense';
const String kLocalParamBrightness = 'brightness';
const String kLocalParamExposure = 'exposure';
const String kLocalParamContrast = 'contrast';
const String kLocalParamSaturation = 'saturation';
const String kLocalParamVibrance = 'vibrance';
const String kLocalParamTexture = 'texture';
const String kLocalParamSharpen = 'sharpen';
const String kLocalParamStructure = 'structure';
const String kLocalParamHighlight = 'highlight';
const String kLocalParamShadow = 'shadow';
const String kLocalParamTemperature = 'temperature';
const String kLocalParamTint = 'tint';
const String kLocalParamGrain = 'grain';
const String kLocalParamFade = 'fade';

const List<String> kLocalParamOrder = <String>[
  kLocalParamLightSense,
  kLocalParamBrightness,
  kLocalParamExposure,
  kLocalParamContrast,
  kLocalParamSaturation,
  kLocalParamVibrance,
  kLocalParamTexture,
  kLocalParamSharpen,
  kLocalParamStructure,
  kLocalParamHighlight,
  kLocalParamShadow,
  kLocalParamTemperature,
  kLocalParamTint,
  kLocalParamGrain,
  kLocalParamFade,
];

String localParamLabel(String key) {
  switch (key) {
    case kLocalParamLightSense:
      return UITextConstants.imageEditorProLightSense;
    case kLocalParamBrightness:
      return UITextConstants.imageEditorProBrightness;
    case kLocalParamExposure:
      return UITextConstants.imageEditorProExposure;
    case kLocalParamContrast:
      return UITextConstants.imageEditorProContrast;
    case kLocalParamSaturation:
      return UITextConstants.imageEditorProSaturation;
    case kLocalParamVibrance:
      return UITextConstants.imageEditorProNaturalSaturation;
    case kLocalParamTexture:
      return UITextConstants.imageEditorProTexture;
    case kLocalParamSharpen:
      return UITextConstants.imageEditorProSharpen;
    case kLocalParamStructure:
      return UITextConstants.imageEditorProStructure;
    case kLocalParamHighlight:
      return UITextConstants.imageEditorProHighlight;
    case kLocalParamShadow:
      return UITextConstants.imageEditorProShadow;
    case kLocalParamTemperature:
      return UITextConstants.imageEditorProColorTemp;
    case kLocalParamTint:
      return UITextConstants.imageEditorProTone;
    case kLocalParamGrain:
      return UITextConstants.imageEditorProGrain;
    case kLocalParamFade:
      return UITextConstants.imageEditorProFade;
    default:
      return key;
  }
}

String localParamLetter(String key) {
  switch (key) {
    case kLocalParamLightSense:
      return '光';
    case kLocalParamBrightness:
      return UITextConstants.imageEditorProAnchorLetterBrightness;
    case kLocalParamExposure:
      return '曝';
    case kLocalParamContrast:
      return UITextConstants.imageEditorProAnchorLetterContrast;
    case kLocalParamSaturation:
      return UITextConstants.imageEditorProAnchorLetterSaturation;
    case kLocalParamVibrance:
      return '自';
    case kLocalParamTexture:
      return '纹';
    case kLocalParamSharpen:
      return '锐';
    case kLocalParamStructure:
      return UITextConstants.imageEditorProAnchorLetterStructure;
    case kLocalParamHighlight:
      return '高';
    case kLocalParamShadow:
      return '阴';
    case kLocalParamTemperature:
      return '温';
    case kLocalParamTint:
      return '调';
    case kLocalParamGrain:
      return '粒';
    case kLocalParamFade:
      return '褪';
    default:
      return '?';
  }
}

class LocalAnchor {
  const LocalAnchor({
    required this.id,
    required this.center,
    required this.radius,
    required this.values,
    required this.selectedParam,
  });

  final int id;
  final Offset center;
  final double radius;
  final Map<String, double> values;
  final String selectedParam;

  LocalAnchor copyWith({
    Offset? center,
    double? radius,
    Map<String, double>? values,
    String? selectedParam,
  }) {
    return LocalAnchor(
      id: id,
      center: center ?? this.center,
      radius: radius ?? this.radius,
      values: values ?? Map<String, double>.from(this.values),
      selectedParam: selectedParam ?? this.selectedParam,
    );
  }
}

Map<String, double> createDefaultLocalAnchorValues() => <String, double>{
      kLocalParamLightSense: 0,
      kLocalParamBrightness: 0,
      kLocalParamExposure: 0,
      kLocalParamContrast: 0,
      kLocalParamSaturation: 0,
      kLocalParamVibrance: 0,
      kLocalParamTexture: 0,
      kLocalParamSharpen: 0,
      kLocalParamStructure: 0,
      kLocalParamHighlight: 0,
      kLocalParamShadow: 0,
      kLocalParamTemperature: 0,
      kLocalParamTint: 0,
      kLocalParamGrain: 0,
      kLocalParamFade: 0,
    };

List<LocalAnchor> cloneLocalAnchors(List<LocalAnchor> anchors) => anchors
    .map(
      (anchor) => LocalAnchor(
        id: anchor.id,
        center: anchor.center,
        radius: anchor.radius,
        values: Map<String, double>.from(anchor.values),
        selectedParam: anchor.selectedParam,
      ),
    )
    .toList(growable: true);
