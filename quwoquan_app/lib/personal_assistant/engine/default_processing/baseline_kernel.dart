import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/personal_assistant/engine/default_processing/answer_composer.dart';
import 'package:quwoquan_app/personal_assistant/engine/default_processing/evidence_evaluator.dart';
import 'package:quwoquan_app/personal_assistant/engine/default_processing/narrative_engine.dart';
import 'package:quwoquan_app/personal_assistant/engine/default_processing/problem_framer.dart';
import 'package:quwoquan_app/personal_assistant/engine/default_processing/retrieval_planner.dart';

class BaselineKernel {
  const BaselineKernel({
    this.problemFramer = const DefaultProblemFramer(),
    this.retrievalPlanner = const DefaultRetrievalPlanner(),
    this.evidenceEvaluator = const DefaultEvidenceEvaluator(),
    this.narrativeEngine = const NarrativeEngine(),
    this.answerComposer = const AnswerComposer(),
  });

  final DefaultProblemFramer problemFramer;
  final DefaultRetrievalPlanner retrievalPlanner;
  final DefaultEvidenceEvaluator evidenceEvaluator;
  final NarrativeEngine narrativeEngine;
  final AnswerComposer answerComposer;

  ProblemFrame frame(
    String query, {
    Map<String, dynamic> intentPayload = const <String, dynamic>{},
  }) => problemFramer.frame(query, intentPayload: intentPayload);

  Map<String, dynamic> buildIntentPayload(
    String query, {
    Map<String, dynamic> intentPayload = const <String, dynamic>{},
  }) {
    return frame(query, intentPayload: intentPayload).toIntentPayload();
  }

  BaselineRetrievalPlan? buildRetrievalPlan(
    String query,
    List<String> availableTools, {
    Map<String, dynamic> intentPayload = const <String, dynamic>{},
  }) {
    final problemFrame = frame(query, intentPayload: intentPayload);
    return retrievalPlanner.plan(
      frame: problemFrame,
      availableTools: availableTools,
    );
  }

  List<EvidenceLedgerEntry> buildEvidenceLedger({
    required String domainId,
    required List<Map<String, dynamic>> toolResults,
    required SlotStateSnapshot slotState,
    required Map<String, dynamic> retrievalPolicy,
  }) {
    return evidenceEvaluator.buildLedger(
      domainId: domainId,
      toolResults: toolResults,
      slotState: slotState,
      retrievalPolicy: retrievalPolicy,
    );
  }

  EvidenceEvaluationResult evaluateEvidence({
    required List<EvidenceLedgerEntry> ledger,
    bool evidenceRequired = false,
    bool authorityRequired = false,
    int freshnessHoursMax = 72,
    List<String> requiredDimensions = const <String>[],
    List<String> blockingDimensions = const <String>[],
  }) {
    return evidenceEvaluator.evaluate(
      ledger: ledger,
      evidenceRequired: evidenceRequired,
      authorityRequired: authorityRequired,
      freshnessHoursMax: freshnessHoursMax,
      requiredDimensions: requiredDimensions,
      blockingDimensions: blockingDimensions,
    );
  }

  BaselineComposedAnswer composeHeuristicAnswer({
    required String query,
    required List<Map<String, dynamic>> observations,
    Map<String, dynamic> intentPayload = const <String, dynamic>{},
  }) {
    return answerComposer.composeHeuristicAnswer(
      frame: frame(query, intentPayload: intentPayload),
      observations: observations,
    );
  }

  BaselineComposedAnswer composeFallbackAnswer({
    required String query,
    required SlotStateSnapshot slotState,
    required EvidenceEvaluationResult evidenceEvaluation,
    required String decisionMode,
    required List<String> missingCriticalSlots,
    required List<Map<String, dynamic>> toolErrors,
    Map<String, dynamic> intentPayload = const <String, dynamic>{},
  }) {
    return answerComposer.composeFallbackAnswer(
      frame: frame(query, intentPayload: intentPayload),
      slotState: slotState,
      evidenceEvaluation: evidenceEvaluation,
      decisionMode: decisionMode,
      missingCriticalSlots: missingCriticalSlots,
      toolErrors: toolErrors,
    );
  }
}
