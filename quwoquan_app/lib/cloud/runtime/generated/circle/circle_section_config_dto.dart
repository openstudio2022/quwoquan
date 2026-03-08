/// 圈子主页板块配置项（嵌入文档）。
///
/// 字段对齐：contracts/metadata/social/circle/fields.yaml CircleSectionConfig
class CircleSectionConfigDto {
  final String sectionType;
  final bool visible;
  final int order;
  final String? customTitle;

  const CircleSectionConfigDto({
    required this.sectionType,
    this.visible = true,
    this.order = 0,
    this.customTitle,
  });

  factory CircleSectionConfigDto.fromMap(Map<String, dynamic> m) {
    return CircleSectionConfigDto(
      sectionType: (m['sectionType'] ?? 'works').toString(),
      visible: m['visible'] as bool? ?? true,
      order: (m['order'] as num?)?.toInt() ?? 0,
      customTitle: m['customTitle'] as String?,
    );
  }

  Map<String, dynamic> toMap() => {
        'sectionType': sectionType,
        'visible': visible,
        'order': order,
        if (customTitle != null) 'customTitle': customTitle,
      };

  CircleSectionConfigDto copyWith({
    String? sectionType,
    bool? visible,
    int? order,
    String? customTitle,
  }) {
    return CircleSectionConfigDto(
      sectionType: sectionType ?? this.sectionType,
      visible: visible ?? this.visible,
      order: order ?? this.order,
      customTitle: customTitle ?? this.customTitle,
    );
  }
}
