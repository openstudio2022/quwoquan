/// 圈子发现页维度 Tab 配置（UI 投影）。
///
/// 数据源：[CircleCategoryTabsLoader] 从 `ui_category_tabs.yaml` asset 解析。
class CircleCategoryTabConfigDto {
  const CircleCategoryTabConfigDto({
    required this.label,
    this.subCategories = const [],
    this.desc,
  });

  final String label;
  final List<String> subCategories;
  final String? desc;
}
