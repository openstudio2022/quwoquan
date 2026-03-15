import 'package:quwoquan_app/assistant/contracts/recall_result.dart';
import 'package:quwoquan_app/assistant/internal_legacy/skills/skill_manifest.dart';
import 'package:quwoquan_app/assistant/internal_legacy/skills/skill_router.dart';

/// Rule-based, non-LLM recall layer that pre-filters the full skill catalog
/// into a top-K shortlist before feeding it to the planner prompt.
///
/// This sits between the raw user query and the planner, reducing the token
/// overhead when the catalog grows to hundreds or thousands of skills.
///
/// Future: swap the rule engine with a vector index or hybrid retriever
/// without changing the contract (returns [RecallResult]).
class RecallCoordinator {
  RecallCoordinator({
    PersonalAssistantSkillRouter? router,
    this.maxTopK = 5,
  }) : _router = router ?? const PersonalAssistantSkillRouter();

  final PersonalAssistantSkillRouter _router;
  final int maxTopK;

  /// Run recall on [userText] against [allSkills].
  RecallResult recall(
    String userText,
    List<PersonalAssistantSkillManifest> allSkills,
  ) {
    if (allSkills.isEmpty) {
      return const RecallResult(
        topK: <RecallCandidate>[],
        recallMethod: 'rule',
      );
    }

    final scored = <_ScoredSkill>[];

    for (final skill in allSkills) {
      final score = _scoreSkill(userText, skill);
      if (score > 0) {
        scored.add(_ScoredSkill(skill: skill, score: score));
      }
    }

    scored.sort((a, b) => b.score.compareTo(a.score));

    final topK = scored.take(maxTopK).map((s) {
      return RecallCandidate(
        domainId: s.skill.domainId,
        description: s.skill.description,
        mode: (s.skill.frontmatter['mode'] as String?)?.trim() ?? 'qa',
        score: s.score,
        matchReason: s.reason,
      );
    }).toList(growable: false);

    final scores = <String, double>{};
    for (final s in scored) {
      scores[s.skill.domainId] = s.score;
    }

    final hasFallback =
        topK.any((c) => c.domainId == 'fallback_general_search');
    if (!hasFallback && topK.isEmpty) {
      final fallback = allSkills.where(
        (s) => s.domainId == 'fallback_general_search',
      );
      if (fallback.isNotEmpty) {
        final fb = fallback.first;
        return RecallResult(
          topK: <RecallCandidate>[
            RecallCandidate(
              domainId: fb.domainId,
              description: fb.description,
              mode: 'qa',
              score: 0.1,
              matchReason: 'fallback',
            ),
          ],
          recallMethod: 'rule',
          totalCandidates: allSkills.length,
          scores: scores,
        );
      }
    }

    return RecallResult(
      topK: topK,
      recallMethod: 'rule',
      totalCandidates: allSkills.length,
      scores: scores,
    );
  }

  double _scoreSkill(String userText, PersonalAssistantSkillManifest skill) {
    double score = 0;

    final matched = _router.resolveSkill(userText, [skill]);
    if (matched != null) {
      score += 0.6;
    }

    final normalized = userText.toLowerCase().trim();
    final domainId = skill.domainId.toLowerCase().trim();
    if (domainId.isNotEmpty && normalized.contains(domainId)) {
      score += 0.2;
    }

    final desc = skill.description.toLowerCase();
    final words = normalized
        .split(RegExp(r'[\s,，。！？!?]+'))
        .where((w) => w.length >= 2);
    for (final w in words) {
      if (desc.contains(w)) {
        score += 0.1;
      }
    }

    return score.clamp(0.0, 1.0);
  }
}

class _ScoredSkill {
  _ScoredSkill({required this.skill, required this.score})
      : reason = score >= 0.6
            ? 'trigger_match'
            : score >= 0.3
                ? 'keyword_overlap'
                : 'description_overlap';

  final PersonalAssistantSkillManifest skill;
  final double score;
  final String reason;
}
