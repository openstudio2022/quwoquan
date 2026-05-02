/// 圈子全局搜索视图 DTO。
///
/// 字段对齐：contracts/metadata/social/circle/fields.yaml
/// `CircleSearchItemView` / `CircleFacetBucketView` / `CircleSearchResultView`。

class CircleSearchItemView {
  const CircleSearchItemView({
    required this.circleId,
    required this.name,
    this.description,
    this.coverUrl,
    this.categoryId,
    this.subCategory,
    this.domainId,
    this.kind,
    this.displaySubjectType,
    required this.memberCount,
    required this.postCount,
    this.highlightText,
    this.matchedField,
    this.circleName,
    this.linkedHomepageId,
    this.linkedHomepageType,
    this.linkedHomepageTitle,
  });

  final String circleId;
  final String name;
  final String? description;
  final String? coverUrl;
  final String? categoryId;
  final String? subCategory;
  final String? domainId;
  final String? kind;
  final String? displaySubjectType;
  final int memberCount;
  final int postCount;
  final String? highlightText;
  final String? matchedField;

  /// 群组结果场景下父圈子展示名（wire：`circleName` / `circle_name`）。
  final String? circleName;

  final String? linkedHomepageId;
  final String? linkedHomepageType;
  final String? linkedHomepageTitle;

  factory CircleSearchItemView.fromMap(Map<String, dynamic> map) {
    return CircleSearchItemView(
      circleId: (map['circleId'] ?? map['id'] ?? map['_id'] ?? '')
          .toString()
          .trim(),
      name: (map['name'] ?? '').toString().trim(),
      description: map['description']?.toString(),
      coverUrl: (map['coverUrl'] ?? map['cover'])?.toString(),
      categoryId: (map['categoryId'] ?? map['category'])?.toString(),
      subCategory: map['subCategory']?.toString(),
      domainId: map['domainId']?.toString(),
      kind: map['kind']?.toString(),
      displaySubjectType: map['displaySubjectType']?.toString(),
      memberCount: (map['memberCount'] as num?)?.toInt() ?? 0,
      postCount: (map['postCount'] as num?)?.toInt() ?? 0,
      highlightText: map['highlightText']?.toString(),
      matchedField: map['matchedField']?.toString(),
      circleName:
          map['circleName']?.toString() ?? map['circle_name']?.toString(),
      linkedHomepageId: map['linkedHomepageId']?.toString(),
      linkedHomepageType: map['linkedHomepageType']?.toString(),
      linkedHomepageTitle: map['linkedHomepageTitle']?.toString(),
    );
  }

  /// 全局搜索 [SearchHit.payload]（与记录手写字段表一致，避免与视图字段漂移）。
  Map<String, dynamic> toSearchHitPayload() => <String, dynamic>{
    'id': circleId,
    'circleId': circleId,
    'name': name,
    'description': description,
    'coverUrl': coverUrl,
    'categoryId': categoryId,
    'subCategory': subCategory,
    'domainId': domainId,
    'kind': kind,
    'displaySubjectType': displaySubjectType,
    'memberCount': memberCount,
    'postCount': postCount,
    'highlightText': highlightText,
    'matchedField': matchedField,
    if (circleName != null && circleName!.trim().isNotEmpty)
      'circleName': circleName,
    if (linkedHomepageId != null) 'linkedHomepageId': linkedHomepageId,
    if (linkedHomepageType != null) 'linkedHomepageType': linkedHomepageType,
    if (linkedHomepageTitle != null) 'linkedHomepageTitle': linkedHomepageTitle,
  };
}

class CircleFacetBucketView {
  const CircleFacetBucketView({
    required this.facetKey,
    required this.label,
    this.categoryId,
    this.subCategory,
    required this.facetCount,
  });

  final String facetKey;
  final String label;
  final String? categoryId;
  final String? subCategory;
  final int facetCount;

  factory CircleFacetBucketView.fromMap(Map<String, dynamic> map) {
    return CircleFacetBucketView(
      facetKey:
          (map['facetKey'] ?? map['subCategory'] ?? map['categoryId'] ?? '')
              .toString()
              .trim(),
      label: (map['label'] ?? map['subCategory'] ?? map['categoryId'] ?? '')
          .toString()
          .trim(),
      categoryId: map['categoryId']?.toString(),
      subCategory: map['subCategory']?.toString(),
      facetCount: (map['facetCount'] as num?)?.toInt() ?? 0,
    );
  }
}

class CircleSearchResultView {
  const CircleSearchResultView({
    this.items = const <CircleSearchItemView>[],
    this.facetBuckets = const <CircleFacetBucketView>[],
    this.cursor,
  });

  final List<CircleSearchItemView> items;
  final List<CircleFacetBucketView> facetBuckets;
  final String? cursor;

  factory CircleSearchResultView.fromMap(Map<String, dynamic> map) {
    final itemMaps =
        (map['items'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    final facetMaps =
        (map['facetBuckets'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    return CircleSearchResultView(
      items: itemMaps.map(CircleSearchItemView.fromMap).toList(growable: false),
      facetBuckets: facetMaps
          .map(CircleFacetBucketView.fromMap)
          .toList(growable: false),
      cursor: map['cursor']?.toString(),
    );
  }
}
