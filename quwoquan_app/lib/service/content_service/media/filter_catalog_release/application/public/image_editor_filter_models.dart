import 'dart:convert';

typedef ImageEditorFilterDigestComputer = String Function(String canonicalJson);

class ImageEditorFilterCategory {
  const ImageEditorFilterCategory({
    required this.id,
    required this.label,
    required this.sort,
    required this.enabled,
    this.displayNameEn,
  });

  final String id;
  final String label;
  final int sort;
  final bool enabled;
  final String? displayNameEn;

  factory ImageEditorFilterCategory.fromJson(Map<String, Object?> json) {
    return ImageEditorFilterCategory(
      id: _requiredText(json, 'categoryId'),
      label: _requiredText(json, 'displayNameZhHans'),
      displayNameEn: _optionalText(json, 'displayNameEn'),
      sort: _requiredInt(json, 'sort'),
      enabled: _requiredBool(json, 'enabled'),
    );
  }

  Map<String, Object?> toJson() => <String, Object?>{
    'categoryId': id,
    'displayNameZhHans': label,
    'displayNameEn': displayNameEn,
    'sort': sort,
    'enabled': enabled,
  };
}

class ImageEditorFilterAdjustments {
  const ImageEditorFilterAdjustments({
    this.lightSense = 0,
    this.brightness = 0,
    this.exposure = 0,
    this.contrast = 0,
    this.saturation = 0,
    this.vibrance = 0,
    this.texture = 0,
    this.sharpen = 0,
    this.structure = 0,
    this.highlight = 0,
    this.shadow = 0,
    this.temperature = 0,
    this.tint = 0,
    this.grain = 0,
    this.fade = 0,
  });

  final double lightSense;
  final double brightness;
  final double exposure;
  final double contrast;
  final double saturation;
  final double vibrance;
  final double texture;
  final double sharpen;
  final double structure;
  final double highlight;
  final double shadow;
  final double temperature;
  final double tint;
  final double grain;
  final double fade;

  double operator [](String key) => switch (key) {
    'lightSense' => lightSense,
    'brightness' => brightness,
    'exposure' => exposure,
    'contrast' => contrast,
    'saturation' => saturation,
    'vibrance' => vibrance,
    'texture' => texture,
    'sharpen' => sharpen,
    'structure' => structure,
    'highlight' => highlight,
    'shadow' => shadow,
    'temperature' => temperature,
    'tint' => tint,
    'grain' => grain,
    'fade' => fade,
    _ => throw ArgumentError.value(key, 'key', 'unsupported filter adjustment'),
  };

  Iterable<MapEntry<String, double>> get entries sync* {
    yield MapEntry<String, double>('lightSense', lightSense);
    yield MapEntry<String, double>('brightness', brightness);
    yield MapEntry<String, double>('exposure', exposure);
    yield MapEntry<String, double>('contrast', contrast);
    yield MapEntry<String, double>('saturation', saturation);
    yield MapEntry<String, double>('vibrance', vibrance);
    yield MapEntry<String, double>('texture', texture);
    yield MapEntry<String, double>('sharpen', sharpen);
    yield MapEntry<String, double>('structure', structure);
    yield MapEntry<String, double>('highlight', highlight);
    yield MapEntry<String, double>('shadow', shadow);
    yield MapEntry<String, double>('temperature', temperature);
    yield MapEntry<String, double>('tint', tint);
    yield MapEntry<String, double>('grain', grain);
    yield MapEntry<String, double>('fade', fade);
  }

  Iterable<double> get values => entries.map((entry) => entry.value);

  bool get isIdentity => values.every((value) => value == 0);

  bool get isInRange => values.every((value) => value >= -100 && value <= 100);

