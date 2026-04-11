import 'circle_category_tab_config_dto.dart';

/// 与 Remote 仅返回 `all` 槽位、或 [CircleCategoryTabsLoader] asset 加载失败时的 UI 回退。
abstract final class CircleCategoryTabDefaults {
  CircleCategoryTabDefaults._();

  static const Map<String, CircleCategoryTabConfigDto> remoteStyleFallback = {
    'all': CircleCategoryTabConfigDto(label: '推荐'),
  };
}
