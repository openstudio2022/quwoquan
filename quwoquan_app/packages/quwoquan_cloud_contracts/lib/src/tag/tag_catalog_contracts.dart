/// tag 域对象级 typed Facet 契约与 DTO（纯 Dart，零 App/平台依赖）。
///
/// Facet 划分对齐 quwoquan_service/services/tag-service/contracts/operations.yaml：
/// - [TagCatalogQuery] ↔ TagCatalogQueryFacade（层级/解析/校验）
library;

import '../operation_request_payload.dart';

/// 标签 API 默认分页常量。
class TagApiDefaults {
  TagApiDefaults._();
  static const int childrenLimit = 500;
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
  ValidateTagRefsQuery({
    required String expectedTaxonomyReleaseId,
    required Iterable<String> tagRefs,
  }) : expectedTaxonomyReleaseId = _requiredTagValue(
         expectedTaxonomyReleaseId,
         'expectedTaxonomyReleaseId',
       ),
       tagRefs = List<String>.unmodifiable(
         tagRefs.map((value) => _requiredTagValue(value, 'tagRefs')),
       ) {
    if (this.tagRefs.isEmpty) {
      throw ArgumentError.value(this.tagRefs, 'tagRefs', 'must not be empty');
    }
  }

  final String expectedTaxonomyReleaseId;
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
  Future<TagValidationResult> validateRefs({
    required String expectedTaxonomyReleaseId,
    required List<String> tagRefs,
  });
}

// ── DTO / Value Objects（对齐 tag/fields.yaml 各 *View）──────────────────

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

  factory TagResolve.fromJson(Map<String, Object?> json) => TagResolve(
    tagRef: _requiredResponseString(json, 'tagRef'),
    group: _requiredResponseString(json, 'group'),
    label: _requiredResponseString(json, 'label'),
    labelEn: _optionalResponseString(json, 'labelEn'),
    aliases: _optionalResponseString(json, 'aliases'),
    ancestors: _optionalResponseString(json, 'ancestors'),
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

  factory TagChild.fromJson(Map<String, Object?> json) => TagChild(
    tagRef: _requiredResponseString(json, 'tagRef'),
    label: _requiredResponseString(json, 'label'),
    displayLabel: _requiredResponseString(json, 'displayLabel'),
    labelEn: _optionalResponseString(json, 'labelEn'),
    parentTagRef: _requiredResponseString(json, 'parentTagRef'),
    depth: _requiredResponseInt(json, 'depth'),
    hasChildren: _requiredResponseBool(json, 'hasChildren'),
    releaseId: _requiredResponseString(json, 'releaseId'),
    lifecycleStatus: _requiredResponseString(json, 'lifecycleStatus'),
  );
}

class TagValidationResult {
  final String taxonomyReleaseId;
  final List<String> valid;
  final List<String> invalid;

  const TagValidationResult({
    required this.taxonomyReleaseId,
    required this.valid,
    required this.invalid,
  });

  factory TagValidationResult.fromJson(Map<String, Object?> json) =>
      TagValidationResult(
        taxonomyReleaseId: _requiredResponseString(json, 'taxonomyReleaseId'),
        valid: _requiredResponseStringList(json, 'valid'),
        invalid: _requiredResponseStringList(json, 'invalid'),
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
    body: <String, Object?>{
      'expectedTaxonomyReleaseId': query.expectedTaxonomyReleaseId,
      'tagRefs': query.tagRefs,
    },
  );
}

TagResolve decodeTagResolve(Object? response) {
  return TagResolve.fromJson(
    _tagObject(_unwrapTagPayload(response), 'TagResolve'),
  );
}

TagChildrenSlice decodeTagChildrenSlice(Object? response) {
  final payload = _tagObject(_unwrapTagPayload(response), 'TagChildrenSlice');
  final values = payload['items'];
  if (values is! List<Object?>) {
    throw const FormatException('TagChildrenSlice.items must be a list');
  }
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

Map<String, Object?> _tagObject(Object? value, String label) {
  if (value is! Map<Object?, Object?>) {
    throw FormatException('$label must be an object');
  }
  return value.map((key, item) => MapEntry(key.toString(), item));
}

String _requiredResponseString(Map<String, Object?> json, String field) {
  final value = json[field];
  if (value is! String || value.trim().isEmpty) {
    throw FormatException('$field must be a non-empty string');
  }
  return value.trim();
}

String _optionalResponseString(Map<String, Object?> json, String field) {
  final value = json[field];
  if (value == null) {
    return '';
  }
  if (value is! String) {
    throw FormatException('$field must be a string');
  }
  return value;
}

int _requiredResponseInt(Map<String, Object?> json, String field) {
  final value = json[field];
  if (value is! int) {
    throw FormatException('$field must be an int');
  }
  return value;
}

bool _requiredResponseBool(Map<String, Object?> json, String field) {
  final value = json[field];
  if (value is! bool) {
    throw FormatException('$field must be a bool');
  }
  return value;
}

List<String> _requiredResponseStringList(
  Map<String, Object?> json,
  String field,
) {
  final value = json[field];
  if (value is! List) {
    throw FormatException('$field must be a list');
  }
  return List<String>.unmodifiable(
    value.map((item) {
      if (item is! String || item.trim().isEmpty) {
        throw FormatException('$field entries must be non-empty strings');
      }
      return item.trim();
    }),
  );
}

String _requiredTagValue(String value, String field) {
  final normalized = value.trim();
  if (normalized.isEmpty) {
    throw ArgumentError.value(value, field, 'must not be empty');
  }
  return normalized;
}
