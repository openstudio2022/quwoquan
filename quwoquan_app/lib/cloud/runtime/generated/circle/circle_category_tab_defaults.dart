import 'circle_category_tab_config_dto.dart';

/// 与 Remote 仅返回部分槽位、或 [CircleCategoryTabsLoader] asset 加载失败时的 UI 回退。
abstract final class CircleCategoryTabDefaults {
  CircleCategoryTabDefaults._();

  static const Map<String, CircleCategoryTabConfigDto> remoteStyleFallback = {
    'campus': CircleCategoryTabConfigDto(
      label: '校园',
      subCategories: ['母校', '院系', '年级', '校友会', '职场互助'],
    ),
    'travel': CircleCategoryTabConfigDto(
      label: '旅行',
      subCategories: ['城市', '露营', '异域', '攻略', '徒步'],
    ),
    'photography': CircleCategoryTabConfigDto(
      label: '摄影',
      subCategories: ['风光', '人像', '街头', '器材', '后期'],
    ),
    'tech': CircleCategoryTabConfigDto(
      label: '科技',
      subCategories: ['数码', 'AI', '编程', '智能', '航天'],
    ),
    'car': CircleCategoryTabConfigDto(
      label: '车之家',
      subCategories: ['品牌', '车型', '自驾', '改装', '同城车会'],
    ),
  };
}
