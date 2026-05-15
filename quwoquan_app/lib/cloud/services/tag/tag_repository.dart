import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/services/tag/mock/tag_mock_data.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';

part 'tag_repository_mock.dart';
part 'tag_repository_remote.dart';

/// 标签 API 默认分页常量
class TagApiDefaults {
  TagApiDefaults._();
  static const int suggestLimit = 20;
  static const int searchLimit = 50;
  static const int relatedLimit = 20;
  static const int graphLimit = 50;
  static const int minCooccurCount = 1;
}

/// 标签域 request page ids（tag domain 尚未 codegen 时的手写常量）
class TagRequestPageIds {
  TagRequestPageIds._();
  static const String listDimensions = 'tag.list.dimensions';
  static const String suggest = 'tag.suggest';
  static const String validate = 'tag.validate';
  static const String search = 'tag.search';
  static const String related = 'tag.related';
  static const String searchByTags = 'tag.search.by.tags';
  static const String feedback = 'tag.feedback';
  static const String cooccurrence = 'tag.graph.cooccurrence';
  static const String invertedIndex = 'tag.graph.inverted.index';
  static const String relatedObjects = 'tag.graph.related.objects';
}

/// 标签体系 Repository（场景2: 内容创作 + 场景3: 推荐搜索 + 场景4: 关系图谱）
///
/// API 定义见 contracts/metadata/tag/service.yaml
abstract class TagRepository {
  // ── 场景2: 内容创作 ──────────────────────────────────────────
  Future<List<TagDimension>> listDimensions();
  Future<List<TagSuggestion>> suggest(String query,
      {String? group, int limit = TagApiDefaults.suggestLimit});
  Future<TagValidationResult> validateRefs(List<String> tagRefs);

  // ── 场景3: 推荐搜索 ──────────────────────────────────────────
  Future<List<TagSearchResult>> search(String query,
      {String? group, int limit = TagApiDefaults.searchLimit});
  Future<List<RelatedTag>> related(String tagRef,
      {int limit = TagApiDefaults.relatedLimit});
  Future<List<TagObjectMatch>> searchByTags(List<String> tagRefs,
      {String? objectType, int limit = TagApiDefaults.searchLimit});
  Future<bool> feedback(String tagRef, String action, {String? context});

  // ── 场景4: 关系图谱 ──────────────────────────────────────────
  Future<List<TagCooccurrence>> cooccurrence(
      {String? tagRef,
      int minCount = TagApiDefaults.minCooccurCount,
      int limit = TagApiDefaults.graphLimit});
  Future<TagInvertedResult> invertedIndex(String tagRef,
      {String? objectType, int limit = TagApiDefaults.graphLimit});
  Future<List<RelatedObject>> relatedObjects(String objectId,
      {String? objectType, int limit = TagApiDefaults.relatedLimit});
}

// ── DTO / Value Objects ──────────────────────────────────────────

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
        suggestions: (json['suggestions'] as List?)
                ?.map((e) => TagRefSuggestion.fromJson(e as Map<String, dynamic>))
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

  const TagSearchResult({required this.tagRef, required this.label, required this.score});

  factory TagSearchResult.fromJson(Map<String, dynamic> json) => TagSearchResult(
        tagRef: json['tagRef'] as String? ?? '',
        label: json['label'] as String? ?? '',
        score: (json['score'] as num?)?.toDouble() ?? 0.0,
      );
}

class RelatedTag {
  final String tagRef;
  final String label;
  final int cooccurCount;

  const RelatedTag({required this.tagRef, required this.label, required this.cooccurCount});

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

  const TagCooccurrence({required this.tagA, required this.tagB, required this.cooccurCount});

  factory TagCooccurrence.fromJson(Map<String, dynamic> json) => TagCooccurrence(
        tagA: json['tagA'] as String? ?? '',
        tagB: json['tagB'] as String? ?? '',
        cooccurCount: json['cooccurCount'] as int? ?? 0,
      );
}

class TagInvertedResult {
  final String tag;
  final int objectCount;
  final List<String> objects;

  const TagInvertedResult({required this.tag, required this.objectCount, required this.objects});

  factory TagInvertedResult.fromJson(Map<String, dynamic> json) => TagInvertedResult(
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
