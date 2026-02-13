import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_recommendation_models.dart';

class ImageEditorFilterSceneClassifier {
  const ImageEditorFilterSceneClassifier();

  List<ImageEditorFilterSceneRecognition> recognize(
    ImageEditorFilterImageFeatures features, {
    int topK = 3,
    double minScore = 0.24,
  }) {
    final recognitions = <ImageEditorFilterSceneRecognition>[
      ImageEditorFilterSceneRecognition(
        type: ImageEditorFilterSceneType.portrait,
        score: _clamp01(
          0.52 * features.skinRatio +
              0.16 * (1 - (features.texture - 0.11).abs() / 0.11).clamp(0.0, 1.0) +
              0.18 *
                  (1 - (features.meanLuma - 0.56).abs() / 0.44)
                      .clamp(0.0, 1.0) +
              0.14 *
                  (1 - (features.meanSaturation - 0.42).abs() / 0.42)
                      .clamp(0.0, 1.0),
        ),
      ),
      ImageEditorFilterSceneRecognition(
        type: ImageEditorFilterSceneType.landscape,
        score: _clamp01(
          0.28 * features.greenRatio +
              0.24 * features.blueRatio +
              0.16 * features.contrast +
              0.16 * features.texture +
              0.16 * features.meanSaturation,
        ),
      ),
      ImageEditorFilterSceneRecognition(
        type: ImageEditorFilterSceneType.food,
        score: _clamp01(
          0.36 * features.warmColorRatio +
              0.30 * features.meanSaturation +
              0.18 *
                  (1 - (features.meanLuma - 0.55).abs() / 0.45)
                      .clamp(0.0, 1.0) +
              0.16 * features.texture,
        ),
      ),
      ImageEditorFilterSceneRecognition(
        type: ImageEditorFilterSceneType.night,
        score: _clamp01(
          0.54 * features.shadowRatio +
              0.16 * (1 - features.meanLuma) +
              0.18 * features.blueRatio +
              0.12 * features.contrast,
        ),
      ),
      ImageEditorFilterSceneRecognition(
        type: ImageEditorFilterSceneType.architecture,
        score: _clamp01(
          0.30 * features.contrast +
              0.28 * features.texture +
              0.20 *
                  (1 - (features.meanSaturation - 0.35).abs() / 0.35)
                      .clamp(0.0, 1.0) +
              0.22 * (1 - (features.aspectRatio - 1.5).abs() / 1.5).clamp(0.0, 1.0),
        ),
      ),
      ImageEditorFilterSceneRecognition(
        type: ImageEditorFilterSceneType.document,
        score: _clamp01(
          0.40 * features.highlightRatio +
              0.32 * (1 - features.meanSaturation) +
              0.16 * features.contrast +
              0.12 * (1 - features.warmColorRatio),
        ),
      ),
    ]..sort((a, b) => b.score.compareTo(a.score));
    return recognitions
        .where((entry) => entry.score > minScore)
        .take(topK)
        .toList(growable: false);
  }

  double _clamp01(double value) => value.clamp(0.0, 1.0).toDouble();
}
