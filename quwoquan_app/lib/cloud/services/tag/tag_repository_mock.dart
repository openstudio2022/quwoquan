part of 'tag_repository.dart';

/// Mock 实现 — 不发 HTTP，返回本地 mock 数据
class MockTagRepository implements TagRepository {
  @override
  Future<List<TagChild>> listChildren(
    String parentTagRef, {
    int limit = TagApiDefaults.childrenLimit,
  }) async {
    return (kMockTagChildren[parentTagRef.trim()] ?? const <TagChild>[])
        .take(limit)
        .toList(growable: false);
  }

  @override
  Future<TagResolve> resolveTag(String tagRef) async {
    final ref = tagRef.trim();
    for (final children in kMockTagChildren.values) {
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
    for (final suggestion in kMockTagSuggestions) {
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
  Future<List<TagDimension>> listDimensions() async => kMockTagDimensions;

  @override
  Future<List<TagSuggestion>> suggest(
    String query, {
    String? group,
    int limit = TagApiDefaults.suggestLimit,
  }) async {
    final lower = query.toLowerCase();
    return kMockTagSuggestions
        .where(
          (s) =>
              s.label.contains(lower) ||
              s.labelEn.toLowerCase().contains(lower) ||
              s.tagRef.toLowerCase().contains(lower),
        )
        .take(limit)
        .toList();
  }

  @override
  Future<TagValidationResult> validateRefs(List<String> tagRefs) async {
    final valid = <String>[];
    final invalid = <String>[];
    for (final ref in tagRefs) {
      if (kMockValidTagRefs.contains(ref)) {
        valid.add(ref);
      } else {
        invalid.add(ref);
      }
    }
    return TagValidationResult(valid: valid, invalid: invalid, suggestions: []);
  }

  @override
  Future<List<TagSearchResult>> search(
    String query, {
    String? group,
    int limit = TagApiDefaults.searchLimit,
  }) async {
    final lower = query.toLowerCase();
    return kMockTagSuggestions
        .where(
          (s) =>
              s.label.contains(lower) ||
              s.labelEn.toLowerCase().contains(lower),
        )
        .map(
          (s) => TagSearchResult(tagRef: s.tagRef, label: s.label, score: 1.0),
        )
        .take(limit)
        .toList();
  }

  @override
  Future<List<RelatedTag>> related(
    String tagRef, {
    int limit = TagApiDefaults.relatedLimit,
  }) async {
    return kMockRelatedTags.take(limit).toList();
  }

  @override
  Future<List<TagObjectMatch>> searchByTags(
    List<String> tagRefs, {
    String? objectType,
    int limit = TagApiDefaults.searchLimit,
  }) async {
    return [];
  }

  @override
  Future<List<TagCooccurrence>> cooccurrence({
    String? tagRef,
    int minCount = TagApiDefaults.minCooccurCount,
    int limit = TagApiDefaults.graphLimit,
  }) async {
    return kMockCooccurrences.take(limit).toList();
  }

  @override
  Future<TagInvertedResult> invertedIndex(
    String tagRef, {
    String? objectType,
    int limit = TagApiDefaults.graphLimit,
  }) async {
    return TagInvertedResult(tag: tagRef, objectCount: 0, objects: []);
  }

  @override
  Future<List<RelatedObject>> relatedObjects(
    String objectId, {
    String? objectType,
    int limit = TagApiDefaults.relatedLimit,
  }) async {
    return [];
  }

  @override
  Future<List<SharedTagView>> sharedTags({
    required String objectAId,
    required String objectAType,
    required String objectBId,
    required String objectBType,
    int limit = TagApiDefaults.graphLimit,
  }) async {
    return kMockSharedTags.take(limit).toList();
  }
}
