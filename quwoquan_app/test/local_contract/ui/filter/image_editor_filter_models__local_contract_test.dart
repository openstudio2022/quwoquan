// ignore_for_file: depend_on_referenced_packages

import 'dart:convert';
import 'dart:io';

import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_models.dart';
import 'package:test/test.dart';

void main() {
  group('ImageEditorFilterConfig', () {
    late ImageEditorFilterConfig config;

    setUpAll(() {
      final source = File(
        'assets/filters/filter_presets.json',
      ).readAsStringSync();
      config = ImageEditorFilterConfig.fromJson(
        json.decode(source) as Map<String, dynamic>,
      );
    });

    test('loads local config and passes validation', () {
      expect(config.isValid(), isTrue);
      expect(config.categories, isNotEmpty);
      expect(config.presets, isNotEmpty);
    });

    test('contains bundled consumer categories', () {
      final categoryIds = config.categories.map((entry) => entry.id).toSet();
      expect(categoryIds.contains('recommended'), isFalse);
      expect(categoryIds.contains('common'), isFalse);
      expect(categoryIds.length, greaterThanOrEqualTo(9));
    });

    test('each non-recommended category has at least three presets', () {
      final grouped = <String, int>{};
      for (final preset in config.presets) {
        grouped[preset.categoryId] = (grouped[preset.categoryId] ?? 0) + 1;
      }
      for (final category in config.categories) {
        if (category.id == 'recommended' || !category.enabled) continue;
        expect(
          grouped[category.id] ?? 0,
          greaterThanOrEqualTo(3),
          reason: 'Category ${category.id} should have >=3 presets',
        );
      }
    });

    test('recommended fallback preset ids exist in presets', () {
      final presetIds = config.presets.map((entry) => entry.id).toSet();
      for (final id in config.recommendedFallbackPresetIds) {
        expect(presetIds.contains(id), isTrue, reason: 'Missing preset: $id');
      }
    });

    test('rejects duplicate category and preset display ordering', () {
      final categoriesWithDuplicateSort = [...config.categories];
      categoriesWithDuplicateSort[1] = _copyCategory(
        categoriesWithDuplicateSort[1],
        sort: categoriesWithDuplicateSort.first.sort,
      );
      expect(
        _rehash(config, categories: categoriesWithDuplicateSort).isValid(),
        isFalse,
      );

      final firstPreset = config.presets.first;
      final sameCategoryPreset = config.presets.firstWhere(
        (preset) =>
            preset.categoryId == firstPreset.categoryId &&
            preset.id != firstPreset.id,
      );
      final presetsWithDuplicateSort = [...config.presets];
      final targetIndex = presetsWithDuplicateSort.indexWhere(
        (preset) => preset.id == sameCategoryPreset.id,
      );
      presetsWithDuplicateSort[targetIndex] = _copyPreset(
        sameCategoryPreset,
        sort: firstPreset.sort,
      );
      expect(
        _rehash(config, presets: presetsWithDuplicateSort).isValid(),
        isFalse,
      );
    });

    test('rejects hidden disabled catalog invariant violations', () {
      final firstCategory = config.categories.first;
      final secondCategory = config.categories[1];
      final categoriesWithDuplicateId = [...config.categories];
      categoriesWithDuplicateId[1] = _copyCategory(
        secondCategory,
        id: firstCategory.id,
        enabled: false,
      );
      final rewiredPresets = config.presets
          .map(
            (preset) => preset.categoryId == secondCategory.id
                ? _copyPreset(preset, categoryId: firstCategory.id)
                : preset,
          )
          .toList(growable: false);
      expect(
        _rehash(
          config,
          categories: categoriesWithDuplicateId,
          presets: rewiredPresets,
        ).isValid(),
        isFalse,
      );

      final disabledUnknownPreset = _copyPreset(
        config.presets.firstWhere((preset) => preset.id != 'original'),
        id: 'disabled-unknown-category',
        categoryId: 'unknown-category',
        enabled: false,
      );
      expect(
        _rehash(
          config,
          presets: [...config.presets, disabledUnknownPreset],
        ).isValid(),
        isFalse,
      );
    });

    test('requires an enabled original and enabled fallback presets', () {
      final originalIndex = config.presets.indexWhere(
        (preset) => preset.id == 'original',
      );
      final disabledOriginal = [...config.presets];
      disabledOriginal[originalIndex] = _copyPreset(
        disabledOriginal[originalIndex],
        enabled: false,
      );
      expect(_rehash(config, presets: disabledOriginal).isValid(), isFalse);

      final fallbackId = config.recommendedFallbackPresetIds.first;
      final fallbackIndex = config.presets.indexWhere(
        (preset) => preset.id == fallbackId,
      );
      final disabledFallback = [...config.presets];
      disabledFallback[fallbackIndex] = _copyPreset(
        disabledFallback[fallbackIndex],
        enabled: false,
      );
      expect(_rehash(config, presets: disabledFallback).isValid(), isFalse);
    });

    test('matches the cross-language decimal boundary digest vector', () {
      final boundaryConfig = _decimalBoundaryVectorConfig();

      expect(
        boundaryConfig.computedCanonicalDigest,
        'fba38ede15295f3bbee31375d9955edc0baf722b8c204dbf0575f4ab25401242',
      );
      expect(boundaryConfig.isValid(), isTrue);
    });
  });
}

