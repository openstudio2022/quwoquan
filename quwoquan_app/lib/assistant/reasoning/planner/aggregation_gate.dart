import 'package:quwoquan_app/assistant/contracts/aggregation_state.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_plan_view.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/assistant/contracts/skill_run.dart';

/// Stateless evaluator that builds [AggregationState] from the current
/// set of [SkillRun]s. Extracted from the old monolithic owner to enable
/// independent testing and reuse in both single- and multi-agent paths.
class AggregationGate {
  const AggregationGate();

  AggregationState evaluate({
    required AssistantPlanView planView,
    required List<SkillRun> skillRuns,
    required Map<String, dynamic> answerPayload,
  }) {
    final dependencyMap = <String, AggregationDependencyChainDto>{
      for (final run in skillRuns)
        run.runId: AggregationDependencyChainDto(
          runIds: _normalizeStringList(
            (run.shell['dependencies'] as List?) ?? const <String>[],
          ),
        ),
    };
    final blockedBy = <String, AggregationBlockingSkillStateDto>{
      for (final run in skillRuns)
        if (!run.answerReady && run.domainId.isNotEmpty)
          run.domainId: AggregationBlockingSkillStateDto(
            stopReason: _resolveStopReason(run.stopReason),
            answerReady: run.answerReady,
          ),
    };
    final blockingSkills = blockedBy.keys.toList(growable: false);
    final allSkillsReady = skillRuns.isNotEmpty && blockingSkills.isEmpty;
    final canGivePartialAnswer =
        skillRuns.any((item) => item.answerReady) && blockingSkills.isNotEmpty;
    final turnDecision = AssistantTurnDecision.fromAnswerPayload(answerPayload);
    final clarificationNeeded =
        planView.clarificationNeeded ||
        turnDecision.messageKind == AssistantMessageKind.askUser;
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
          ? AggregationExpansionPlanDto(
              targetSkills: blockingSkills,
              policy: ContextScopeExpansionPolicy.expandScopeAndRequery,
              reasonCode: PlannerReasonCode.needMoreEvidence,
            )
          : const AggregationExpansionPlanDto(
              policy: ContextScopeExpansionPolicy.none,
            ),
      finalAnswerReady: allSkillsReady || canGivePartialAnswer,
      finalAnswerMode: allSkillsReady
          ? FinalAnswerMode.full
          : (canGivePartialAnswer
                ? FinalAnswerMode.boundedAnswer
                : (clarificationNeeded
                      ? FinalAnswerMode.clarify
                      : FinalAnswerMode.replan)),
      clarificationNeeded: clarificationNeeded,
      answerOwner: answerOwner,
      clarificationSource: clarificationSource,
      dependencies: dependencyMap,
    );
  }

  static FinalAnswerMode _resolveStopReason(String raw) {
    switch (raw.trim()) {
      case 'full':
        return FinalAnswerMode.full;
      case 'bounded_answer':
        return FinalAnswerMode.boundedAnswer;
      case 'clarify':
        return FinalAnswerMode.clarify;
      case 'replan':
        return FinalAnswerMode.replan;
      case 'retry':
        return FinalAnswerMode.retry;
      default:
        return FinalAnswerMode.blocked;
    }
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
