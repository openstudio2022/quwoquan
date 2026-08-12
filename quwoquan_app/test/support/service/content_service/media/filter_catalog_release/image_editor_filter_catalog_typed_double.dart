import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/adapters/verified_filter_catalog_store.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/application/public/image_editor_filter_catalog.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/application/public/image_editor_filter_models.dart';

import 'filter_catalog_query_typed_double.dart';

/// 图片编辑器滤镜读面的对象级 in-memory typed double。
///
/// 只实现 [ImageEditorFilterCatalog] 这一个 port：目录内容直接来自 canonical
/// FilterCatalogRelease（经 [InMemoryFilterCatalogQuery]），不自造第二套滤镜数据；
/// 最近使用与使用次数是纯本地偏好，测试期用内存 map 承载，避免依赖 SharedPreferences。
final class InMemoryImageEditorFilterCatalog
    implements ImageEditorFilterCatalog {
  InMemoryImageEditorFilterCatalog({InMemoryFilterCatalogQuery? query})
    : _query = query ?? InMemoryFilterCatalogQuery();

  static const String _cameraPhotoCategoryId = 'camera_photo';

  final InMemoryFilterCatalogQuery _query;
  final List<String> _recentPresetIds = <String>[];
  final Map<String, int> _usageCounts = <String, int>{};

  ImageEditorFilterConfig? _cachedConfig;

  @override
  Future<ImageEditorFilterConfig> loadConfig() async {
    return _cachedConfig ??= imageEditorFilterConfigFromSnapshot(
      await _query.getActiveFilterCatalog(),
    );
  }

  @override
  Future<List<ImageEditorFilterPreset>> loadCameraPhotoPresets() async {
    final config = await loadConfig();
    return config.presets
        .where(
          (preset) =>
              preset.enabled && preset.categoryId == _cameraPhotoCategoryId,
        )
        .toList(growable: false)
      ..sort((left, right) {
        final bySort = left.sort.compareTo(right.sort);
        return bySort != 0 ? bySort : left.id.compareTo(right.id);
      });
  }

  @override
  Future<List<String>> loadRecentPresetIds() async =>
      List<String>.unmodifiable(_recentPresetIds);

  @override
  Future<Map<String, int>> loadUsageCounts() async =>
      Map<String, int>.unmodifiable(_usageCounts);

  @override
  Future<void> savePresetUseStats(String presetId) async {
    _recentPresetIds
      ..remove(presetId)
      ..insert(0, presetId);
    _usageCounts[presetId] = (_usageCounts[presetId] ?? 0) + 1;
  }
}
