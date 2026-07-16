import 'circle_category_tab_config_dto.dart';

/// 由 Circle UI metadata 投影的分类配置。
abstract final class CircleCategoryTabDefaults {
  CircleCategoryTabDefaults._();

  static const Map<String, CircleCategoryTabConfigDto> remoteStyleFallback = {
    'campus': CircleCategoryTabConfigDto(
      label: '校园',
      subCategories: ['母校', '院系', '年级', '校友会', '职场互助'],
      desc: '连接校友关系，从学号到职场终身互助',
    ),
    'travel': CircleCategoryTabConfigDto(
      label: '旅行',
      subCategories: ['城市', '露营', '异域', '攻略', '徒步'],
      desc: '看世界，见众生，在路上发现真我',
    ),
    'photography': CircleCategoryTabConfigDto(
      label: '摄影',
      subCategories: ['风光', '人像', '街头', '器材', '后期'],
      desc: '用影像记录世界，放大每一张好图的质感',
    ),
    'tech': CircleCategoryTabConfigDto(
      label: '科技',
      subCategories: ['数码', 'AI', '编程', '智能', '航天'],
      desc: '追踪前沿趋势，探索未来可能',
    ),
    'car': CircleCategoryTabConfigDto(
      label: '车之家',
      subCategories: ['品牌', '车型', '自驾', '改装', '同城车会'],
      desc: '发现同款生活方式，开启座驾新旅程',
    ),
  };
}
