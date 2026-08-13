import 'package:quwoquan_app/service/tag_service/tag/tag_node_view/application/public/tag_catalog_query.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Tag 目录对象级替身：只在 local_contract 中读取 tag-service canonical 场景。
final class TagCatalogTypedDouble implements TagCatalogQuery {
  /// 默认发布身份来自 fixture 目录节点自身，与线上「客户端回显 TagChildView.releaseId」
  /// 同构；显式传值只用于构造过期发布的负例。
  factory TagCatalogTypedDouble({String? taxonomyReleaseId}) {
    final catalog = _loadCatalog();
    return TagCatalogTypedDouble._(
      taxonomyReleaseId: _requiredTaxonomyReleaseId(
        taxonomyReleaseId ?? catalog.taxonomyReleaseId,
      ),
      catalog: catalog,
    );
  }

  TagCatalogTypedDouble._({
    required this.taxonomyReleaseId,
    required this._catalog,
  });

  final String taxonomyReleaseId;
  final _TagCatalogFixture _catalog;

  static _TagCatalogFixture _loadCatalog() {
    return _TagCatalogFixture.fromJson(_tagCatalogWireExample());
  }

  @override
  Future<List<TagChildView>> listChildren(
    String parentTagRef, {
    int limit = TagApiDefaults.childrenLimit,
  }) async {
    final query = ListTagChildrenQuery(
      parentTagRef: parentTagRef,
      limit: limit,
    );
    if (!_catalog.knownTagRefs.contains(query.parentTagRef)) {
      throw StateError('TAG.USER.tag_not_found');
    }
    return (_catalog.childrenByParent[query.parentTagRef] ??
            const <TagChildView>[])
        .take(limit)
        .toList(growable: false);
  }

  @override
  Future<TagResolveView> resolveTag(String tagRef) async {
    final ref = tagRef.trim();
    for (final children in _catalog.childrenByParent.values) {
      for (final child in children) {
        if (child.tagRef == ref) {
          return TagResolveView(
            tagRef: child.tagRef,
            group: child.tagRef.split('/').first,
            label: (child.displayLabel ?? '').isNotEmpty
                ? child.displayLabel!
                : child.label,
            labelEn: child.labelEn,
          );
        }
      }
    }
    throw StateError('TAG.USER.tag_not_found');
  }

  @override
  Future<TagValidationResultView> validateRefs({
    required String expectedTaxonomyReleaseId,
    required List<String> tagRefs,
  }) async {
    final query = ValidateTagRefsQuery(
      expectedTaxonomyReleaseId: expectedTaxonomyReleaseId,
      tagRefs: tagRefs,
    );
    final valid = <String>[];
    final invalid = <String>[];
    for (final ref in query.tagRefs) {
      if (query.expectedTaxonomyReleaseId == taxonomyReleaseId &&
          _catalog.validTagRefs.contains(ref)) {
        valid.add(ref);
      } else {
        invalid.add(ref);
      }
    }
    return TagValidationResultView(
      taxonomyReleaseId: taxonomyReleaseId,
      valid: valid,
      invalid: invalid,
    );
  }

  static String _requiredTaxonomyReleaseId(String value) {
    final normalized = value.trim();
    if (normalized.isEmpty) {
      throw ArgumentError.value(
        value,
        'taxonomyReleaseId',
        'must not be empty',
      );
    }
    return normalized;
  }
}

final class _TagCatalogFixture {
  const _TagCatalogFixture({
    required this.childrenByParent,
    required this.validTagRefs,
    required this.knownTagRefs,
    required this.taxonomyReleaseId,
  });

  final Map<String, List<TagChildView>> childrenByParent;
  final Set<String> validTagRefs;
  final Set<String> knownTagRefs;
  final String taxonomyReleaseId;

  factory _TagCatalogFixture.fromJson(Map<String, Object?> json) {
    final rawChildren = _requiredObject(
      json['childrenByParent'],
      'tag childrenByParent',
    );
    final childrenByParent = <String, List<TagChildView>>{
      for (final entry in rawChildren.entries)
        entry.key:
            _requiredList(entry.value, 'tag childrenByParent.${entry.key}')
                .map(
                  (item) => _tagChildViewFromFixture(
                    _requiredObject(item, 'tag child'),
                  ),
                )
                .toList(growable: false),
    };

    final validTagRefs = _requiredList(json['validTagRefs'], 'tag validTagRefs')
        .map((item) {
          if (item is! String || item.trim().isEmpty) {
            throw const FormatException(
              'tag validTagRefs entries must be non-empty strings',
            );
          }
          return item.trim();
        })
        .toSet();
    final releaseIds = <String>{
      for (final children in childrenByParent.values)
        for (final child in children)
          if (child.releaseId.trim().isNotEmpty) child.releaseId.trim(),
    };
    if (releaseIds.length != 1) {
      throw FormatException(
        'tag fixture must expose exactly one taxonomy release; '
        'found ${releaseIds.length}',
      );
    }
    return _TagCatalogFixture(
      childrenByParent: childrenByParent,
      validTagRefs: validTagRefs,
      taxonomyReleaseId: releaseIds.single,
      knownTagRefs: <String>{
        ...validTagRefs,
        ...childrenByParent.keys,
        for (final children in childrenByParent.values)
          for (final child in children) child.tagRef,
      },
    );
  }
}

