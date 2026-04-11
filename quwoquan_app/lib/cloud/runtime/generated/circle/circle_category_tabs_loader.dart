import 'package:flutter/services.dart';
import 'package:yaml/yaml.dart';

import 'circle_category_tab_config_dto.dart';
import 'circle_category_tab_defaults.dart';

/// 从 [assetPath] 加载 `ui_category_tabs.yaml`，与 contracts 单一真源对齐。
abstract final class CircleCategoryTabsLoader {
  CircleCategoryTabsLoader._();

  /// 与 [pubspec.yaml] 中声明的 asset 路径一致（相对 `quwoquan_app/pubspec.yaml`）。
  static const String assetPath =
      '../quwoquan_service/contracts/metadata/social/circle/ui_category_tabs.yaml';

  static Future<Map<String, CircleCategoryTabConfigDto>> loadFromAsset() async {
    try {
      final yamlText = await rootBundle.loadString(assetPath);
      return parseFromYamlString(yamlText);
    } catch (_) {
      return Map<String, CircleCategoryTabConfigDto>.from(
        CircleCategoryTabDefaults.remoteStyleFallback,
      );
    }
  }

  static Map<String, CircleCategoryTabConfigDto> parseFromYamlString(
    String yamlText,
  ) {
    final dynamic doc = loadYaml(yamlText);
    if (doc is! YamlMap) {
      return Map<String, CircleCategoryTabConfigDto>.from(
        CircleCategoryTabDefaults.remoteStyleFallback,
      );
    }
    final tabs = doc['tabs'];
    if (tabs is! YamlList) {
      return Map<String, CircleCategoryTabConfigDto>.from(
        CircleCategoryTabDefaults.remoteStyleFallback,
      );
    }
    final out = <String, CircleCategoryTabConfigDto>{};
    for (final raw in tabs) {
      if (raw is! YamlMap) continue;
      final id = raw['id']?.toString();
      if (id == null || id.isEmpty) continue;
      final subs = raw['subCategories'];
      List<dynamic>? subList;
      if (subs is YamlList) {
        subList = subs;
      } else if (subs is List) {
        subList = subs;
      }
      out[id] = CircleCategoryTabConfigDto.fromMap(<String, dynamic>{
        'label': raw['label']?.toString() ?? '',
        'subCategories': subList,
        'desc': raw['desc']?.toString(),
      });
    }
    if (out.isEmpty) {
      return Map<String, CircleCategoryTabConfigDto>.from(
        CircleCategoryTabDefaults.remoteStyleFallback,
      );
    }
    return out;
  }
}
