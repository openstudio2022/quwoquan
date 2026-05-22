import 'package:quwoquan_app/cloud/services/tag/tag_repository.dart';

/// Mock 数据：标签维度列表
const kMockTagDimensions = <TagDimension>[
  TagDimension(
    group: 'Topic',
    dimensionId: 'Topic/主题',
    label: '主题垂类',
    labelEn: 'Topic Vertical',
    maxDepth: 4,
    pathPolicy: 'any-depth',
  ),
  TagDimension(
    group: 'Topic',
    dimensionId: 'Topic/场景',
    label: '场景',
    labelEn: 'Scene',
    maxDepth: 3,
    pathPolicy: 'prefer-leaf',
  ),
  TagDimension(
    group: 'Topic',
    dimensionId: 'Topic/事件话题',
    label: '事件话题',
    labelEn: 'Trending Topics',
    maxDepth: 3,
    pathPolicy: 'any-depth',
  ),
  TagDimension(
    group: 'Topic',
    dimensionId: 'Topic/时间',
    label: '时间',
    labelEn: 'Time Dimension',
    maxDepth: 3,
    pathPolicy: 'prefer-leaf',
  ),
  TagDimension(
    group: 'Topic',
    dimensionId: 'Topic/地理',
    label: '地理',
    labelEn: 'Geography',
    maxDepth: 5,
    pathPolicy: 'any-depth',
  ),
  TagDimension(
    group: 'Audience',
    dimensionId: 'Audience/用户',
    label: '用户画像',
    labelEn: 'User Profile',
    maxDepth: 4,
    pathPolicy: 'leaf-only',
  ),
  TagDimension(
    group: 'Audience',
    dimensionId: 'Audience/创作者',
    label: '创作者',
    labelEn: 'Creator',
    maxDepth: 3,
    pathPolicy: 'any-depth',
  ),
  TagDimension(
    group: 'Audience',
    dimensionId: 'Audience/商品',
    label: '商品画像',
    labelEn: 'Product Profile',
    maxDepth: 3,
    pathPolicy: 'any-depth',
  ),
  TagDimension(
    group: 'Audience',
    dimensionId: 'Audience/圈子',
    label: '圈子画像',
    labelEn: 'Circle Profile',
    maxDepth: 3,
    pathPolicy: 'any-depth',
  ),
  TagDimension(
    group: 'Format',
    dimensionId: 'Format/内容载体',
    label: '内容载体',
    labelEn: 'Content Medium',
    maxDepth: 3,
    pathPolicy: 'prefer-leaf',
  ),
  TagDimension(
    group: 'Format',
    dimensionId: 'Format/内容角度',
    label: '内容角度',
    labelEn: 'Content Angle',
    maxDepth: 3,
    pathPolicy: 'any-depth',
  ),
  TagDimension(
    group: 'Format',
    dimensionId: 'Format/表现手法',
    label: '表现手法',
    labelEn: 'Production Technique',
    maxDepth: 3,
    pathPolicy: 'any-depth',
  ),
  TagDimension(
    group: 'Format',
    dimensionId: 'Format/视觉风格',
    label: '视觉风格',
    labelEn: 'Visual Style',
    maxDepth: 3,
    pathPolicy: 'any-depth',
  ),
  TagDimension(
    group: 'Entity',
    dimensionId: 'Entity/地点',
    label: '地点',
    labelEn: 'Place',
    maxDepth: 3,
    pathPolicy: 'any-depth',
  ),
  TagDimension(
    group: 'Entity',
    dimensionId: 'Entity/机构',
    label: '机构',
    labelEn: 'Organization',
    maxDepth: 2,
    pathPolicy: 'any-depth',
  ),
  TagDimension(
    group: 'Entity',
    dimensionId: 'Entity/活动',
    label: '活动',
    labelEn: 'Event',
    maxDepth: 2,
    pathPolicy: 'any-depth',
  ),
  TagDimension(
    group: 'Entity',
    dimensionId: 'Entity/人物',
    label: '人物',
    labelEn: 'Person',
    maxDepth: 3,
    pathPolicy: 'any-depth',
  ),
  TagDimension(
    group: 'Entity',
    dimensionId: 'Entity/品牌',
    label: '品牌',
    labelEn: 'Brand',
    maxDepth: 3,
    pathPolicy: 'any-depth',
  ),
];

/// Mock 数据：标签建议
const kMockTagSuggestions = <TagSuggestion>[
  TagSuggestion(
    tagRef: 'Topic/主题/自然风光',
    label: '自然风光',
    labelEn: 'Nature & Scenery',
    matchField: 'label',
  ),
  TagSuggestion(
    tagRef: 'Topic/主题/美食餐饮',
    label: '美食餐饮',
    labelEn: 'Food & Dining',
    matchField: 'label',
  ),
  TagSuggestion(
    tagRef: 'Topic/场景/出行场景/自驾游',
    label: '自驾游',
    labelEn: 'Self-driving Tour',
    matchField: 'label',
  ),
  TagSuggestion(
    tagRef: 'Format/内容角度/攻略',
    label: '攻略',
    labelEn: 'Guide',
    matchField: 'label',
  ),
  TagSuggestion(
    tagRef: 'Entity/地点/景区类型/5A景区',
    label: '5A景区',
    labelEn: '5A Scenic Spot',
    matchField: 'label',
  ),
  TagSuggestion(
    tagRef: 'Topic/地理/行政区/中国/四川省',
    label: '四川省',
    labelEn: 'Sichuan Province',
    matchField: 'label',
  ),
];

/// Mock 数据：有效 tagRef 集合（用于 validateRefs）
const kMockValidTagRefs = <String>{
  'Topic/主题/自然风光',
  'Topic/主题/美食餐饮',
  'Topic/场景/出行场景/自驾游',
  'Format/内容角度/攻略',
  'Format/内容角度/体验',
  'Format/内容角度/探店',
  'Entity/地点/景区类型/5A景区',
  'Topic/地理/行政区/中国/四川省',
  'Topic/地理/行政区/中国/四川省/成都市',
};

/// Mock 数据：相关标签
const kMockRelatedTags = <RelatedTag>[
  RelatedTag(tagRef: 'Topic/主题/历史文化', label: '历史文化', cooccurCount: 12),
  RelatedTag(tagRef: 'Topic/场景/出行场景/徒步', label: '徒步', cooccurCount: 8),
  RelatedTag(tagRef: 'Format/内容角度/攻略', label: '攻略', cooccurCount: 15),
];

/// Mock 数据：共现关系
const kMockCooccurrences = <TagCooccurrence>[
  TagCooccurrence(
    tagA: 'Topic/主题/自然风光',
    tagB: 'Topic/场景/出行场景/自驾游',
    cooccurCount: 24,
  ),
  TagCooccurrence(
    tagA: 'Topic/主题/美食餐饮',
    tagB: 'Format/内容角度/探店',
    cooccurCount: 18,
  ),
  TagCooccurrence(
    tagA: 'Entity/地点/景区类型/5A景区',
    tagB: 'Format/内容角度/攻略',
    cooccurCount: 15,
  ),
];
