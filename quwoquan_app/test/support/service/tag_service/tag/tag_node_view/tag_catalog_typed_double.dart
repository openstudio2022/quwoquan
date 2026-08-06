import 'package:quwoquan_app/service/tag_service/tag/tag_node_view/application/public/tag_catalog_query.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../runtime/fixtures/object_scenario_seed_reader.dart';

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

  TagCatalogTypedDouble._({required this.taxonomyReleaseId, required this._catalog});

  final String taxonomyReleaseId;
  final _TagCatalogFixture _catalog;

  static _TagCatalogFixture _loadCatalog() {
    final decoded = _requiredObject(
      objectScenarioSeedReader.document('tag'),
      'tag fixture root',
    );
    final seedSets = _requiredObject(decoded['seedSets'], 'tag seedSets');
    final coreValue = seedSets['tag_catalog_core'];
    if (coreValue == null) {
      throw StateError('tag fixture is missing the tag_catalog_core scenario');
    }
    return _TagCatalogFixture.fromJson(
      _requiredObject(coreValue, 'tag_catalog_core'),
    );
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