ImageEditorFilterConfig _decimalBoundaryVectorConfig() {
  const categories = <ImageEditorFilterCategory>[
    ImageEditorFilterCategory(
      id: 'camera_photo',
      label: '拍照',
      sort: 1,
      enabled: true,
    ),
  ];
  const presets = <ImageEditorFilterPreset>[
    ImageEditorFilterPreset(
      id: 'original',
      categoryId: 'camera_photo',
      name: '原图',
      sort: 1,
      enabled: true,
      defaultStrength: 0,
      adjustments: ImageEditorFilterAdjustments(),
    ),
    ImageEditorFilterPreset(
      id: 'cinema',
      categoryId: 'camera_photo',
      name: '电影',
      displayNameEn: 'Cinema',
      sort: 2,
      enabled: true,
      defaultStrength: 80.5,
      adjustments: ImageEditorFilterAdjustments(
        contrast: 8.25,
        temperature: -12.5,
        grain: 1e-7,
        fade: -0.0,
      ),
    ),
  ];
  final draft = ImageEditorFilterConfig(
    releaseId: 'filter-catalog-decimal-boundary',
    canonicalDigest: '0' * 64,
    categories: categories,
    presets: presets,
    recommendedFallbackPresetIds: const <String>['cinema'],
  );
  return ImageEditorFilterConfig(
    releaseId: draft.releaseId,
    canonicalDigest: draft.computedCanonicalDigest,
    categories: categories,
    presets: presets,
    recommendedFallbackPresetIds: draft.recommendedFallbackPresetIds,
  );
}

ImageEditorFilterConfig _rehash(
  ImageEditorFilterConfig source, {
  List<ImageEditorFilterCategory>? categories,
  List<ImageEditorFilterPreset>? presets,
  List<String>? recommendedFallbackPresetIds,
}) {
  final draft = ImageEditorFilterConfig(
    releaseId: source.releaseId,
    canonicalDigest: '0' * 64,
    categories: categories ?? source.categories,
    presets: presets ?? source.presets,
    recommendedFallbackPresetIds:
        recommendedFallbackPresetIds ?? source.recommendedFallbackPresetIds,
  );
  return ImageEditorFilterConfig(
    releaseId: draft.releaseId,
    canonicalDigest: draft.computedCanonicalDigest,
    categories: draft.categories,
    presets: draft.presets,
    recommendedFallbackPresetIds: draft.recommendedFallbackPresetIds,
  );
}

ImageEditorFilterCategory _copyCategory(
  ImageEditorFilterCategory source, {
  String? id,
  int? sort,
  bool? enabled,
}) {
  return ImageEditorFilterCategory(
    id: id ?? source.id,
    label: source.label,
    displayNameEn: source.displayNameEn,
    sort: sort ?? source.sort,
    enabled: enabled ?? source.enabled,
  );
}

ImageEditorFilterPreset _copyPreset(
  ImageEditorFilterPreset source, {
  String? id,
  String? categoryId,
  int? sort,
  bool? enabled,
}) {
  return ImageEditorFilterPreset(
    id: id ?? source.id,
    categoryId: categoryId ?? source.categoryId,
    name: source.name,
    displayNameEn: source.displayNameEn,
    sort: sort ?? source.sort,
    enabled: enabled ?? source.enabled,
    defaultStrength: source.defaultStrength,
    adjustments: source.adjustments,
  );
}
