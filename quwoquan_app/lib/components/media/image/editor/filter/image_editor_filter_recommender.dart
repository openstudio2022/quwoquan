import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_models.dart';
import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_recommendation_models.dart';
import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_scene_classifier.dart';

class ImageEditorFilterRecommender {
  const ImageEditorFilterRecommender({
    ImageEditorFilterSceneClassifier sceneClassifier =
        const ImageEditorFilterSceneClassifier(),
  }) : _sceneClassifier = sceneClassifier;

  final ImageEditorFilterSceneClassifier _sceneClassifier;

  List<String> recommendPresetIds({
    required List<ImageEditorFilterPreset> presets,
    required ImageEditorFilterImageFeatures features,
    required Set<String> excludedPresetIds,
    required List<String> fallbackPresetIds,
    required int maxCount,
  }) {
    final scenes = _sceneClassifier.recognize(features);
    final available = presets
        .where((entry) => !excludedPresetIds.contains(entry.id))
        .toList(growable: false);
    final availableIds = available.map((entry) => entry.id).toSet();
    final scores = <_FilterRecommendationScore>[
      for (final preset in available)
        _FilterRecommendationScore(
          presetId: preset.id,
          score: _scorePresetForImage(
            preset: preset,
            features: features,
            scenes: scenes,
          ),
        ),
    ]..sort((a, b) => b.score.compareTo(a.score));
    final result = <String>[];
    for (final entry in scores) {
      result.add(entry.presetId);
      if (result.length >= maxCount) break;
    }
    if (result.length < maxCount) {
      final presetById = {for (final p in presets) p.id: p};
      final skipBwForColorful = _isColorfulImage(features);
      for (final id in fallbackPresetIds) {
        if (!availableIds.contains(id) ||
            excludedPresetIds.contains(id) ||
            result.contains(id)) {
          continue;
        }
        final preset = presetById[id];
        if (preset != null &&
            skipBwForColorful &&
            _isColorReducingPreset(preset)) {
          continue;
        }
        result.add(id);
        if (result.length >= maxCount) break;
      }
    }
    return result.take(maxCount).toList(growable: false);
  }

  double _scorePresetForImage({
    required ImageEditorFilterPreset preset,
    required ImageEditorFilterImageFeatures features,
    required List<ImageEditorFilterSceneRecognition> scenes,
  }) {
    final p = preset.params;
    double score = 0;

    final darkNeed = (0.52 - features.meanLuma).clamp(0.0, 0.52) / 0.52;
    final brightNeed = (features.meanLuma - 0.62).clamp(0.0, 0.38) / 0.38;
    final lowContrastNeed = (0.15 - features.contrast).clamp(0.0, 0.15) / 0.15;
    final highContrastNeed = (features.contrast - 0.22).clamp(0.0, 0.78) / 0.78;
    final lowSatNeed =
        (0.30 - features.meanSaturation).clamp(0.0, 0.30) / 0.30;
    final highSatNeed =
        (features.meanSaturation - 0.58).clamp(0.0, 0.42) / 0.42;
    final coolNeed = (-features.warmth).clamp(0.0, 1.0);
    final warmNeed = features.warmth.clamp(0.0, 1.0);
    final flatNeed = (0.09 - features.texture).clamp(0.0, 0.09) / 0.09;
    final harshNeed = (features.texture - 0.17).clamp(0.0, 0.83) / 0.83;

    double param(String key) => (p[key] ?? 0).toDouble();
    score += darkNeed *
        (param('brightness') +
                param('exposure') +
                param('lightSense') +
                param('shadow'))
            .clamp(-100, 100) *
        0.15;
    score += brightNeed *
        (-param('highlight') - param('brightness')).clamp(-100, 100) *
        0.12;
    score += lowContrastNeed *
        (param('contrast') + param('structure')).clamp(-100, 100) *
        0.10;
    score += highContrastNeed *
        (-param('contrast') + param('fade')).clamp(-100, 100) *
        0.10;
    score += lowSatNeed *
        (param('saturation') + param('vibrance')).clamp(-100, 100) *
        0.09;
    score += highSatNeed *
        (-param('saturation') - param('vibrance')).clamp(-100, 100) *
        0.09;
    score += coolNeed * param('temperature').clamp(-100, 100) * 0.08;
    score += warmNeed * (-param('temperature')).clamp(-100, 100) * 0.08;
    score += flatNeed *
        (param('structure') + param('sharpen') + param('texture'))
            .clamp(-100, 100) *
        0.08;
    score += harshNeed *
        (param('fade') - param('contrast')).clamp(-100, 100) *
        0.08;

    final styleStrength = p.values.fold<double>(
      0,
      (prev, value) => prev + value.abs(),
    );
    score += (styleStrength / 500).clamp(0, 1.5) * 2.0;
    score += _sceneCategoryBonus(
      categoryId: preset.categoryId,
      scenes: scenes,
    );
    score += _sceneParamBonus(
      params: p,
      scenes: scenes,
    );
    score += _whitelistBonus(
      features: features,
      params: p,
    );
    score -= _blacklistPenalty(
      preset: preset,
      features: features,
      params: p,
    );
    return score;
  }

