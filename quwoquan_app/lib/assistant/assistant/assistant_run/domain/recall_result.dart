export 'package:quwoquan_app/assistant/generated/contracts/recall_result.g.dart';

/// Result of the non-LLM recall layer that pre-filters the skill catalog
/// before feeding it to the planner prompt.
class RecallResult {
  const RecallResult({
    required this.topK,
    this.recallMethod = 'rule',
    this.totalCandidates = 0,
    this.scores = const <String, double>{},
  });

  /// Top-K skill IDs recommended for the planner, in relevance order.
  final List<RecallCandidate> topK;

  /// How the recall was performed: `rule`, `keyword`, `semantic`, `hybrid`.
  final String recallMethod;

  /// Total number of candidate skills evaluated.
  final int totalCandidates;

  /// Per-skill relevance scores (0..1) — for observability, not used at
  /// runtime.
  final Map<String, double> scores;

  bool get isEmpty => topK.isEmpty;

  bool hasNonFallbackCandidate({
    String fallbackDomainId = 'fallback_general_search',
  }) {
    final normalizedFallback = fallbackDomainId.trim();
    return topK.any(
      (candidate) =>
          candidate.domainId.trim().isNotEmpty &&
          candidate.domainId.trim() != normalizedFallback,
    );
  }

  /// Build a compact catalog prompt containing only the recalled skills.
  String toPromptSnippet() {
    if (topK.isEmpty) return '（无匹配技能，使用默认通用能力）';
    final buf = StringBuffer();
    for (final c in topK) {
      buf.writeln('- ${c.domainId}: ${c.description} [mode=${c.mode}]');
    }
    return buf.toString().trimRight();
  }

  /// Build the planner-visible skill catalog in a model-first way.
  ///
  /// Recall is only an advisory ranking hint. The planner must still see the
  /// full catalog so that low-recall or recall-miss situations do not block the
  /// model from selecting the correct skill.
  String toPlannerSkillCatalog({
    required String fullCatalog,
    String fallbackDomainId = 'fallback_general_search',
  }) {
    final normalizedFullCatalog = fullCatalog.trim();
    if (normalizedFullCatalog.isEmpty) {
      return toPromptSnippet();
    }
    if (!hasNonFallbackCandidate(fallbackDomainId: fallbackDomainId)) {
      return normalizedFullCatalog;
    }
    final advisoryCandidates = topK
        .where((candidate) {
          final domainId = candidate.domainId.trim();
          return domainId.isNotEmpty && domainId != fallbackDomainId.trim();
        })
        .toList(growable: false);
    if (advisoryCandidates.isEmpty) {
      return normalizedFullCatalog;
    }
    final buf = StringBuffer();
    buf.writeln('优先候选技能（仅作参考，不限制最终选择）：');
    for (final candidate in advisoryCandidates) {
      buf.writeln(
        '- ${candidate.domainId}: ${candidate.description} [mode=${candidate.mode}]',
      );
    }
    buf.writeln();
    buf.writeln('完整技能目录：');
    buf.write(normalizedFullCatalog);
    return buf.toString().trimRight();
  }

  Map<String, dynamic> toJson() => <String, dynamic>{
    'topK': topK.map((c) => c.toJson()).toList(growable: false),
    'recallMethod': recallMethod,
    'totalCandidates': totalCandidates,
    'scores': scores,
  };

  factory RecallResult.fromJson(Map<String, dynamic> json) {
    return RecallResult(
      topK:
          (json['topK'] as List?)
              ?.whereType<Map>()
              .map((m) => RecallCandidate.fromJson(m.cast<String, dynamic>()))
              .toList(growable: false) ??
          const <RecallCandidate>[],
      recallMethod: (json['recallMethod'] as String?)?.trim() ?? 'rule',
      totalCandidates: (json['totalCandidates'] as num?)?.toInt() ?? 0,
      scores:
          (json['scores'] as Map?)?.map(
            (k, v) => MapEntry(k.toString(), (v as num).toDouble()),
          ) ??
          const <String, double>{},
    );
  }
}

class RecallCandidate {
  const RecallCandidate({
    required this.domainId,
    required this.description,
    this.mode = 'qa',
    this.score = 0.0,
    this.matchReason = '',
  });

  final String domainId;
  final String description;
  final String mode;
  final double score;
  final String matchReason;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'domainId': domainId,
    'description': description,
    'mode': mode,
    'score': score,
    'matchReason': matchReason,
  };

  factory RecallCandidate.fromJson(Map<String, dynamic> json) {
    return RecallCandidate(
      domainId: (json['domainId'] as String?)?.trim() ?? '',
      description: (json['description'] as String?)?.trim() ?? '',
      mode: (json['mode'] as String?)?.trim() ?? 'qa',
      score: (json['score'] as num?)?.toDouble() ?? 0.0,
      matchReason: (json['matchReason'] as String?)?.trim() ?? '',
    );
  }
}
