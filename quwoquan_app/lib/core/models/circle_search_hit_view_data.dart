/// 圈子全局搜索视图 DTO。
///
/// 字段对齐：contracts/metadata/circle/circle/circle/fields.yaml
/// `CircleSearchHitViewData` / `CircleSearchFacetBucketViewData` / `CircleSearchResultViewData`。

library;

class CircleSearchHitViewData {
  const CircleSearchHitViewData({
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
}

class CircleSearchFacetBucketViewData {
  const CircleSearchFacetBucketViewData({
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
}

class CircleSearchResultViewData {
  const CircleSearchResultViewData({
    this.items = const <CircleSearchHitViewData>[],
    this.facetBuckets = const <CircleSearchFacetBucketViewData>[],
    this.cursor,
  });

  final List<CircleSearchHitViewData> items;
  final List<CircleSearchFacetBucketViewData> facetBuckets;
  final String? cursor;
}
