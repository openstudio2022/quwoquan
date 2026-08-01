import 'dart:async';
import 'dart:convert';
import 'dart:developer' as developer;

import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_models.dart';
import 'package:shared_preferences/shared_preferences.dart';

typedef ImageEditorFilterCatalogLoader =
    Future<ImageEditorFilterConfig> Function();

class ImageEditorFilterRepository {
  ImageEditorFilterRepository({ImageEditorFilterCatalogLoader? catalogLoader})
    : _catalogLoader = catalogLoader ?? _missingCatalogLoader;

  static const String _recentPresetIdsKey =
      'image_editor_recent_filter_preset_ids';
  static const String _usageCountMapKey = 'image_editor_filter_usage_count_map';
  static const int recentPresetMaxCount = 8;
  static const String cameraPhotoCategoryId = 'camera_photo';

  final ImageEditorFilterCatalogLoader _catalogLoader;

  Future<ImageEditorFilterConfig> loadConfig() async {
    final config = await _catalogLoader();
    if (!config.isValid()) {
      throw StateError('filter catalog loader returned an unverified release');
    }
    return config;
  }

  Future<List<ImageEditorFilterPreset>> loadCameraPhotoPresets() async {
    final config = await loadConfig();
    final presets =
        config.presets
            .where(
              (preset) =>
                  preset.enabled && preset.categoryId == cameraPhotoCategoryId,
            )
            .toList(growable: false)
          ..sort((left, right) {
            final bySort = left.sort.compareTo(right.sort);
            return bySort != 0 ? bySort : left.id.compareTo(right.id);
          });
    return presets;
  }

  Future<List<String>> loadRecentPresetIds() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getStringList(_recentPresetIdsKey) ?? const <String>[];
    return raw
        .where((entry) => entry.trim().isNotEmpty)
        .toList(growable: false);
  }

  Future<void> saveRecentPresetUse(String presetId) async {
    if (presetId.trim().isEmpty) return;
    final prefs = await SharedPreferences.getInstance();
    final current = prefs.getStringList(_recentPresetIdsKey) ?? <String>[];
    final truncated = mergeRecentPresetIds(current, presetId);
    await prefs.setStringList(_recentPresetIdsKey, truncated);
  }

  Future<Map<String, int>> loadUsageCounts() async {
    final prefs = await SharedPreferences.getInstance();
    final source = prefs.getString(_usageCountMapKey);
    if (source == null || source.trim().isEmpty) {
      return const <String, int>{};
    }
    try {
      final raw = (json.decode(source) as Map).cast<String, dynamic>();
      return <String, int>{
        for (final entry in raw.entries)
          entry.key: (entry.value as num?)?.toInt() ?? 0,
      };
    } catch (error, stackTrace) {
      developer.log(
        'Invalid image editor filter usage cache',
        name: 'ImageEditorFilterRepository',
        error: error,
        stackTrace: stackTrace,
      );
      return const <String, int>{};
    }
  }

  Future<void> incrementUsageCount(String presetId) async {
    if (presetId.trim().isEmpty) return;
    final prefs = await SharedPreferences.getInstance();
    final current = Map<String, int>.from(await loadUsageCounts());
    current[presetId] = (current[presetId] ?? 0) + 1;
    await prefs.setString(_usageCountMapKey, json.encode(current));
  }

  Future<void> savePresetUseStats(String presetId) async {
    await saveRecentPresetUse(presetId);
    await incrementUsageCount(presetId);
  }

  static List<String> mergeRecentPresetIds(
    List<String> existing,
    String incoming, {
    int maxCount = recentPresetMaxCount,
  }) {
    final safeIncoming = incoming.trim();
    if (safeIncoming.isEmpty) {
      return existing
          .where((entry) => entry.trim().isNotEmpty)
          .take(maxCount)
          .toList(growable: false);
    }
    final deduped = <String>[
      safeIncoming,
      ...existing.where(
        (entry) => entry.trim().isNotEmpty && entry != safeIncoming,
      ),
    ];
    return deduped.take(maxCount).toList(growable: false);
  }
}

Future<ImageEditorFilterConfig> _missingCatalogLoader() {
  throw StateError(
    'ImageEditorFilterRepository requires a verified catalog loader',
  );
}
