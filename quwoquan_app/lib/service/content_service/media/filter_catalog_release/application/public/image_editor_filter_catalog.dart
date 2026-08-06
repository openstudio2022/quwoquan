import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/application/public/image_editor_filter_models.dart';

/// Public application seam for the verified image-editor filter catalog.
///
/// Presentation consumers may load typed catalog state and record local usage,
/// while persistence and generated-client details remain behind the concrete
/// adapter installed by `runtime/di`.
abstract interface class ImageEditorFilterCatalog {
  Future<ImageEditorFilterConfig> loadConfig();

  Future<List<ImageEditorFilterPreset>> loadCameraPhotoPresets();

  Future<List<String>> loadRecentPresetIds();

  Future<Map<String, int>> loadUsageCounts();

  Future<void> savePresetUseStats(String presetId);
}
