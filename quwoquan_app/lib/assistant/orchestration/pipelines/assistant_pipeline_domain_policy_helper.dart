import 'package:quwoquan_app/assistant/contracts/assistant_typed_turn_decision_contract.dart';
import 'package:quwoquan_app/assistant/contracts/dialogue_round_script.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/skill_run.dart';
import 'package:quwoquan_app/assistant/contracts/slot_schema.dart';
import 'package:quwoquan_app/assistant/context/assembly/evidence_evaluator.dart';
import 'package:quwoquan_app/assistant/skill/domain/skill_manifest.dart';

DomainPolicyBundle buildDomainPolicyBundle({
  required String domainId,
  required SkillExecutionShell skillExecutionShell,
  required SlotSchema slotSchema,
  required DialogueRoundScript dialogueRoundScript,
  required Map<String, dynamic> retrievalPolicy,
  required EvidenceEvaluationResult evidenceEvaluation,
  required AssistantTypedTurnDecision stateDecision,
  DomainPolicyBundle? previous,
}) {
  return DomainPolicyBundle(
    domainId: domainId,
    executionPolicy: <String, dynamic>{
      ...?previous?.executionPolicy,
      'problemClass': skillExecutionShell.problemClass,
      'maxIterations': skillExecutionShell.maxIterations,
      'toolBudget': skillExecutionShell.toolBudget,
      'variantBudget': skillExecutionShell.variantBudget,
      'reflectionBudget': skillExecutionShell.reflectionBudget,
      'providerPolicy': skillExecutionShell.providerPolicy,
      'preferredProviders': skillExecutionShell.preferredProviders,
      'freshnessHoursMax': skillExecutionShell.freshnessHoursMax,
      'finalAnswerMode': stateDecision.finalAnswerModeWireName,
      'nextAction': stateDecision.nextActionWireName,
    },
    slotSchema: <String, dynamic>{
      ...?previous?.slotSchema,
      ...slotSchema.toSchemaMap(),
    },
    dialoguePolicy: <String, dynamic>{
      ...?previous?.dialoguePolicy,
      'currentStateId': dialogueRoundScript.currentStateId,
      'suggestedNextStateId': dialogueRoundScript.suggestedNextStateId,
      'detectedEvent': dialogueRoundScript.detectedEvent,
      'requiredFieldsForNextState':
          dialogueRoundScript.requiredFieldsForNextState,
      'missingCriticalSlots': stateDecision.missingCriticalSlots,
      'askUser': stateDecision.askUserData,
    },
    authorityPolicy: <String, dynamic>{
      ...?previous?.authorityPolicy,
      'authorityRequired': retrievalPolicy['authorityRequired'] == true,
      'authoritySatisfied': evidenceEvaluation.authoritySatisfied,
      'freshnessSatisfied': evidenceEvaluation.freshnessSatisfied,
    },
    retrievalPolicy: <String, dynamic>{
      ...?previous?.retrievalPolicy,
      ...retrievalPolicy,
      'coveredDimensions': evidenceEvaluation.coveredDimensions,
      'missingDimensions': evidenceEvaluation.missingDimensions,
      'coveredSearchPlanIds': evidenceEvaluation.coveredSearchPlanIds,
    },
    answerPolicy: <String, dynamic>{
      ...?previous?.answerPolicy,
      'answerEligibility': stateDecision.answerEligibilityWireName,
      'finalAnswerMode': stateDecision.finalAnswerModeWireName,
      'qualityGates': stateDecision.qualityGatesData,
    },
    narrativePolicy: <String, dynamic>{
      ...?previous?.narrativePolicy,
      'style': 'user_facing',
      'referencesMode': 'inline_links',
      'fallbackReasoning': evidenceEvaluation.summary,
    },
  );
}

List<SkillRun> finalizeSkillRuns({
  required List<SkillRun> skillRuns,
  required String primaryDomainId,
  required SlotStateSnapshot slotState,
  required bool answerReady,
  required String stopReason,
  required List<Map<String, dynamic>> references,
  required String resultSummary,
}) {
  return skillRuns
      .map((item) {
        if (item.domainId != primaryDomainId) return item;
        return SkillRun(
          runId: item.runId,
          domainId: item.domainId,
          goal: item.goal,
          problemClass: item.problemClass,
          shell: item.shell,
          slotState: slotState.toJson(),
          answerReady: answerReady,
          stopReason: stopReason,
          references: references,
          resultSummary: resultSummary,
        );
      })
      .toList(growable: false);
}