  double _sceneCategoryBonus({
    required String categoryId,
    required List<ImageEditorFilterSceneRecognition> scenes,
  }) {
    if (scenes.isEmpty) return 0;
    const categoryMap = <ImageEditorFilterSceneType, List<String>>{
      ImageEditorFilterSceneType.portrait: <String>[
        'portrait',
        'fresh_natural',
        'movie_dream',
        'seasons',
      ],
      ImageEditorFilterSceneType.landscape: <String>[
        'landscape_travel',
        'fresh_natural',
        'seasons',
      ],
      ImageEditorFilterSceneType.food: <String>[
        'food',
        'fresh_natural',
        'seasons',
      ],
      ImageEditorFilterSceneType.night: <String>[
        'movie_dream',
        'film_retro',
        'bw_art',
      ],
      ImageEditorFilterSceneType.architecture: <String>[
        'texture',
        'bw_art',
        'film_retro',
      ],
      ImageEditorFilterSceneType.document: <String>[
        'bw_art',
        'texture',
        'fresh_natural',
      ],
    };
    var bonus = 0.0;
    for (final scene in scenes) {
      final preferred = categoryMap[scene.type] ?? const <String>[];
      if (preferred.contains(categoryId)) {
        bonus += 2.8 * scene.score;
      }
    }
    return bonus;
  }

  double _sceneParamBonus({
    required Map<String, double> params,
    required List<ImageEditorFilterSceneRecognition> scenes,
  }) {
    if (scenes.isEmpty) return 0;
    const expectations = <ImageEditorFilterSceneType, Map<String, double>>{
      ImageEditorFilterSceneType.portrait: <String, double>{
        'highlight': -1,
        'shadow': 1,
        'saturation': -0.2,
        'temperature': 0.3,
      },
      ImageEditorFilterSceneType.landscape: <String, double>{
        'contrast': 0.6,
        'saturation': 0.6,
        'vibrance': 0.7,
        'structure': 0.4,
      },
      ImageEditorFilterSceneType.food: <String, double>{
        'saturation': 0.7,
        'temperature': 0.6,
        'contrast': 0.4,
        'sharpen': 0.3,
      },
      ImageEditorFilterSceneType.night: <String, double>{
        'shadow': 0.7,
        'highlight': -0.4,
        'temperature': -0.5,
        'contrast': 0.4,
      },
      ImageEditorFilterSceneType.architecture: <String, double>{
        'contrast': 0.7,
        'structure': 0.7,
        'sharpen': 0.5,
        'saturation': -0.2,
      },
      ImageEditorFilterSceneType.document: <String, double>{
        'contrast': 0.8,
        'saturation': -0.8,
        'highlight': -0.3,
        'sharpen': 0.4,
      },
    };
    var bonus = 0.0;
    for (final scene in scenes) {
      final expected = expectations[scene.type];
      if (expected == null) continue;
      expected.forEach((key, direction) {
        final value = (params[key] ?? 0).clamp(-100, 100) / 100.0;
        final align = (value * direction).clamp(-1.0, 1.0);
        bonus += align * scene.score * 1.2;
      });
    }
    return bonus;
  }

