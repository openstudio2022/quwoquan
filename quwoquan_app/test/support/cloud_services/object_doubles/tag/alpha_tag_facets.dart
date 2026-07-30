import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../object_scenario_seed_reader.dart';

/// Tag 目录对象级替身：只在 local_contract 中读取 tag-service canonical 场景。
final class AlphaTagFacet implements TagCatalogQuery {
  /// 默认发布身份来自 fixture 目录节点自身，与线上「客户端回显 TagChild.releaseId」
  /// 同构；显式传值只用于构造过期发布的负例。
  factory AlphaTagFacet({String? taxonomyReleaseId}) {
    final catalog = _loadCatalog();
    return AlphaTagFacet._(
      taxonomyReleaseId: _requiredTaxonomyReleaseId(
        taxonomyReleaseId ?? catalog.taxonomyReleaseId,
      ),
      catalog: catalog,
    );
  }

  AlphaTagFacet._({
    required this.taxonomyReleaseId,
    required _TagCatalogFixture catalog,
  }) : _catalog = catalog;

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
  Future<List<TagChild>> listChildren(
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
    return (_catalog.childrenByParent[query.parentTagRef] ?? const <TagChild>[])
        .take(limit)
        .toList(growable: false);
  }

  @override
  Future<TagResolve> resolveTag(String tagRef) async {
    final ref = tagRef.trim();
    for (final children in _catalog.childrenByParent.values) {
      for (final child in children) {
        if (child.tagRef == ref) {
          return TagResolve(
            tagRef: child.tagRef,
            group: child.tagRef.split('/').first,
            label: child.displayLabel.isNotEmpty
                ? child.displayLabel
                : child.label,
            labelEn: child.labelEn,
          );
        }
      }
    }
    throw StateError('TAG.USER.tag_not_found');
  }

  @override
  Future<TagValidationResult> validateRefs({
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
    return TagValidationResult(
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

/// Alpha TagFeedback 替身：进程内追加 + 同 key 幂等（与服务端唯一索引同构）。
final class AlphaTagFeedbackWriter implements TagFeedbackCommandWriter {
  final Map<String, ReportTagFeedbackCommand> _byKey =
      <String, ReportTagFeedbackCommand>{};

  List<ReportTagFeedbackCommand> get recorded =>
      _byKey.values.toList(growable: false);

  @override
  Future<TagFeedbackAck> reportTagFeedback(
    ReportTagFeedbackCommand command,
  ) async {
    final key =
        '${command.tagRef}\u0000${command.action.wireValue}\u0000${command.context ?? ''}';
    _byKey.putIfAbsent(key, () => command);
    return const TagFeedbackAck(accepted: true);
  }
}

final class _TagCatalogFixture {
  const _TagCatalogFixture({
    required this.childrenByParent,
    required this.validTagRefs,
    required this.knownTagRefs,
    required this.taxonomyReleaseId,
  });

  final Map<String, List<TagChild>> childrenByParent;
  final Set<String> validTagRefs;
  final Set<String> knownTagRefs;
  final String taxonomyReleaseId;

  factory _TagCatalogFixture.fromJson(Map<String, Object?> json) {
    final rawChildren = _requiredObject(
      json['childrenByParent'],
      'tag childrenByParent',
    );
    final childrenByParent = <String, List<TagChild>>{
      for (final entry in rawChildren.entries)
        entry.key:
            _requiredList(entry.value, 'tag childrenByParent.${entry.key}')
                .map(
                  (item) =>
                      TagChild.fromJson(_requiredObject(item, 'tag child')),
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
