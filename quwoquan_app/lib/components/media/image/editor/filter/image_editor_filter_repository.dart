import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;

import 'package:flutter/services.dart';
import 'package:path_provider/path_provider.dart';
import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_models.dart';
import 'package:shared_preferences/shared_preferences.dart';

class ImageEditorFilterRepository {
  static const String _assetPath = 'assets/filters/filter_presets.json';
  static const String _cacheFileName = 'filter_presets_cache.json';
  static const String _recentPresetIdsKey =
      'image_editor_recent_filter_preset_ids';
  static const String _usageCountMapKey = 'image_editor_filter_usage_count_map';
  static const int recentPresetMaxCount = 8;
  static const int _presetTargetCount = 220;

  Future<ImageEditorFilterConfig> loadConfig() async {
    final cached = await _readCachedConfig();
    if (cached != null && cached.isValid()) {
      return _expandPresetPool(cached, targetCount: _presetTargetCount);
    }
    final local = await _readBundledConfig();
    if (local != null && local.isValid()) {
      await saveConfigToCache(local);
      return _expandPresetPool(local, targetCount: _presetTargetCount);
    }
    // 兜底：返回最小可用结构，避免页面崩溃。
    return const ImageEditorFilterConfig(
      version: 1,
      categories: <ImageEditorFilterCategory>[],
      presets: <ImageEditorFilterPreset>[],
      recommendedFallbackPresetIds: <String>[],
    );
  }

  ImageEditorFilterConfig _expandPresetPool(
    ImageEditorFilterConfig config, {
    required int targetCount,
  }) {
    if (config.presets.length >= targetCount) return config;
    final source = config.presets
        .where((entry) => entry.enabled)
        .toList(growable: false);
    if (source.isEmpty) return config;
    final byCategory = <String, List<ImageEditorFilterPreset>>{};
    for (final preset in source) {
      byCategory
          .putIfAbsent(preset.categoryId, () => <ImageEditorFilterPreset>[])
          .add(preset);
    }
    for (final list in byCategory.values) {
      list.sort((a, b) => a.sort.compareTo(b.sort));
    }

    const variants = <_PresetVariant>[
      _PresetVariant(
        suffix: '·清透+',
        strengthDelta: 4,
        scales: <String, double>{
          'contrast': 1.08,
          'saturation': 1.08,
          'lightSense': 1.06,
          'highlight': 0.95,
        },
      ),
      _PresetVariant(
        suffix: '·柔和',
        strengthDelta: -6,
        scales: <String, double>{
          'contrast': 0.90,
          'fade': 1.18,
          'highlight': 0.90,
          'shadow': 1.10,
        },
      ),
      _PresetVariant(
        suffix: '·胶片感',
        strengthDelta: 0,
        scales: <String, double>{
          'grain': 1.28,
          'fade': 1.14,
          'temperature': 1.06,
          'contrast': 1.06,
        },
      ),
      _PresetVariant(
        suffix: '·明亮',
        strengthDelta: 3,
        scales: <String, double>{
          'brightness': 1.18,
          'exposure': 1.12,
          'highlight': 1.08,
          'shadow': 1.05,
        },
      ),
      _PresetVariant(
        suffix: '·氛围',
        strengthDelta: 2,
        scales: <String, double>{
          'vibrance': 1.15,
          'temperature': 1.06,
          'tint': 1.08,
          'contrast': 1.04,
        },
      ),
      _PresetVariant(
        suffix: '·质感',
        strengthDelta: 2,
        scales: <String, double>{
          'structure': 1.20,
          'texture': 1.16,
          'sharpen': 1.14,
          'contrast': 1.08,
        },
      ),
    ];

    final generated = <ImageEditorFilterPreset>[];
    final categoryIds = byCategory.keys.toList(growable: false);
    var categoryCursor = 0;
    var variantCursor = 0;
    var sourceCursor = 0;

    while (source.length + generated.length < targetCount &&
        categoryIds.isNotEmpty) {
      final categoryId = categoryIds[categoryCursor % categoryIds.length];
      final categoryPresets = byCategory[categoryId]!;
      if (categoryPresets.isEmpty) {
        categoryCursor++;
        continue;
      }
      final base = categoryPresets[sourceCursor % categoryPresets.length];
      final variant = variants[variantCursor % variants.length];
      final nextSort = base.sort + 1000 + generated.length;
      final generatedId = '${base.id}_g${generated.length + 1}';
      generated.add(
        ImageEditorFilterPreset(
          id: generatedId,
          categoryId: base.categoryId,
          name: '${base.name}${variant.suffix}',
          sort: nextSort,
          enabled: true,
          defaultStrength: (base.defaultStrength + variant.strengthDelta)
              .clamp(40, 100)
              .toDouble(),
          params: _applyVariant(base.params, variant.scales),
        ),
      );
      categoryCursor++;
      if (categoryCursor % categoryIds.length == 0) {
        sourceCursor++;
      }
      variantCursor++;
    }

    final mergedPresets = <ImageEditorFilterPreset>[
      ...config.presets,
      ...generated,
    ];
    return ImageEditorFilterConfig(
      version: config.version,
      categories: config.categories,
      presets: mergedPresets,
      recommendedFallbackPresetIds: config.recommendedFallbackPresetIds,
    );
  }

  Map<String, double> _applyVariant(
    Map<String, double> source,
    Map<String, double> scales,
  ) {
    final result = <String, double>{};
    for (final entry in source.entries) {
      final factor = scales[entry.key] ?? 1.0;
      result[entry.key] = (entry.value * factor)
          .clamp(-100.0, 100.0)
          .toDouble();
    }
    // 若某些关键参数不存在，按变体风格轻量补齐。
    for (final entry in scales.entries) {
      result.putIfAbsent(
        entry.key,
        () => (math.max(
          -100.0,
          math.min(100.0, (entry.value - 1.0) * 26),
        )).toDouble(),
      );
    }
    return result;
  }

  Future<void> saveConfigToCache(ImageEditorFilterConfig config) async {
    final file = await _resolveCacheFile();
    await file.writeAsString(config.toJsonString(), flush: true);
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
    } catch (_) {
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

  /// 存量位点：预留后续云端更新检查入口（本次不实现网络请求）。
  Future<void> scheduleUpdateCheckPlaceholder() async {
    // Intentionally no-op for current milestone.
  }

  Future<ImageEditorFilterConfig?> _readBundledConfig() async {
    try {
      final source = await rootBundle.loadString(_assetPath);
      return ImageEditorFilterConfig.fromJsonString(source);
    } catch (_) {
      return null;
    }
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

  Future<ImageEditorFilterConfig?> _readCachedConfig() async {
    try {
      final file = await _resolveCacheFile();
      if (!file.existsSync()) return null;
      final source = await file.readAsString();
      return ImageEditorFilterConfig.fromJsonString(source);
    } catch (_) {
      return null;
    }
  }

  Future<File> _resolveCacheFile() async {
    final dir = await getApplicationDocumentsDirectory();
    return File('${dir.path}/$_cacheFileName');
  }
}

class _PresetVariant {
  const _PresetVariant({
    required this.suffix,
    required this.strengthDelta,
    required this.scales,
  });

  final String suffix;
  final double strengthDelta;
  final Map<String, double> scales;
}