  factory ImageEditorFilterAdjustments.fromJson(Map<String, Object?> json) {
    return ImageEditorFilterAdjustments(
      lightSense: _requiredDouble(json, 'lightSense'),
      brightness: _requiredDouble(json, 'brightness'),
      exposure: _requiredDouble(json, 'exposure'),
      contrast: _requiredDouble(json, 'contrast'),
      saturation: _requiredDouble(json, 'saturation'),
      vibrance: _requiredDouble(json, 'vibrance'),
      texture: _requiredDouble(json, 'texture'),
      sharpen: _requiredDouble(json, 'sharpen'),
      structure: _requiredDouble(json, 'structure'),
      highlight: _requiredDouble(json, 'highlight'),
      shadow: _requiredDouble(json, 'shadow'),
      temperature: _requiredDouble(json, 'temperature'),
      tint: _requiredDouble(json, 'tint'),
      grain: _requiredDouble(json, 'grain'),
      fade: _requiredDouble(json, 'fade'),
    );
  }

  Map<String, Object> toJson() => <String, Object>{
    for (final entry in entries) entry.key: _canonicalNumber(entry.value),
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
    required this.adjustments,
    this.displayNameEn,
  });

  final String id;
  final String categoryId;
  final String name;
  final int sort;
  final bool enabled;
  final double defaultStrength;
  final ImageEditorFilterAdjustments adjustments;
  final String? displayNameEn;

  factory ImageEditorFilterPreset.fromJson(Map<String, Object?> json) {
    return ImageEditorFilterPreset(
      id: _requiredText(json, 'presetId'),
      categoryId: _requiredText(json, 'categoryId'),
      name: _requiredText(json, 'displayNameZhHans'),
      displayNameEn: _optionalText(json, 'displayNameEn'),
      sort: _requiredInt(json, 'sort'),
      enabled: _requiredBool(json, 'enabled'),
      defaultStrength: _requiredDouble(json, 'defaultStrength'),
      adjustments: ImageEditorFilterAdjustments.fromJson(
        _requiredObject(json, 'adjustments'),
      ),
    );
  }

  Map<String, Object?> toJson() => <String, Object?>{
    'presetId': id,
    'categoryId': categoryId,
    'displayNameZhHans': name,
    'displayNameEn': displayNameEn,
    'sort': sort,
    'enabled': enabled,
    'defaultStrength': _canonicalNumber(defaultStrength),
    'adjustments': adjustments.toJson(),
  };
}

class ImageEditorFilterConfig {
  const ImageEditorFilterConfig({
    required this.releaseId,
    required this.canonicalDigest,
    required this.categories,
    required this.presets,
    required this.recommendedFallbackPresetIds,
  });

  final String releaseId;
  final String canonicalDigest;
  final List<ImageEditorFilterCategory> categories;
  final List<ImageEditorFilterPreset> presets;
  final List<String> recommendedFallbackPresetIds;

  factory ImageEditorFilterConfig.fromJson(Map<String, Object?> json) {
    return ImageEditorFilterConfig(
      releaseId: _requiredText(json, 'releaseId'),
      canonicalDigest: _requiredText(json, 'canonicalDigest').toLowerCase(),
      categories: _requiredList(json, 'categories')
          .map(
            (entry) => ImageEditorFilterCategory.fromJson(
              _requiredObjectValue(entry, 'category'),
            ),
          )
          .toList(growable: false),
      presets: _requiredList(json, 'presets')
          .map(
            (entry) => ImageEditorFilterPreset.fromJson(
              _requiredObjectValue(entry, 'preset'),
            ),
          )
          .toList(growable: false),
      recommendedFallbackPresetIds:
          _requiredList(json, 'recommendedFallbackPresetIds')
              .map((entry) {
                if (entry is! String || entry.trim().isEmpty) {
                  throw const FormatException(
                    'recommendedFallbackPresetIds contains invalid value',
                  );
                }
                return entry.trim();
              })
              .toList(growable: false),
    );
  }

  factory ImageEditorFilterConfig.fromJsonString(String source) {
    final decoded = jsonDecode(source);
    if (decoded is! Map) {
      throw const FormatException('filter catalog must be an object');
    }
    return ImageEditorFilterConfig.fromJson(decoded.cast<String, Object?>());
  }