TagChildView _tagChildViewFromFixture(Map<String, Object?> value) {
  return TagChildView(
    tagRef: _requiredString(value, 'tagRef'),
    label: _requiredString(value, 'label'),
    displayLabel: _optionalString(value, 'displayLabel'),
    labelEn: _optionalString(value, 'labelEn'),
    parentTagRef: _requiredString(value, 'parentTagRef'),
    depth: _requiredInt(value, 'depth'),
    hasChildren: _requiredBool(value, 'hasChildren'),
    releaseId: _requiredString(value, 'releaseId'),
    lifecycleStatus: TagLifecycleStatus.fromWire(
      value['lifecycleStatus'],
      'lifecycleStatus',
    ),
  );
}

String _requiredString(Map<String, Object?> value, String field) {
  final item = value[field];
  if (item is! String || item.trim().isEmpty) {
    throw FormatException('$field must be a non-empty string');
  }
  return item.trim();
}

String? _optionalString(Map<String, Object?> value, String field) {
  final item = value[field];
  if (item == null) return null;
  if (item is! String) throw FormatException('$field must be a string');
  return item;
}

int _requiredInt(Map<String, Object?> value, String field) {
  final item = value[field];
  if (item is! int) throw FormatException('$field must be an int');
  return item;
}

bool _requiredBool(Map<String, Object?> value, String field) {
  final item = value[field];
  if (item is! bool) throw FormatException('$field must be a bool');
  return item;
}

Map<String, Object?> _requiredObject(Object? value, String label) {
  if (value is! Map) {
    throw FormatException('$label must be an object');
  }
  final result = <String, Object?>{};
  for (final entry in value.entries) {
    if (entry.key is! String) {
      throw FormatException('$label keys must be strings');
    }
    result[entry.key as String] = entry.value;
  }
  return result;
}

List<Object?> _requiredList(Object? value, String label) {
  if (value is! List) {
    throw FormatException('$label must be a list');
  }
  return value.cast<Object?>();
}

