import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:quwoquan_app/application/content/filter_catalog/filter_catalog_coordinator.dart';
import 'package:quwoquan_app/content/media/filter_catalog_release/adapters/image_editor_filter_models.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:shared_preferences/shared_preferences.dart';

final class SharedPreferencesVerifiedFilterCatalogStore
    implements VerifiedFilterCatalogStore {
  const SharedPreferencesVerifiedFilterCatalogStore();

  static const String _catalogKey = 'verified_filter_catalog_release';

  @override
  Future<VerifiedFilterCatalogCacheEntry?> read() async {
    final preferences = await SharedPreferences.getInstance();
    final source = preferences.getString(_catalogKey);
    if (source == null || source.trim().isEmpty) return null;
    final decoded = jsonDecode(source);
    if (decoded is! Map) {
      throw const FormatException(
        'verified filter catalog cache is not an object',
      );
    }
    final payload = decoded.map(
      (key, value) => MapEntry(key.toString(), value),
    );
    final verifiedAtValue = payload['verifiedAt'];
    if (verifiedAtValue is! String || verifiedAtValue.trim().isEmpty) {
      throw const FormatException(
        'verified filter catalog cache has no verifiedAt timestamp',
      );
    }
    final verifiedAt = DateTime.tryParse(verifiedAtValue);
    if (verifiedAt == null) {
      throw const FormatException(
        'verified filter catalog cache has an invalid verifiedAt timestamp',
      );
    }
    final snapshotPayload = Map<String, Object?>.from(payload)
      ..remove('verifiedAt');
    return VerifiedFilterCatalogCacheEntry(
      snapshot: FilterCatalogSlice.fromWire(
        snapshotPayload,
        'VerifiedFilterCatalogCacheEntry.snapshot',
      ),
      verifiedAt: verifiedAt.toUtc(),
    );
  }

  @override
  Future<void> write(FilterCatalogSlice snapshot) async {
    if (!imageEditorFilterConfigFromSnapshot(snapshot).isValid()) {
      throw ArgumentError.value(snapshot, 'snapshot', 'must be verified');
    }
    final preferences = await SharedPreferences.getInstance();
    final payload = _snapshotToJson(snapshot)
      ..['verifiedAt'] = DateTime.now().toUtc().toIso8601String();
    final committed = await preferences.setString(
      _catalogKey,
      jsonEncode(payload),
    );
    if (!committed) {
      throw StateError('verified filter catalog cache commit failed');
    }
  }

  @override
  Future<void> clear() async {
    final preferences = await SharedPreferences.getInstance();
    final removed = await preferences.remove(_catalogKey);
    if (!removed && preferences.containsKey(_catalogKey)) {
      throw StateError('verified filter catalog cache clear failed');
    }
  }
}

final class AssetFilterCatalogBootstrapReader
    implements FilterCatalogBootstrapReader {
  const AssetFilterCatalogBootstrapReader({
    this.assetPath = 'assets/filters/filter_presets.json',
  });

  final String assetPath;

  @override
  Future<FilterCatalogSlice> read() async {
    final source = await rootBundle.loadString(assetPath);
    final catalog = ImageEditorFilterConfig.fromJsonString(source);
    if (!catalog.isValid()) {
      throw const FormatException('invalid bundled filter catalog');
    }
    return FilterCatalogSlice(
      releaseId: catalog.releaseId,
      canonicalDigest: catalog.canonicalDigest,
      status: FilterCatalogReleaseStatus.active,
      categoryCount: catalog.categories.length,
      presetCount: catalog.presets.length,
      categories: catalog.categories
          .map(
            (category) => FilterCategoryDefinition(
              categoryId: category.id,
              displayNameZhHans: category.label,
              displayNameEn: category.displayNameEn,
              sort: category.sort,
              enabled: category.enabled,
            ),
          )
          .toList(growable: false),
      presets: catalog.presets
          .map(
            (preset) => FilterPresetDefinition(
              presetId: preset.id,
              categoryId: preset.categoryId,
              displayNameZhHans: preset.name,
              displayNameEn: preset.displayNameEn,
              sort: preset.sort,
              enabled: preset.enabled,
              defaultStrength: preset.defaultStrength,
              adjustments: _toContractAdjustments(preset.adjustments),
            ),
          )
          .toList(growable: false),
      recommendedFallbackPresetIds: catalog.recommendedFallbackPresetIds,
      importedAt: DateTime.fromMillisecondsSinceEpoch(0, isUtc: true),
      activatedAt: null,
    );
  }
}

final class CanonicalFilterCatalogIntegrityVerifier
    implements FilterCatalogIntegrityVerifier {
  const CanonicalFilterCatalogIntegrityVerifier();

  @override
  bool hasValidCanonicalDigest(FilterCatalogSlice snapshot) {
    return imageEditorFilterConfigFromSnapshot(snapshot).isValid();
  }
}