  Map<String, Object> toJson() => <String, Object>{
    'releaseId': releaseId,
    'canonicalDigest': canonicalDigest,
    'categories': categories.map((entry) => entry.toJson()).toList(),
    'presets': presets.map((entry) => entry.toJson()).toList(),
    'recommendedFallbackPresetIds': recommendedFallbackPresetIds,
  };

  String toJsonString() => jsonEncode(toJson());

  bool isValid({required ImageEditorFilterDigestComputer computeDigest}) {
    if (!_isCanonicalText(releaseId) ||
        !_isCanonicalSha256(canonicalDigest) ||
        categories.isEmpty ||
        categories.length > 32 ||
        presets.isEmpty ||
        presets.length > 256) {
      return false;
    }
    final categoriesById = <String, ImageEditorFilterCategory>{};
    final categorySorts = <int>{};
    var hasEnabledCategory = false;
    for (final category in categories) {
      if (!_isCanonicalText(category.id) ||
          !_isCanonicalText(category.label) ||
          !_isOptionalCanonicalText(category.displayNameEn) ||
          categoriesById.containsKey(category.id) ||
          !categorySorts.add(category.sort)) {
        return false;
      }
      categoriesById[category.id] = category;
      hasEnabledCategory = hasEnabledCategory || category.enabled;
    }
    if (!hasEnabledCategory) return false;

    final presetsById = <String, ImageEditorFilterPreset>{};
    final sortsByCategory = <String, Set<int>>{};
    for (final preset in presets) {
      final category = categoriesById[preset.categoryId];
      if (!_isCanonicalText(preset.id) ||
          !_isCanonicalText(preset.categoryId) ||
          !_isCanonicalText(preset.name) ||
          !_isOptionalCanonicalText(preset.displayNameEn) ||
          category == null ||
          preset.enabled && !category.enabled ||
          presetsById.containsKey(preset.id) ||
          !preset.defaultStrength.isFinite ||
          preset.defaultStrength < 0 ||
          preset.defaultStrength > 100 ||
          !preset.adjustments.isInRange) {
        return false;
      }
      final categorySorts = sortsByCategory.putIfAbsent(
        preset.categoryId,
        () => <int>{},
      );
      if (!categorySorts.add(preset.sort)) return false;
      presetsById[preset.id] = preset;
    }
    final original = presetsById['original'];
    if (original == null ||
        !original.enabled ||
        original.defaultStrength != 0 ||
        !original.adjustments.isIdentity) {
      return false;
    }
    if (recommendedFallbackPresetIds.toSet().length !=
            recommendedFallbackPresetIds.length ||
        !recommendedFallbackPresetIds.every(
          (presetId) =>
              _isCanonicalText(presetId) &&
              (presetsById[presetId]?.enabled ?? false),
        )) {
      return false;
    }
    return canonicalDigest == computedCanonicalDigest(computeDigest);
  }

  String computedCanonicalDigest(
    ImageEditorFilterDigestComputer computeDigest,
  ) => _computeCanonicalDigest(computeDigest);

  String _computeCanonicalDigest(
    ImageEditorFilterDigestComputer computeDigest,
  ) {
    final sortedCategories = [...categories]
      ..sort((left, right) {
        final bySort = left.sort.compareTo(right.sort);
        return bySort != 0 ? bySort : left.id.compareTo(right.id);
      });
    final sortedPresets = [...presets]
      ..sort((left, right) {
        final byCategory = left.categoryId.compareTo(right.categoryId);
        if (byCategory != 0) return byCategory;
        final bySort = left.sort.compareTo(right.sort);
        return bySort != 0 ? bySort : left.id.compareTo(right.id);
      });
    final canonicalPayload = <String, Object>{
      'categories': sortedCategories.map((entry) => entry.toJson()).toList(),
      'presets': sortedPresets.map((entry) => entry.toJson()).toList(),
      'recommendedFallbackPresetIds': recommendedFallbackPresetIds,
    };
    return computeDigest(_canonicalJson(canonicalPayload));
  }
}

