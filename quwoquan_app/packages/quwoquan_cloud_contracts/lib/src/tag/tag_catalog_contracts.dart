/// tag 域对象级 typed Facet 契约与 DTO（纯 Dart，零 App/平台依赖）。
///
/// Facet 划分对齐 contracts/metadata/tag/service.yaml：
/// - [TagCatalogQuery] ↔ TagCatalogQueryFacade（层级/解析/维度/联想/校验/搜索/相关）
/// - [TagGraphQuery] ↔ TagGraphQueryFacade（共享标签/反向索引/共现/相关对象/多标签搜索）
library;

import '../operation_request_payload.dart';

/// 标签 API 默认分页常量。
class TagApiDefaults {
  TagApiDefaults._();
  static const int childrenLimit = 500;
  static const int suggestLimit = 20;
  static const int searchLimit = 50;
  static const int relatedLimit = 20;
  static const int graphLimit = 50;
  static const int minCooccurCount = 1;
}

/// 端侧消费的稳定 taxonomy 根（值与数据工程 taxonomy 目录一致）。
class TagTaxonomyRefs {
  TagTaxonomyRefs._();
  static const String chinaAdminRegionRoot = 'Topic/地理/行政区/中国';
  static const String careerOccupationRoot = 'Audience/用户/职业';
  static const String careerInterestRoot = 'Audience/用户/兴趣偏好';
}

/// App 商用页面暴露的标签解析查询。
final class ResolveTagQuery {
  ResolveTagQuery({required String tagRef})
    : tagRef = _requiredTagValue(tagRef, 'tagRef');

  final String tagRef;
}

/// App 商用页面暴露的标签子节点查询。
final class ListTagChildrenQuery {
  ListTagChildrenQuery({
    required String parentTagRef,
    this.limit = TagApiDefaults.childrenLimit,
  }) : parentTagRef = _requiredTagValue(parentTagRef, 'parentTagRef') {
    if (limit <= 0) {
      throw ArgumentError.value(limit, 'limit', 'must be positive');
    }
  }

  final String parentTagRef;
  final int limit;
}

/// App 商用页面暴露的批量标签校验查询。
final class ValidateTagRefsQuery {
  ValidateTagRefsQuery({required Iterable<String> tagRefs})
    : tagRefs = List<String>.unmodifiable(
        tagRefs.map((value) => _requiredTagValue(value, 'tagRefs')),
      ) {
    if (this.tagRefs.isEmpty) {
      throw ArgumentError.value(this.tagRefs, 'tagRefs', 'must not be empty');
    }
  }

  final List<String> tagRefs;
}

/// 标签直接子节点的强类型切片。
final class TagChildrenSlice {
  TagChildrenSlice(Iterable<TagChild> items)
    : items = List<TagChild>.unmodifiable(items);

  final List<TagChild> items;
}

/// 标签目录查询 Facet（R02：≤10 方法）。
abstract interface class TagCatalogQuery {
  Future<List<TagChild>> listChildren(
    String parentTagRef, {
    int limit = TagApiDefaults.childrenLimit,
  });
  Future<TagResolve> resolveTag(String tagRef);
  Future<List<TagDimension>> listDimensions();
  Future<List<TagSuggestion>> suggest(
    String query, {
    String? group,
    int limit = TagApiDefaults.suggestLimit,
  });
  Future<TagValidationResult> validateRefs(List<String> tagRefs);
  Future<List<TagSearchResult>> search(
    String query, {
    String? group,
    int limit = TagApiDefaults.searchLimit,
  });
  Future<List<RelatedTag>> related(
    String tagRef, {
    int limit = TagApiDefaults.relatedLimit,
  });
}

/// 标签图谱查询 Facet（R02：≤10 方法）。
abstract interface class TagGraphQuery {
  Future<List<TagObjectMatch>> searchByTags(
    List<String> tagRefs, {
    String? objectType,
    int limit = TagApiDefaults.searchLimit,
  });
  Future<List<TagCooccurrence>> cooccurrence({
    String? tagRef,
    int minCount = TagApiDefaults.minCooccurCount,
    int limit = TagApiDefaults.graphLimit,
  });
  Future<TagInvertedResult> invertedIndex(
    String tagRef, {
    String? objectType,
    int limit = TagApiDefaults.graphLimit,
  });
  Future<List<RelatedObject>> relatedObjects(
    String objectId, {
    String? objectType,
    int limit = TagApiDefaults.relatedLimit,
  });
  Future<List<SharedTagView>> sharedTags({
    required String objectAId,
    required String objectAType,
    required String objectBId,
    required String objectBType,
    int limit = TagApiDefaults.graphLimit,
  });
}

// ── DTO / Value Objects（对齐 tag/fields.yaml 各 *View）──────────────────

/// 交集锚点（/tag/shared-tags 返回项，对齐 SharedTagView）。
class SharedTagView {
  final String tagRef;
  final String label;
  final double strength;
  final String source;

  const SharedTagView({
    required this.tagRef,
    required this.label,
    this.strength = 0.0,
    this.source = '',
  });

