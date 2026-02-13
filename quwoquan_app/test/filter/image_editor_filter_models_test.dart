// ignore_for_file: depend_on_referenced_packages

import 'dart:convert';
import 'dart:io';

import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_models.dart';
import 'package:test/test.dart';

void main() {
  group('ImageEditorFilterConfig', () {
    late ImageEditorFilterConfig config;

    setUpAll(() {
      final source = File('assets/filters/filter_presets.json').readAsStringSync();
      config = ImageEditorFilterConfig.fromJson(
        json.decode(source) as Map<String, dynamic>,
      );
    });

    test('loads local config and passes validation', () {
      expect(config.isValid(), isTrue);
      expect(config.categories, isNotEmpty);
      expect(config.presets, isNotEmpty);
    });

    test('contains recommended category and all consumer categories', () {
      final categoryIds = config.categories.map((entry) => entry.id).toSet();
      expect(categoryIds.contains('recommended'), isTrue);
      expect(categoryIds.length, greaterThanOrEqualTo(19));
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
  });
}
