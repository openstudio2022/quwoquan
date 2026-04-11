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

  factory CircleCategoryTabConfigDto.fromMap(Map<String, dynamic> m) {
    final subs = (m['subCategories'] as List?)
        ?.map((e) => e.toString())
        .toList(growable: false);
    return CircleCategoryTabConfigDto(
      label: (m['label'] ?? '').toString(),
      subCategories: subs ?? const [],
      desc: m['desc']?.toString(),
    );
  }

  Map<String, dynamic> toMap() => {
        'label': label,
        'subCategories': subCategories,
        if (desc != null) 'desc': desc,
      };
}
