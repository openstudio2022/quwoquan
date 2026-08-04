class ImageEditorFilterImageFeatures {
  const ImageEditorFilterImageFeatures({
    this.meanLuma = 0.5,
    this.contrast = 0.18,
    this.meanSaturation = 0.4,
    this.warmth = 0,
    this.texture = 0.12,
    this.shadowRatio = 0.2,
    this.highlightRatio = 0.2,
    this.skinRatio = 0.0,
    this.greenRatio = 0.0,
    this.blueRatio = 0.0,
    this.warmColorRatio = 0.0,
    this.grayRatio = 0.0,
    this.aspectRatio = 1.0,
  });

  final double meanLuma;
  final double contrast;
  final double meanSaturation;
  final double warmth;
  final double texture;
  final double shadowRatio;
  final double highlightRatio;
  final double skinRatio;
  final double greenRatio;
  final double blueRatio;
  final double warmColorRatio;
  final double grayRatio;
  final double aspectRatio;
}

enum ImageEditorFilterSceneType {
  portrait,
  landscape,
  food,
  night,
  architecture,
  document,
}

class ImageEditorFilterSceneRecognition {
  const ImageEditorFilterSceneRecognition({
    required this.type,
    required this.score,
  });

  final ImageEditorFilterSceneType type;
  final double score;
}