String _requiredText(Map<String, Object?> json, String key) {
  final value = json[key];
  if (value is! String || value.trim().isEmpty) {
    throw FormatException('$key must be a non-empty string');
  }
  return value.trim();
}

bool _isCanonicalText(String value) =>
    value.isNotEmpty && value.trim() == value;

bool _isOptionalCanonicalText(String? value) =>
    value == null || _isCanonicalText(value);

bool _isCanonicalSha256(String value) =>
    RegExp(r'^[0-9a-f]{64}$').hasMatch(value);

String? _optionalText(Map<String, Object?> json, String key) {
  final value = json[key];
  if (value == null) return null;
  if (value is! String) throw FormatException('$key must be a string or null');
  final normalized = value.trim();
  return normalized.isEmpty ? null : normalized;
}

int _requiredInt(Map<String, Object?> json, String key) {
  final value = json[key];
  if (value is! num || !value.isFinite || value.toInt() != value) {
    throw FormatException('$key must be an integer');
  }
  return value.toInt();
}

double _requiredDouble(Map<String, Object?> json, String key) {
  final value = json[key];
  if (value is! num || !value.isFinite) {
    throw FormatException('$key must be a finite number');
  }
  return value.toDouble();
}

bool _requiredBool(Map<String, Object?> json, String key) {
  final value = json[key];
  if (value is! bool) throw FormatException('$key must be a boolean');
  return value;
}

Map<String, Object?> _requiredObject(Map<String, Object?> json, String key) =>
    _requiredObjectValue(json[key], key);

Map<String, Object?> _requiredObjectValue(Object? value, String name) {
  if (value is! Map) throw FormatException('$name must be an object');
  return value.cast<String, Object?>();
}

List<Object?> _requiredList(Map<String, Object?> json, String key) {
  final value = json[key];
  if (value is! List) throw FormatException('$key must be a list');
  return value;
}

Object _canonicalNumber(double value) =>
    value.truncateToDouble() == value ? value.toInt() : value;

String _canonicalJson(Object? value) {
  if (value == null) return 'null';
  if (value is bool) return value ? 'true' : 'false';
  if (value is String) return jsonEncode(value);
  if (value is num) {
    if (!value.isFinite) {
      throw ArgumentError.value(value, 'value', 'must be finite');
    }
    if (value == 0) return '0';
    if (value is int || value.toInt() == value) return value.toInt().toString();
    return _canonicalFiniteDouble(value.toDouble());
  }
  if (value is List<Object?>) {
    return '[${value.map(_canonicalJson).join(',')}]';
  }
  if (value is Map<String, Object?>) {
    final entries = value.entries.toList()
      ..sort((left, right) => left.key.compareTo(right.key));
    return '{${entries.map((entry) {
      return '${jsonEncode(entry.key)}:${_canonicalJson(entry.value)}';
    }).join(',')}}';
  }
  throw ArgumentError.value(value, 'value', 'unsupported canonical JSON type');
}

String _canonicalFiniteDouble(double value) {
  final text = value.toString();
  final exponentIndex = text.indexOf(RegExp(r'[eE]'));
  if (exponentIndex == -1) return text;

  final coefficient = text.substring(0, exponentIndex);
  final exponent = int.parse(text.substring(exponentIndex + 1));
  final negative = coefficient.startsWith('-');
  final unsignedCoefficient = negative ? coefficient.substring(1) : coefficient;
  final parts = unsignedCoefficient.split('.');
  final integer = parts.first;
  final fraction = parts.length == 2 ? parts.last : '';
  final digits = integer + fraction;
  final decimalIndex = integer.length + exponent;
  final sign = negative ? '-' : '';
  if (decimalIndex <= 0) {
    return '${sign}0.${'0' * -decimalIndex}$digits';
  }
  if (decimalIndex >= digits.length) {
    return '$sign$digits${'0' * (decimalIndex - digits.length)}';
  }
  return '$sign${digits.substring(0, decimalIndex)}.${digits.substring(decimalIndex)}';
}
