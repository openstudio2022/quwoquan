import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_repository.dart';
import 'package:quwoquan_app/content/media/filter_catalog_release/adapters/image_editor_filter_models.dart';
import 'package:test/test.dart';

void main() {
  group('ImageEditorFilterRepository recent presets', () {
    test('deduplicates and keeps latest usage first', () async {
      final result = ImageEditorFilterRepository.mergeRecentPresetIds(
        const <String>['preset_b', 'preset_a'],
        'preset_a',
      );
      expect(result, equals(<String>['preset_a', 'preset_b']));
    });

    test('truncates list with max count limit', () async {
      var state = <String>[];
      for (var i = 0; i < 20; i++) {
        state = ImageEditorFilterRepository.mergeRecentPresetIds(
          state,
          'preset_$i',
        );
      }
      expect(state.length, lessThanOrEqualTo(8));
      expect(state.first, equals('preset_19'));
    });

    test('camera presets follow the active catalog category and sort', () async {
      final repository = ImageEditorFilterRepository(
        catalogLoader: () async => _cameraCatalogWithNewPreset(),
      );

      final presets = await repository.loadCameraPhotoPresets();

      expect(
        presets.map((preset) => preset.id),
        equals(<String>['original', 'portrait', 'new-release-preset']),
      );
    });
  });
}

ImageEditorFilterConfig _cameraCatalogWithNewPreset() {
  const categories = <ImageEditorFilterCategory>[
    ImageEditorFilterCategory(
      id: ImageEditorFilterRepository.cameraPhotoCategoryId,
      label: '相机',
      sort: 1,
      enabled: true,
    ),
  ];
  const presets = <ImageEditorFilterPreset>[
    ImageEditorFilterPreset(
      id: 'original',
      categoryId: ImageEditorFilterRepository.cameraPhotoCategoryId,
      name: '原图',
      sort: 1,
      enabled: true,
      defaultStrength: 0,
      adjustments: ImageEditorFilterAdjustments(),
    ),
    ImageEditorFilterPreset(
      id: 'portrait',
      categoryId: ImageEditorFilterRepository.cameraPhotoCategoryId,
      name: '人像',
      sort: 2,
      enabled: true,
      defaultStrength: 50,
      adjustments: ImageEditorFilterAdjustments(),
    ),
    ImageEditorFilterPreset(
      id: 'new-release-preset',
      categoryId: ImageEditorFilterRepository.cameraPhotoCategoryId,
      name: '新发布滤镜',
      sort: 3,
      enabled: true,
      defaultStrength: 60,
      adjustments: ImageEditorFilterAdjustments(),
    ),
    ImageEditorFilterPreset(
      id: 'disabled',
      categoryId: ImageEditorFilterRepository.cameraPhotoCategoryId,
      name: '已停用',
      sort: 4,
      enabled: false,
      defaultStrength: 0,
      adjustments: ImageEditorFilterAdjustments(),
    ),
  ];
  const releaseId = 'test-filter-release';
  const recommendedFallbackPresetIds = <String>['original'];
  final unsigned = ImageEditorFilterConfig(
    releaseId: releaseId,
    canonicalDigest: '',
    categories: categories,
    presets: presets,
    recommendedFallbackPresetIds: recommendedFallbackPresetIds,
  );
  return ImageEditorFilterConfig(
    releaseId: releaseId,
    canonicalDigest: unsigned.computedCanonicalDigest,
    categories: categories,
    presets: presets,
    recommendedFallbackPresetIds: recommendedFallbackPresetIds,
  );
}