ImageEditorFilterConfig imageEditorFilterConfigFromSnapshot(
  FilterCatalogSlice snapshot,
) {
  return ImageEditorFilterConfig(
    releaseId: snapshot.releaseId,
    canonicalDigest: snapshot.canonicalDigest,
    categories: snapshot.categories
        .map(
          (category) => ImageEditorFilterCategory(
            id: category.categoryId,
            label: category.displayNameZhHans,
            displayNameEn: category.displayNameEn,
            sort: category.sort,
            enabled: category.enabled,
          ),
        )
        .toList(growable: false),
    presets: snapshot.presets
        .map(
          (preset) => ImageEditorFilterPreset(
            id: preset.presetId,
            categoryId: preset.categoryId,
            name: preset.displayNameZhHans,
            displayNameEn: preset.displayNameEn,
            sort: preset.sort,
            enabled: preset.enabled,
            defaultStrength: preset.defaultStrength,
            adjustments: _toEditorAdjustments(preset.adjustments),
          ),
        )
        .toList(growable: false),
    recommendedFallbackPresetIds: snapshot.recommendedFallbackPresetIds,
  );
}

Map<String, Object?> _snapshotToJson(FilterCatalogSlice snapshot) {
  return <String, Object?>{
    'releaseId': snapshot.releaseId,
    'canonicalDigest': snapshot.canonicalDigest,
    'status': snapshot.status.name,
    'categoryCount': snapshot.categoryCount,
    'presetCount': snapshot.presetCount,
    'categories': snapshot.categories
        .map(
          (category) => <String, Object?>{
            'categoryId': category.categoryId,
            'displayNameZhHans': category.displayNameZhHans,
            'displayNameEn': category.displayNameEn,
            'sort': category.sort,
            'enabled': category.enabled,
          },
        )
        .toList(growable: false),
    'presets': snapshot.presets
        .map(
          (preset) => <String, Object?>{
            'presetId': preset.presetId,
            'categoryId': preset.categoryId,
            'displayNameZhHans': preset.displayNameZhHans,
            'displayNameEn': preset.displayNameEn,
            'sort': preset.sort,
            'enabled': preset.enabled,
            'defaultStrength': preset.defaultStrength,
            'adjustments': _contractAdjustmentsToJson(preset.adjustments),
          },
        )
        .toList(growable: false),
    'recommendedFallbackPresetIds': snapshot.recommendedFallbackPresetIds,
    'importedAt': snapshot.importedAt.toUtc().toIso8601String(),
    'activatedAt': snapshot.activatedAt?.toUtc().toIso8601String(),
  };
}

Map<String, double> _contractAdjustmentsToJson(
  FilterAdjustmentValues adjustments,
) {
  return <String, double>{
    'lightSense': adjustments.lightSense,
    'brightness': adjustments.brightness,
    'exposure': adjustments.exposure,
    'contrast': adjustments.contrast,
    'saturation': adjustments.saturation,
    'vibrance': adjustments.vibrance,
    'texture': adjustments.texture,
    'sharpen': adjustments.sharpen,
    'structure': adjustments.structure,
    'highlight': adjustments.highlight,
    'shadow': adjustments.shadow,
    'temperature': adjustments.temperature,
    'tint': adjustments.tint,
    'grain': adjustments.grain,
    'fade': adjustments.fade,
  };
}

FilterAdjustmentValues _toContractAdjustments(
  ImageEditorFilterAdjustments adjustments,
) {
  return FilterAdjustmentValues(
    lightSense: adjustments.lightSense,
    brightness: adjustments.brightness,
    exposure: adjustments.exposure,
    contrast: adjustments.contrast,
    saturation: adjustments.saturation,
    vibrance: adjustments.vibrance,
    texture: adjustments.texture,
    sharpen: adjustments.sharpen,
    structure: adjustments.structure,
    highlight: adjustments.highlight,
    shadow: adjustments.shadow,
    temperature: adjustments.temperature,
    tint: adjustments.tint,
    grain: adjustments.grain,
    fade: adjustments.fade,
  );
}

ImageEditorFilterAdjustments _toEditorAdjustments(
  FilterAdjustmentValues adjustments,
) {
  return ImageEditorFilterAdjustments(
    lightSense: adjustments.lightSense,
    brightness: adjustments.brightness,
    exposure: adjustments.exposure,
    contrast: adjustments.contrast,
    saturation: adjustments.saturation,
    vibrance: adjustments.vibrance,
    texture: adjustments.texture,
    sharpen: adjustments.sharpen,
    structure: adjustments.structure,
    highlight: adjustments.highlight,
    shadow: adjustments.shadow,
    temperature: adjustments.temperature,
    tint: adjustments.tint,
    grain: adjustments.grain,
    fade: adjustments.fade,
  );
}