Map<String, Object?> _tagCatalogWireExample() {
  const chinaRoot = 'Topic/地理/行政区/中国';
  const guangdong = '$chinaRoot/广东省';
  const occupationRoot = 'Audience/用户/职业';
  const productOps = '$occupationRoot/产品运营';
  const engineering = '$occupationRoot/研发技术';
  const design = '$occupationRoot/设计创意';
  const student = '$occupationRoot/学生';
  const freelance = '$occupationRoot/自由职业';
  const interestRoot = 'Audience/用户/兴趣偏好';
  const travelPhoto = '$interestRoot/旅行摄影';
  const campus = '$interestRoot/校园';
  const life = '$interestRoot/生活';
  const art = '$interestRoot/艺术';
  const tech = '$interestRoot/科技';
  final provinces = _provinceLabels
      .map(
        (label) => _tagChild(
          parent: chinaRoot,
          label: label,
          displayLabel: label.replaceAll('省', '').replaceAll('市', ''),
          hasChildren: true,
        ),
      )
      .toList(growable: false);
  final childrenByParent = <String, Object?>{
    chinaRoot: provinces,
    // 广东 21 个地级市全量（与真实 taxonomy 同构）：编辑资料 T28 旅程需要滚动到
    // 列表远端的「云浮」验证长列表选择，替身不得只保留头部两市造成数据脱节。
    guangdong: <Map<String, Object?>>[
      for (final city in _guangdongCityLabels)
        _tagChild(
          parent: guangdong,
          label: city,
          displayLabel: city.replaceAll('市', ''),
        ),
    ],
    // 职业与兴趣分类必须覆盖 UserProfileUIConfig.careerInterestCatalog 声明的
    // 全部分类节点：页面对每个分类 tagRef 调 listChildren，缺注册会命中
    // TAG.USER.tag_not_found 使整页进错误态（career_interest 三红根因）。
    occupationRoot: <Map<String, Object?>>[
      _tagChild(parent: occupationRoot, label: '产品运营', hasChildren: true),
      _tagChild(parent: occupationRoot, label: '研发技术', hasChildren: true),
      _tagChild(parent: occupationRoot, label: '设计创意', hasChildren: true),
      _tagChild(parent: occupationRoot, label: '学生', hasChildren: true),
      _tagChild(parent: occupationRoot, label: '自由职业', hasChildren: true),
    ],
    productOps: <Map<String, Object?>>[
      _tagChild(parent: productOps, label: '产品经理'),
      _tagChild(parent: productOps, label: '产品运营'),
    ],
    engineering: <Map<String, Object?>>[
      _tagChild(parent: engineering, label: '后端工程师'),
      _tagChild(parent: engineering, label: '客户端工程师'),
    ],
    design: <Map<String, Object?>>[
      _tagChild(parent: design, label: '视觉设计师'),
    ],
    student: <Map<String, Object?>>[
      _tagChild(parent: student, label: '本科生'),
    ],
    freelance: <Map<String, Object?>>[
      _tagChild(parent: freelance, label: '自媒体'),
    ],
    interestRoot: <Map<String, Object?>>[
      _tagChild(parent: interestRoot, label: '旅行摄影', hasChildren: true),
      _tagChild(parent: interestRoot, label: '校园', hasChildren: true),
      _tagChild(parent: interestRoot, label: '生活', hasChildren: true),
      _tagChild(parent: interestRoot, label: '艺术', hasChildren: true),
      _tagChild(parent: interestRoot, label: '科技', hasChildren: true),
    ],
    travelPhoto: <Map<String, Object?>>[
      _tagChild(parent: travelPhoto, label: '旅行'),
      _tagChild(parent: travelPhoto, label: '摄影'),
      _tagChild(parent: travelPhoto, label: '城市漫游'),
    ],
    campus: <Map<String, Object?>>[
      _tagChild(parent: campus, label: '考研'),
      _tagChild(parent: campus, label: '社团'),
    ],
    life: <Map<String, Object?>>[
      _tagChild(parent: life, label: '美食'),
      _tagChild(parent: life, label: '徒步'),
    ],
    art: <Map<String, Object?>>[
      _tagChild(parent: art, label: '胶片摄影'),
      _tagChild(parent: art, label: '手工'),
    ],
    tech: <Map<String, Object?>>[
      _tagChild(parent: tech, label: '人工智能'),
    ],
  };
  final validRefs = <String>[
    'Topic/主题/自然风光',
    for (final value in childrenByParent.values)
      for (final child in (value as List<Map<String, Object?>>))
        child['tagRef']! as String,
  ];
  return <String, Object?>{
    'childrenByParent': childrenByParent,
    'validTagRefs': validRefs,
  };
}

Map<String, Object?> _tagChild({
  required String parent,
  required String label,
  String? displayLabel,
  bool hasChildren = false,
}) => <String, Object?>{
  'tagRef': '$parent/$label',
  'label': label,
  'displayLabel': displayLabel ?? label,
  'labelEn': '',
  'parentTagRef': parent,
  'depth': 4,
  'hasChildren': hasChildren,
  'releaseId': 'tag-catalog-current',
  'lifecycleStatus': 'active',
};

const List<String> _guangdongCityLabels = <String>[
  '广州市',
  '深圳市',
  '珠海市',
  '汕头市',
  '佛山市',
  '韶关市',
  '湛江市',
  '肇庆市',
  '江门市',
  '茂名市',
  '惠州市',
  '梅州市',
  '汕尾市',
  '河源市',
  '阳江市',
  '清远市',
  '东莞市',
  '中山市',
  '潮州市',
  '揭阳市',
  '云浮市',
];

const List<String> _provinceLabels = <String>[
  '广东省',
  '北京市',
  '上海市',
  '浙江省',
  '江苏省',
  '四川省',
  '重庆市',
  '福建省',
  '湖北省',
  '湖南省',
  '山东省',
  '河南省',
  '河北省',
  '安徽省',
  '广西壮族自治区',
  '海南省',
  '天津市',
  '山西省',
  '内蒙古自治区',
  '辽宁省',
  '吉林省',
  '黑龙江省',
  '江西省',
  '贵州省',
  '云南省',
  '西藏自治区',
  '陕西省',
  '甘肃省',
  '青海省',
  '宁夏回族自治区',
  '新疆维吾尔自治区',
  '香港特别行政区',
  '澳门特别行政区',
  '台湾省',
];