  factory SharedTagView.fromJson(Map<String, dynamic> json) => SharedTagView(
    tagRef: json['tagRef'] as String? ?? '',
    label: json['label'] as String? ?? '',
    strength: (json['strength'] as num?)?.toDouble() ?? 0.0,
    source: json['source'] as String? ?? '',
  );
}

/// 标签解析结果（/tag/resolve 返回项）。
class TagResolve {
  final String tagRef;
  final String group;
  final String label;
  final String labelEn;
  final String aliases;
  final String ancestors;

  const TagResolve({
    required this.tagRef,
    required this.group,
    required this.label,
    this.labelEn = '',
    this.aliases = '',
    this.ancestors = '',
  });

  factory TagResolve.fromJson(Map<String, dynamic> json) => TagResolve(
    tagRef: json['tagRef'] as String? ?? '',
    group: json['group'] as String? ?? '',
    label: json['label'] as String? ?? '',
    labelEn: json['labelEn'] as String? ?? '',
    aliases: json['aliases'] as String? ?? '',
    ancestors: json['ancestors'] as String? ?? '',
  );
}

/// 标签层级直接子节点（/tag/children 返回项）。
class TagChild {
  final String tagRef;
  final String label;
  final String displayLabel;
  final String labelEn;
  final String parentTagRef;
  final int depth;
  final bool hasChildren;
  final String releaseId;
  final String lifecycleStatus;

  const TagChild({
    required this.tagRef,
    required this.label,
    required this.displayLabel,
    required this.labelEn,
    required this.parentTagRef,
    required this.depth,
    required this.hasChildren,
    required this.releaseId,
    required this.lifecycleStatus,
  });

  factory TagChild.fromJson(Map<String, dynamic> json) => TagChild(
    tagRef: json['tagRef'] as String? ?? '',
    label: json['label'] as String? ?? '',
    displayLabel: json['displayLabel'] as String? ?? '',
    labelEn: json['labelEn'] as String? ?? '',
    parentTagRef: json['parentTagRef'] as String? ?? '',
    depth: (json['depth'] as num?)?.toInt() ?? 0,
    hasChildren: json['hasChildren'] as bool? ?? false,
    releaseId: json['releaseId'] as String? ?? '',
    lifecycleStatus: json['lifecycleStatus'] as String? ?? '',
  );
}

class TagDimension {
  final String group;
  final String dimensionId;
  final String label;
  final String labelEn;
  final int maxDepth;
  final String pathPolicy;

  const TagDimension({
    required this.group,
    required this.dimensionId,
    required this.label,
    required this.labelEn,
    required this.maxDepth,
    required this.pathPolicy,
  });

  factory TagDimension.fromJson(Map<String, dynamic> json) => TagDimension(
    group: json['group'] as String? ?? '',
    dimensionId: json['dimensionId'] as String? ?? '',
    label: json['label'] as String? ?? '',
    labelEn: json['labelEn'] as String? ?? '',
    maxDepth: json['maxDepth'] as int? ?? 3,
    pathPolicy: json['pathPolicy'] as String? ?? 'any-depth',
  );
}

class TagSuggestion {
  final String tagRef;
  final String label;
  final String labelEn;
  final String matchField;

  const TagSuggestion({
    required this.tagRef,
    required this.label,
    required this.labelEn,
    required this.matchField,
  });

  factory TagSuggestion.fromJson(Map<String, dynamic> json) => TagSuggestion(
    tagRef: json['tagRef'] as String? ?? '',
    label: json['label'] as String? ?? '',
    labelEn: json['labelEn'] as String? ?? '',
    matchField: json['matchField'] as String? ?? '',
  );
}

class TagValidationResult {
  final List<String> valid;
  final List<String> invalid;
  final List<TagRefSuggestion> suggestions;

  const TagValidationResult({
    required this.valid,
    required this.invalid,
    required this.suggestions,
  });

  factory TagValidationResult.fromJson(Map<String, dynamic> json) =>
      TagValidationResult(
        valid: (json['valid'] as List?)?.cast<String>() ?? [],
        invalid: (json['invalid'] as List?)?.cast<String>() ?? [],
        suggestions:
            (json['suggestions'] as List?)
                ?.map(
                  (e) => TagRefSuggestion.fromJson(e as Map<String, dynamic>),
                )
                .toList() ??
            [],
      );
}

class TagRefSuggestion {
  final String invalid;
  final String suggestedRef;
  final String reason;

  const TagRefSuggestion({
    required this.invalid,
    required this.suggestedRef,
    required this.reason,
  });

  factory TagRefSuggestion.fromJson(Map<String, dynamic> json) =>
      TagRefSuggestion(
        invalid: json['invalid'] as String? ?? '',
        suggestedRef: json['suggestedRef'] as String? ?? '',
        reason: json['reason'] as String? ?? '',
      );
}

class TagSearchResult {
  final String tagRef;
  final String label;
  final double score;

  const TagSearchResult({
    required this.tagRef,
    required this.label,
    required this.score,
  });

