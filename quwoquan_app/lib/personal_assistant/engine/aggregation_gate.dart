import 'package:quwoquan_app/personal_assistant/contracts/aggregation_state.dart';
import 'package:quwoquan_app/personal_assistant/contracts/intent_graph.dart';
import 'package:quwoquan_app/personal_assistant/contracts/skill_run.dart';

/// Stateless evaluator that builds [AggregationState] from the current
/// set of [SkillRun]s. Extracted from the monolithic agent_loop to enable
/// independent testing and reuse in both single- and multi-agent paths.
class AggregationGate {
  const AggregationGate();

  AggregationState evaluate({
    required IntentGraph intentGraph,
    required List<SkillRun> skillRuns,
    required Map<String, dynamic> answerPayload,
  }) {
    final dependencyMap = <String, List<String>>{
      for (final run in skillRuns)
        run.runId: _normalizeStringList(
          (run.shell['dependencies'] as List?) ?? const <String>[],
        ),
    };
    final blockedBy = <String, String>{
      for (final run in skillRuns)
        if (!run.answerReady && run.domainId.isNotEmpty)
          run.domainId: run.stopReason.isNotEmpty
              ? run.stopReason
              : 'not_ready',
    };
    final blockingSkills = blockedBy.keys.toList(growable: false);
    final allSkillsReady = skillRuns.isNotEmpty && blockingSkills.isEmpty;
    final canGivePartialAnswer =
        skillRuns.any((item) => item.answerReady) && blockingSkills.isNotEmpty;
    final clarificationNeeded =
        intentGraph.clarificationNeeded ||
        ((answerPayload['messageKind'] as String?)?.trim() ?? '') == 'ask_user';
    final needExpansion =
        !allSkillsReady && !canGivePartialAnswer && !clarificationNeeded;
    final answerOwner = skillRuns
        .firstWhere(
          (item) => item.answerReady,
          orElse: () => skillRuns.isNotEmpty
              ? skillRuns.first
              : const SkillRun(
                  runId: '',
                  domainId: '',
                  goal: '',
                  problemClass: '',
                ),
        )
        .runId;
    final clarificationSource = clarificationNeeded && blockingSkills.isNotEmpty
        ? blockingSkills.first
        : '';
    return AggregationState(
      allSkillsReady: allSkillsReady,
      blockingSkills: blockingSkills,
      blockedBy: blockedBy,
      canGivePartialAnswer: canGivePartialAnswer,
      needExpansion: needExpansion,
      expansionPlan: needExpansion
          ? <String, dynamic>{
              'targetSkills': blockingSkills,
              'strategy': 'broaden_or_retry',
            }
          : const <String, dynamic>{},
      finalAnswerReady: allSkillsReady || canGivePartialAnswer,
      finalAnswerMode: allSkillsReady
          ? 'full'
          : (canGivePartialAnswer
                ? 'partial'
                : (clarificationNeeded ? 'clarify' : 'expansion')),
      clarificationNeeded: clarificationNeeded,
      answerOwner: answerOwner,
      clarificationSource: clarificationSource,
      dependencies: dependencyMap,
    );
  }

  static List<String> _normalizeStringList(Object? value) {
    if (value is List) {
      return value
          .whereType<String>()
          .map((item) => item.trim())
          .where((item) => item.isNotEmpty)
          .toList(growable: false);
    }
    if (value is String && value.trim().isNotEmpty) {
      return <String>[value.trim()];
    }
    return const <String>[];
  }
}
