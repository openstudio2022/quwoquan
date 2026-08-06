import 'circle_category_tab_config_dto.dart';
import 'circle_category_tab_defaults.dart';

typedef CircleCategoryTabEntry = MapEntry<String, CircleCategoryTabConfigDto>;

List<CircleCategoryTabEntry> resolveCircleCategoryTabEntries(
  Map<String, CircleCategoryTabConfigDto> config,
) {
  final merged = <String, CircleCategoryTabConfigDto>{
    ...CircleCategoryTabDefaults.remoteStyleFallback,
    ...config,
  };
  return merged.entries.toList(growable: false);
}
