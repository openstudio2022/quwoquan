import 'dart:convert';

import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../generated/alpha_fixture_bundle.g.dart';

/// Alpha tag 目录/图谱 Facet：数据唯一来源为 metadata seed manifest 生成的
/// immutable fixture bundle（tag_scenarios.json 的 tag_catalog_core），
/// 不发 HTTP、不在代码内维护第二套目录数据。
final class AlphaTagFacet implements TagCatalogQuery, TagGraphQuery {
  AlphaTagFacet() : _catalog = _loadCatalog();

  final _TagCatalogFixture _catalog;

  static _TagCatalogFixture _loadCatalog() {
    final asset = alphaFixtureBundle.assets['tag'];
    if (asset == null) {
      throw StateError('alpha fixture bundle is missing the tag domain');
    }
    final decoded = json.decode(asset.sourceJson) as Map<String, dynamic>;
    final seedSets = decoded['seedSets'] as Map<String, dynamic>? ?? const {};
    final core = seedSets['tag_catalog_core'] as Map<String, dynamic>?;
    if (core == null) {
      throw StateError('tag fixture is missing the tag_catalog_core scenario');
    }
    return _TagCatalogFixture.fromJson(core);
  }

  @override
  Future<List<TagChild>> listChildren(
    String parentTagRef, {
    int limit = TagApiDefaults.childrenLimit,
  }) async {
    return (_catalog.childrenByParent[parentTagRef.trim()] ??
            const <TagChild>[])
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
    for (final suggestion in _catalog.suggestions) {
      if (suggestion.tagRef == ref) {
        return TagResolve(
          tagRef: suggestion.tagRef,
          group: suggestion.tagRef.split('/').first,
          label: suggestion.label,
          labelEn: suggestion.labelEn,
        );
      }
    }
    final parts = ref.split('/').where((part) => part.isNotEmpty).toList();
    final fallback = parts.isEmpty ? ref : parts.last;
    return TagResolve(
      tagRef: ref,
      group: parts.isEmpty ? '' : parts.first,
      label: fallback,
    );
  }

  @override
  Future<List<TagDimension>> listDimensions() async => _catalog.dimensions;

  @override
  Future<List<TagSuggestion>> suggest(
    String query, {
    String? group,
    int limit = TagApiDefaults.suggestLimit,
  }) async {
    final lower = query.toLowerCase();
    return _catalog.suggestions
        .where(
          (s) =>
              s.label.contains(lower) ||
              s.labelEn.toLowerCase().contains(lower) ||
              s.tagRef.toLowerCase().contains(lower),
        )
        .take(limit)
        .toList(growable: false);
  }

  @override
  Future<TagValidationResult> validateRefs(List<String> tagRefs) async {
    final valid = <String>[];
    final invalid = <String>[];
    for (final ref in tagRefs) {
      if (_catalog.validTagRefs.contains(ref)) {
        valid.add(ref);
      } else {
        invalid.add(ref);
      }
    }
    return TagValidationResult(
      valid: valid,
      invalid: invalid,
      suggestions: const [],
    );
  }

  @override
  Future<List<TagSearchResult>> search(
    String query, {
    String? group,
    int limit = TagApiDefaults.searchLimit,
  }) async {
    final lower = query.toLowerCase();
    return _catalog.suggestions
        .where(
          (s) =>
              s.label.contains(lower) ||
              s.labelEn.toLowerCase().contains(lower),
        )
        .map(
          (s) => TagSearchResult(tagRef: s.tagRef, label: s.label, score: 1.0),
        )
        .take(limit)
        .toList(growable: false);
  }

  @override
  Future<List<RelatedTag>> related(
    String tagRef, {
    int limit = TagApiDefaults.relatedLimit,
  }) async {
    return _catalog.relatedTags.take(limit).toList(growable: false);
  }

  @override
  Future<List<TagObjectMatch>> searchByTags(
    List<String> tagRefs, {
    String? objectType,
    int limit = TagApiDefaults.searchLimit,
  }) async {
    return const <TagObjectMatch>[];
  }

  @override
  Future<List<TagCooccurrence>> cooccurrence({
    String? tagRef,
    int minCount = TagApiDefaults.minCooccurCount,
    int limit = TagApiDefaults.graphLimit,
  }) async {
    return _catalog.cooccurrences.take(limit).toList(growable: false);
  }

  @override
  Future<TagInvertedResult> invertedIndex(
    String tagRef, {
    String? objectType,
    int limit = TagApiDefaults.graphLimit,
  }) async {
    return TagInvertedResult(tag: tagRef, objectCount: 0, objects: const []);
  }

  @override
  Future<List<RelatedObject>> relatedObjects(
    String objectId, {
    String? objectType,
    int limit = TagApiDefaults.relatedLimit,
  }) async {
    return const <RelatedObject>[];
  }

  @override
  Future<List<SharedTagView>> sharedTags({
    required String objectAId,
    required String objectAType,
    required String objectBId,
    required String objectBType,
    int limit = TagApiDefaults.graphLimit,
  }) async {
    return _catalog.sharedTags.take(limit).toList(growable: false);
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
        '${command.tagRef}\u0000${command.action}\u0000${command.context ?? ''}';
    _byKey.putIfAbsent(key, () => command);
    return const TagFeedbackAck(accepted: true);
  }
}

final class _TagCatalogFixture {
  const _TagCatalogFixture({
    required this.childrenByParent,
    required this.dimensions,
    required this.suggestions,
    required this.validTagRefs,
    required this.relatedTags,
    required this.cooccurrences,
    required this.sharedTags,
  });

  final Map<String, List<TagChild>> childrenByParent;
  final List<TagDimension> dimensions;
  final List<TagSuggestion> suggestions;
  final Set<String> validTagRefs;
  final List<RelatedTag> relatedTags;
  final List<TagCooccurrence> cooccurrences;
  final List<SharedTagView> sharedTags;

  factory _TagCatalogFixture.fromJson(Map<String, dynamic> json) {
    final rawChildren =
        json['childrenByParent'] as Map<String, dynamic>? ?? const {};
    final childrenByParent = <String, List<TagChild>>{
      for (final entry in rawChildren.entries)
        entry.key: (entry.value as List)
            .map((item) => TagChild.fromJson(item as Map<String, dynamic>))
            .toList(growable: false),
    };
    List<T> parseList<T>(String key, T Function(Map<String, dynamic>) parse) {
      return ((json[key] as List?) ?? const [])
          .map((item) => parse(item as Map<String, dynamic>))
          .toList(growable: false);
    }

    return _TagCatalogFixture(
      childrenByParent: childrenByParent,
      dimensions: parseList('dimensions', TagDimension.fromJson),
      suggestions: parseList('suggestions', TagSuggestion.fromJson),
      validTagRefs: ((json['validTagRefs'] as List?) ?? const [])
          .map((item) => item.toString())
          .toSet(),
      relatedTags: parseList('relatedTags', RelatedTag.fromJson),
      cooccurrences: parseList('cooccurrences', TagCooccurrence.fromJson),
      sharedTags: parseList('sharedTags', SharedTagView.fromJson),
    );
  }
}
