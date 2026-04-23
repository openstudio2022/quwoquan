import 'package:quwoquan_app/assistant/contracts/recall_result.dart';
import 'package:quwoquan_app/assistant/skill/domain/skill_manifest.dart';

/// Lightweight catalog observer.
///
/// Milestone 2 freezes routing as model-led, so recall no longer performs
/// keyword or rule-based shortlist filtering. We still return a structured
/// [RecallResult] for observability and future retrieval experiments, but the
/// planner always sees the full catalog.
class RecallCoordinator {
  const RecallCoordinator();

  /// Run recall on [userText] against [allSkills].
  RecallResult recall(
    String userText,
    List<PersonalAssistantSkillManifest> allSkills,
  ) {
    return RecallResult(
      topK: const <RecallCandidate>[],
      recallMethod: 'catalog_only',
      totalCandidates: allSkills.length,
      scores: const <String, double>{},
    );
  }
}