  /// 大红大绿、色彩浓郁（红/绿/蓝/暖色占比高或整体饱和度高）视为彩色图，不推荐降色滤镜。
  bool _isColorfulImage(ImageEditorFilterImageFeatures features) {
    return features.meanSaturation > 0.28 ||
        features.warmColorRatio > 0.08 ||
        features.greenRatio > 0.10 ||
        features.blueRatio > 0.10;
  }

  /// 降色类预设：黑白分类或明显降低饱和度/鲜艳度的参数。
  bool _isColorReducingPreset(ImageEditorFilterPreset preset) {
    if (preset.categoryId == 'bw_art') return true;
    final p = preset.params;
    final sat = (p['saturation'] ?? 0).toDouble();
    final vibrance = (p['vibrance'] ?? 0).toDouble();
    if (sat <= -25) return true;
    if (sat <= 0 && vibrance <= -15) return true;
    return false;
  }

  /// 白名单机制（专业摄影“好图”导向）：
  /// - 色彩可用时，优先彩色增强
  /// - 动态范围偏窄时，优先提对比/提细节
  /// - 高光/阴影失衡时，优先纠偏参数
  double _whitelistBonus({
    required ImageEditorFilterImageFeatures features,
    required Map<String, double> params,
  }) {
    double bonus = 0;
    final saturation = (params['saturation'] ?? 0).toDouble();
    final vibrance = (params['vibrance'] ?? 0).toDouble();
    final contrast = (params['contrast'] ?? 0).toDouble();
    final structure = (params['structure'] ?? 0).toDouble();
    final sharpen = (params['sharpen'] ?? 0).toDouble();
    final highlight = (params['highlight'] ?? 0).toDouble();
    final shadow = (params['shadow'] ?? 0).toDouble();

    if (features.meanSaturation > 0.24 && (saturation > 4 || vibrance > 4)) {
      bonus += 1.2;
    }
    if (features.contrast < 0.16 && contrast > 6) {
      bonus += 1.0;
    }
    if (features.texture < 0.10 && (structure > 6 || sharpen > 6)) {
      bonus += 0.8;
    }
    if (features.highlightRatio > 0.32 && highlight < -4) {
      bonus += 0.8;
    }
    if (features.shadowRatio > 0.36 && shadow > 4) {
      bonus += 0.8;
    }
    return bonus;
  }

  /// 黑名单机制（不佳输出风险）：
  /// - 灰度倾向高：优先降权
  /// - 彩色图上降色预设：强降权
  /// - 灰图继续降色：避免“脏灰”
  double _blacklistPenalty({
    required ImageEditorFilterPreset preset,
    required ImageEditorFilterImageFeatures features,
    required Map<String, double> params,
  }) {
    double penalty = 0;
    final saturation = (params['saturation'] ?? 0).toDouble();
    final vibrance = (params['vibrance'] ?? 0).toDouble();
    final contrast = (params['contrast'] ?? 0).toDouble();

    // 灰度风险：图像越偏灰，降色越要谨慎。
    if (features.grayRatio > 0.45 && saturation <= 0) {
      penalty += 2.4;
    }
    // 彩色图命中降色预设，明显降权。
    if (_isColorfulImage(features) && _isColorReducingPreset(preset)) {
      penalty += 2.2;
    }
    if (saturation <= -25) {
      penalty += 1.8;
    }
    if (saturation <= 0 && vibrance <= -12) {
      penalty += 1.2;
    }
    // 低对比图再降对比，容易发灰发闷。
    if (features.contrast < 0.14 && contrast < -4) {
      penalty += 1.0;
    }
    return penalty;
  }
}

class _FilterRecommendationScore {
  const _FilterRecommendationScore({
    required this.presetId,
    required this.score,
  });

  final String presetId;
  final double score;
}
