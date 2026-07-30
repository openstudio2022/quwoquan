import '../operation_request_payload.dart';
part '../generated/requests/content/filter_catalog_facets.requests.g.dart';

enum FilterCatalogReleaseStatus { staged, active, retired }



final class FilterCatalogAdjustmentValues {
  const FilterCatalogAdjustmentValues({
    required this.lightSense,
    required this.brightness,
    required this.exposure,
    required this.contrast,
    required this.saturation,
    required this.vibrance,
    required this.texture,
    required this.sharpen,
    required this.structure,
    required this.highlight,
    required this.shadow,
    required this.temperature,
    required this.tint,
    required this.grain,
    required this.fade,
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

  bool get isIdentity =>
      lightSense == 0 &&
      brightness == 0 &&
      exposure == 0 &&
      contrast == 0 &&
      saturation == 0 &&
      vibrance == 0 &&
      texture == 0 &&
      sharpen == 0 &&
      structure == 0 &&
      highlight == 0 &&
      shadow == 0 &&
      temperature == 0 &&
      tint == 0 &&
      grain == 0 &&
      fade == 0;
}

final class FilterCatalogCategory {
  const FilterCatalogCategory({
    required this.categoryId,
    required this.displayNameZhHans,
    required this.displayNameEn,
    required this.sort,
    required this.enabled,
  });

  final String categoryId;
  final String displayNameZhHans;
  final String? displayNameEn;
  final int sort;
  final bool enabled;
}

final class FilterCatalogPreset {
  const FilterCatalogPreset({
    required this.presetId,
    required this.categoryId,
    required this.displayNameZhHans,
    required this.displayNameEn,
    required this.sort,
    required this.enabled,
    required this.defaultStrength,
    required this.adjustments,
  });

  final String presetId;
  final String categoryId;
  final String displayNameZhHans;
  final String? displayNameEn;
  final int sort;
  final bool enabled;
  final double defaultStrength;
  final FilterCatalogAdjustmentValues adjustments;
}

final class FilterCatalogSnapshot {
  const FilterCatalogSnapshot({
    required this.releaseId,
    required this.canonicalDigest,
    required this.status,
    required this.categoryCount,
    required this.presetCount,
    required this.categories,
    required this.presets,
    required this.recommendedFallbackPresetIds,
    required this.importedAt,
    required this.activatedAt,
  });

  final String releaseId;
  final String canonicalDigest;
  final FilterCatalogReleaseStatus status;
  final int categoryCount;
  final int presetCount;
  final List<FilterCatalogCategory> categories;
  final List<FilterCatalogPreset> presets;
  final List<String> recommendedFallbackPresetIds;
  final DateTime importedAt;
  final DateTime? activatedAt;
}

abstract interface class ContentFilterCatalogQuery {
  Future<FilterCatalogSnapshot> getActiveFilterCatalog();
}



FilterCatalogSnapshot decodeFilterCatalogSnapshot(Object? value) {
  final map = _object(value, 'FilterCatalogSnapshot');
  final statusValue = _string(map, 'status');
  final status = FilterCatalogReleaseStatus.values.firstWhere(
    (candidate) => candidate.name == statusValue,
    orElse: () => throw FormatException(
      'FilterCatalogSnapshot.status has unsupported value $statusValue',
    ),
  );
  return FilterCatalogSnapshot(
    releaseId: _string(map, 'releaseId'),
    canonicalDigest: _string(map, 'canonicalDigest'),
    status: status,
    categoryCount: _integer(map, 'categoryCount'),
    presetCount: _integer(map, 'presetCount'),
    categories: _list(map, 'categories')
        .map(
          (item) => _decodeCategory(
            _object(item, 'FilterCatalogCategory'),
          ),
        )
        .toList(growable: false),
    presets: _list(map, 'presets')
        .map(
          (item) => _decodePreset(
            _object(item, 'FilterCatalogPreset'),
          ),
        )
        .toList(growable: false),
    recommendedFallbackPresetIds: _list(
      map,
      'recommendedFallbackPresetIds',
    ).map((item) {
      if (item is! String || item.trim().isEmpty) {
        throw const FormatException(
          'recommendedFallbackPresetIds must contain non-empty strings',
        );
      }
      return item.trim();
    }).toList(growable: false),
    importedAt: _timestamp(map, 'importedAt'),
    activatedAt: _optionalTimestamp(map, 'activatedAt'),
  );
}

FilterCatalogCategory _decodeCategory(Map<String, Object?> map) {
  return FilterCatalogCategory(
    categoryId: _string(map, 'categoryId'),
    displayNameZhHans: _string(map, 'displayNameZhHans'),
    displayNameEn: _optionalString(map, 'displayNameEn'),
    sort: _integer(map, 'sort'),
    enabled: _boolean(map, 'enabled'),
  );
}

FilterCatalogPreset _decodePreset(Map<String, Object?> map) {
  return FilterCatalogPreset(
    presetId: _string(map, 'presetId'),
    categoryId: _string(map, 'categoryId'),
    displayNameZhHans: _string(map, 'displayNameZhHans'),
    displayNameEn: _optionalString(map, 'displayNameEn'),
    sort: _integer(map, 'sort'),
    enabled: _boolean(map, 'enabled'),
    defaultStrength: _number(map, 'defaultStrength'),
    adjustments: _decodeAdjustments(
      _object(map['adjustments'], 'FilterCatalogAdjustmentValues'),
    ),
  );
}

FilterCatalogAdjustmentValues _decodeAdjustments(Map<String, Object?> map) {
  return FilterCatalogAdjustmentValues(
    lightSense: _number(map, 'lightSense'),
    brightness: _number(map, 'brightness'),
    exposure: _number(map, 'exposure'),
    contrast: _number(map, 'contrast'),
    saturation: _number(map, 'saturation'),
    vibrance: _number(map, 'vibrance'),
    texture: _number(map, 'texture'),
    sharpen: _number(map, 'sharpen'),
    structure: _number(map, 'structure'),
    highlight: _number(map, 'highlight'),
    shadow: _number(map, 'shadow'),
    temperature: _number(map, 'temperature'),
    tint: _number(map, 'tint'),
    grain: _number(map, 'grain'),
    fade: _number(map, 'fade'),
  );
}

Map<String, Object?> _object(Object? value, String context) {
  if (value is! Map) {
    throw FormatException('$context must be an object');
  }
  return value.map(
    (key, fieldValue) => MapEntry(key.toString(), fieldValue),
  );
}

List<Object?> _list(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! List) {
    throw FormatException('$key must be an array');
  }
  return List<Object?>.unmodifiable(value);
}

String _string(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! String || value.trim().isEmpty) {
    throw FormatException('$key must be a non-empty string');
  }
  return value.trim();
}

String? _optionalString(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value == null) return null;
  if (value is! String) {
    throw FormatException('$key must be a string');
  }
  final normalized = value.trim();
  return normalized.isEmpty ? null : normalized;
}

int _integer(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! num || !value.isFinite || value != value.roundToDouble()) {
    throw FormatException('$key must be an integer');
  }
  return value.toInt();
}

double _number(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! num || !value.isFinite) {
    throw FormatException('$key must be a finite number');
  }
  return value.toDouble();
}

bool _boolean(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! bool) {
    throw FormatException('$key must be a boolean');
  }
  return value;
}

DateTime _timestamp(Map<String, Object?> map, String key) {
  final value = _string(map, key);
  final parsed = DateTime.tryParse(value);
  if (parsed == null) {
    throw FormatException('$key must be an ISO-8601 timestamp');
  }
  return parsed.toUtc();
}

DateTime? _optionalTimestamp(Map<String, Object?> map, String key) {
  final value = _optionalString(map, key);
  if (value == null) return null;
  final parsed = DateTime.tryParse(value);
  if (parsed == null) {
    throw FormatException('$key must be an ISO-8601 timestamp');
  }
  return parsed.toUtc();
}

