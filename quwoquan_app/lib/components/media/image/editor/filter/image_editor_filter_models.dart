import 'dart:convert';

class ImageEditorFilterCategory {
  const ImageEditorFilterCategory({
    required this.id,
    required this.label,
    required this.sort,
    required this.enabled,
  });

  final String id;
  final String label;
  final int sort;
  final bool enabled;

  factory ImageEditorFilterCategory.fromJson(Map<String, dynamic> json) {
    return ImageEditorFilterCategory(
      id: (json['id'] as String? ?? '').trim(),
      label: (json['label'] as String? ?? '').trim(),
      sort: (json['sort'] as num?)?.toInt() ?? 0,
      enabled: json['enabled'] as bool? ?? true,
    );
  }

  Map<String, dynamic> toJson() => <String, dynamic>{
        'id': id,
        'label': label,
        'sort': sort,
        'enabled': enabled,
      };
}

class ImageEditorFilterPreset {
  const ImageEditorFilterPreset({
    required this.id,
    required this.categoryId,
    required this.name,
    required this.sort,
    required this.enabled,
    required this.defaultStrength,
    required this.params,
  });

  final String id;
  final String categoryId;
  final String name;
  final int sort;
  final bool enabled;
  final double defaultStrength;
  final Map<String, double> params;

  factory ImageEditorFilterPreset.fromJson(Map<String, dynamic> json) {
    final rawParams = (json['params'] as Map?)?.cast<Object?, Object?>() ?? const {};
    return ImageEditorFilterPreset(
      id: (json['id'] as String? ?? '').trim(),
      categoryId: (json['categoryId'] as String? ?? '').trim(),
      name: (json['name'] as String? ?? '').trim(),
      sort: (json['sort'] as num?)?.toInt() ?? 0,
      enabled: json['enabled'] as bool? ?? true,
      defaultStrength: ((json['defaultStrength'] as num?)?.toDouble() ?? 100).clamp(0, 100),
      params: <String, double>{
        for (final entry in rawParams.entries)
          entry.key.toString(): (entry.value as num?)?.toDouble() ?? 0,
      },
    );
  }

  Map<String, dynamic> toJson() => <String, dynamic>{
        'id': id,
        'categoryId': categoryId,
        'name': name,
        'sort': sort,
        'enabled': enabled,
        'defaultStrength': defaultStrength,
        'params': params,
      };
}

class ImageEditorFilterConfig {
  const ImageEditorFilterConfig({
    required this.version,
    required this.categories,
    required this.presets,
    required this.recommendedFallbackPresetIds,
  });

  final int version;
  final List<ImageEditorFilterCategory> categories;
  final List<ImageEditorFilterPreset> presets;
  final List<String> recommendedFallbackPresetIds;

  factory ImageEditorFilterConfig.fromJson(Map<String, dynamic> json) {
    final categoriesRaw = (json['categories'] as List?) ?? const [];
    final presetsRaw = (json['presets'] as List?) ?? const [];
    final fallbackRaw = (json['recommendedFallbackPresetIds'] as List?) ?? const [];
    return ImageEditorFilterConfig(
      version: (json['version'] as num?)?.toInt() ?? 1,
      categories: categoriesRaw
          .whereType<Map>()
          .map((entry) => ImageEditorFilterCategory.fromJson(
                entry.cast<String, dynamic>(),
              ))
          .where((entry) => entry.id.isNotEmpty && entry.label.isNotEmpty)
          .toList(growable: false),
      presets: presetsRaw
          .whereType<Map>()
          .map((entry) => ImageEditorFilterPreset.fromJson(
                entry.cast<String, dynamic>(),
              ))
          .where((entry) =>
              entry.id.isNotEmpty &&
              entry.name.isNotEmpty &&
              entry.categoryId.isNotEmpty)
          .toList(growable: false),
      recommendedFallbackPresetIds: fallbackRaw
          .map((entry) => entry.toString().trim())
          .where((entry) => entry.isNotEmpty)
          .toList(growable: false),
    );
  }

  factory ImageEditorFilterConfig.fromJsonString(String source) {
    return ImageEditorFilterConfig.fromJson(
      json.decode(source) as Map<String, dynamic>,
    );
  }

  String toJsonString() => json.encode(toJson());

  Map<String, dynamic> toJson() => <String, dynamic>{
        'version': version,
        'categories': categories.map((entry) => entry.toJson()).toList(),
        'presets': presets.map((entry) => entry.toJson()).toList(),
        'recommendedFallbackPresetIds': recommendedFallbackPresetIds,
      };

  bool isValid() {
    if (categories.isEmpty || presets.isEmpty) return false;
    final categoryIds = categories
        .where((entry) => entry.enabled)
        .map((entry) => entry.id)
        .toSet();
    if (categoryIds.isEmpty) return false;
    for (final preset in presets) {
      if (!preset.enabled) continue;
      if (!categoryIds.contains(preset.categoryId)) return false;
    }
    return true;
  }
}
