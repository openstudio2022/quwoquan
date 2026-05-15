part of 'tag_repository.dart';

/// Mock 实现 — 不发 HTTP，返回本地 mock 数据
class MockTagRepository implements TagRepository {
  @override
  Future<List<TagDimension>> listDimensions() async => kMockTagDimensions;

  @override
  Future<List<TagSuggestion>> suggest(String query,
      {String? group, int limit = 20}) async {
    final lower = query.toLowerCase();
    return kMockTagSuggestions
        .where((s) =>
            s.label.contains(lower) ||
            s.labelEn.toLowerCase().contains(lower) ||
            s.tagRef.toLowerCase().contains(lower))
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
  Future<List<TagSearchResult>> search(String query,
      {String? group, int limit = 50}) async {
    final lower = query.toLowerCase();
    return kMockTagSuggestions
        .where((s) =>
            s.label.contains(lower) || s.labelEn.toLowerCase().contains(lower))
        .map((s) => TagSearchResult(tagRef: s.tagRef, label: s.label, score: 1.0))
        .take(limit)
        .toList();
  }

  @override
  Future<List<RelatedTag>> related(String tagRef, {int limit = 20}) async {
    return kMockRelatedTags.take(limit).toList();
  }

  @override
  Future<List<TagObjectMatch>> searchByTags(List<String> tagRefs,
      {String? objectType, int limit = 50}) async {
    return [];
  }

  @override
  Future<bool> feedback(String tagRef, String action, {String? context}) async {
    return true;
  }

  @override
  Future<List<TagCooccurrence>> cooccurrence(
      {String? tagRef, int minCount = 1, int limit = 50}) async {
    return kMockCooccurrences.take(limit).toList();
  }

  @override
  Future<TagInvertedResult> invertedIndex(String tagRef,
      {String? objectType, int limit = 50}) async {
    return TagInvertedResult(tag: tagRef, objectCount: 0, objects: []);
  }

  @override
  Future<List<RelatedObject>> relatedObjects(String objectId,
      {String? objectType, int limit = 20}) async {
    return [];
  }
}