  factory TagSearchResult.fromJson(Map<String, dynamic> json) =>
      TagSearchResult(
        tagRef: json['tagRef'] as String? ?? '',
        label: json['label'] as String? ?? '',
        score: (json['score'] as num?)?.toDouble() ?? 0.0,
      );
}

class RelatedTag {
  final String tagRef;
  final String label;
  final int cooccurCount;

  const RelatedTag({
    required this.tagRef,
    required this.label,
    required this.cooccurCount,
  });

  factory RelatedTag.fromJson(Map<String, dynamic> json) => RelatedTag(
    tagRef: json['tagRef'] as String? ?? '',
    label: json['label'] as String? ?? '',
    cooccurCount: json['cooccurCount'] as int? ?? 0,
  );
}

class TagObjectMatch {
  final String objectId;
  final String objectType;
  final List<String> matchedTags;
  final double score;

  const TagObjectMatch({
    required this.objectId,
    required this.objectType,
    required this.matchedTags,
    required this.score,
  });

  factory TagObjectMatch.fromJson(Map<String, dynamic> json) => TagObjectMatch(
    objectId: json['objectId'] as String? ?? '',
    objectType: json['objectType'] as String? ?? '',
    matchedTags: (json['matchedTags'] as List?)?.cast<String>() ?? [],
    score: (json['score'] as num?)?.toDouble() ?? 0.0,
  );
}

class TagCooccurrence {
  final String tagA;
  final String tagB;
  final int cooccurCount;

  const TagCooccurrence({
    required this.tagA,
    required this.tagB,
    required this.cooccurCount,
  });

  factory TagCooccurrence.fromJson(Map<String, dynamic> json) =>
      TagCooccurrence(
        tagA: json['tagA'] as String? ?? '',
        tagB: json['tagB'] as String? ?? '',
        cooccurCount: json['cooccurCount'] as int? ?? 0,
      );
}

class TagInvertedResult {
  final String tag;
  final int objectCount;
  final List<String> objects;

  const TagInvertedResult({
    required this.tag,
    required this.objectCount,
    required this.objects,
  });

  factory TagInvertedResult.fromJson(Map<String, dynamic> json) =>
      TagInvertedResult(
        tag: json['tag'] as String? ?? '',
        objectCount: json['objectCount'] as int? ?? 0,
        objects: (json['objects'] as List?)?.cast<String>() ?? [],
      );
}

class RelatedObject {
  final String objectId;
  final String objectType;
  final List<String> sharedTags;
  final int sharedCount;

  const RelatedObject({
    required this.objectId,
    required this.objectType,
    required this.sharedTags,
    required this.sharedCount,
  });

  factory RelatedObject.fromJson(Map<String, dynamic> json) => RelatedObject(
    objectId: json['objectId'] as String? ?? '',
    objectType: json['objectType'] as String? ?? '',
    sharedTags: (json['sharedTags'] as List?)?.cast<String>() ?? [],
    sharedCount: json['sharedCount'] as int? ?? 0,
  );
}

CloudOperationRequestPayload encodeResolveTagQuery(ResolveTagQuery query) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{'tagRef': query.tagRef},
  );
}

CloudOperationRequestPayload encodeListTagChildrenQuery(
  ListTagChildrenQuery query,
) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      'parentTagRef': query.parentTagRef,
      'limit': '${query.limit}',
    },
  );
}

CloudOperationRequestPayload encodeValidateTagRefsQuery(
  ValidateTagRefsQuery query,
) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{'tagRefs': query.tagRefs},
  );
}

TagResolve decodeTagResolve(Object? response) {
  return TagResolve.fromJson(
    _tagObject(_unwrapTagPayload(response), 'TagResolve'),
  );
}

TagChildrenSlice decodeTagChildrenSlice(Object? response) {
  final payload = _unwrapTagPayload(response);
  final values = switch (payload) {
    List<Object?> items => items,
    Map<Object?, Object?> map when map['items'] is List<Object?> =>
      map['items']! as List<Object?>,
    _ => throw FormatException('TagChildrenSlice must be a list'),
  };
  return TagChildrenSlice(
    values.map((value) => TagChild.fromJson(_tagObject(value, 'TagChild'))),
  );
}

TagValidationResult decodeTagValidationResult(Object? response) {
  return TagValidationResult.fromJson(
    _tagObject(_unwrapTagPayload(response), 'TagValidationResult'),
  );
}

Object? _unwrapTagPayload(Object? response) {
  if (response case final Map<Object?, Object?> map) {
    return map.containsKey('data') ? map['data'] : response;
  }
  return response;
}

Map<String, dynamic> _tagObject(Object? value, String label) {
  if (value is! Map<Object?, Object?>) {
    throw FormatException('$label must be an object');
  }
  return value.map((key, item) => MapEntry(key.toString(), item));
}

String _requiredTagValue(String value, String field) {
  final normalized = value.trim();
  if (normalized.isEmpty) {
    throw ArgumentError.value(value, field, 'must not be empty');
  }
  return normalized;
}
