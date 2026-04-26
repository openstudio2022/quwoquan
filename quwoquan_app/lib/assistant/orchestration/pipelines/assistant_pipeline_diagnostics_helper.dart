import 'package:quwoquan_app/assistant/contracts/assistant_subagent_run_record.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_tool_result_row.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_diagnostics_models.dart';

class AssistantPipelineDiagnosticsHelper {
  const AssistantPipelineDiagnosticsHelper();

  Map<String, dynamic> buildPhaseOneRoutingDiagnostics({
    required String phaseOneRoute,
    required bool synthesisReadinessReady,
    required String synthesisReadinessReason,
    required String rawDirectAnswerReason,
    required String directAnswerReason,
    required bool directAnswerShouldSkipSynthesis,
    required bool phaseOneRecoveryApplied,
    required bool phaseOneModelRepairApplied,
    required bool phaseOneModelRepairAttempted,
    required bool phaseOneModelRepairProducedText,
    required String phaseOneModelRepairFailureCode,
    required bool phaseOneParsedContractTurn,
    required String phaseOneNextAction,
    required String phaseOneMessageKind,
    required String phaseOnePhaseId,
    required String phaseOneActionCode,
    required String phaseOneReasonCode,
    required bool phaseOneHasRenderableContent,
    required int phaseOneExplicitSkillRunPlanCount,
    required int phaseOneDerivedSkillRunPlanCount,
    required int phaseOneSkillRunPlanCount,
    required bool typedExecutionReady,
    required String phaseOneSkillRunPlanSource,
    required bool phaseOneExecutionSignalsPresent,
    required bool phaseOneContinuationCarryover,
    required bool allowPhaseOneContractRepair,
    required List<Map<String, dynamic>> phaseOneSkillRunPlans,
    required String templateVersionUsed,
  }) {
    return <String, dynamic>{
      'route': phaseOneRoute,
      'synthesisReadinessReady': synthesisReadinessReady,
      'synthesisReadinessReason': synthesisReadinessReason,
      'rawDirectAnswerReason': rawDirectAnswerReason,
      'directAnswerReason': directAnswerReason,
      'directAnswerShouldSkipSynthesis': directAnswerShouldSkipSynthesis,
      'phaseOneRecoveryApplied': phaseOneRecoveryApplied,
      'phaseOneModelRepairApplied': phaseOneModelRepairApplied,
      'phaseOneModelRepairAttempted': phaseOneModelRepairAttempted,
      'phaseOneModelRepairProducedText': phaseOneModelRepairProducedText,
      'phaseOneModelRepairFailureCode': phaseOneModelRepairFailureCode,
      'phaseOneParsedContractTurn': phaseOneParsedContractTurn,
      'phaseOneNextAction': phaseOneNextAction,
      'phaseOneMessageKind': phaseOneMessageKind,
      'phaseOnePhaseId': phaseOnePhaseId,
      'phaseOneActionCode': phaseOneActionCode,
      'phaseOneReasonCode': phaseOneReasonCode,
      'phaseOneHasRenderableContent': phaseOneHasRenderableContent,
      'phaseOneExplicitSkillRunPlanCount': phaseOneExplicitSkillRunPlanCount,
      'phaseOneDerivedSkillRunPlanCount': phaseOneDerivedSkillRunPlanCount,
      'phaseOneSkillRunPlanCount': phaseOneSkillRunPlanCount,
      'typedExecutionReady': typedExecutionReady,
      'phaseOneSkillRunPlanSource': phaseOneSkillRunPlanSource,
      'phaseOneExecutionSignalsPresent': phaseOneExecutionSignalsPresent,
      'phaseOneContinuationCarryover': phaseOneContinuationCarryover,
      'allowPhaseOneContractRepair': allowPhaseOneContractRepair,
      'phaseOneSkillRunPlans': phaseOneSkillRunPlans,
      'templateVersionUsed': templateVersionUsed,
    };
  }

  List<AssistantToolObservation> buildToolObservations({
    required List<AssistantToolResultRow> toolResults,
    required List<Map<String, dynamic>> toolErrors,
  }) {
    return <AssistantToolObservation>[
      ...toolResults.map(
        (item) => AssistantToolObservation(
          ok: true,
          message: item.message,
          data: item.data,
          toolCallId: item.toolCallId,
        ),
      ),
      ...toolErrors.map(
        (item) => AssistantToolObservation(
          ok: false,
          message: item['message'] ?? '',
          data:
              (item['data'] as Map?)?.cast<String, dynamic>() ??
              const <String, dynamic>{},
          toolCallId: item['toolCallId'] ?? '',
        ),
      ),
    ];
  }

  AssistantQualityMetrics buildQualityMetrics({
    required bool decisionParseSuccess,
    required bool renderFallbackFlag,
    required bool heuristicFallbackUsed,
    required bool evidenceSufficient,
    required bool freshnessSatisfied,
    required bool freshnessRequired,
    required bool criticalSlotsResolved,
    required bool answerGateReady,
    required String answerGateReasonCode,
  }) {
    return AssistantQualityMetrics(
      decisionParseSuccess: decisionParseSuccess,
      renderFallback: renderFallbackFlag,
      heuristicFallbackUsed: heuristicFallbackUsed,
      evidenceSufficient: evidenceSufficient,
      freshnessSatisfied: freshnessSatisfied || !freshnessRequired,
      criticalSlotsResolved: criticalSlotsResolved,
      answerGateReady: answerGateReady,
      answerGateReasonCode: answerGateReasonCode,
    );
  }

  List<AssistantUiTimelineEntry> buildUiTimeline({
    required List<AssistantSubagentRunRecord> subagentRuns,
  }) {
    return <AssistantUiTimelineEntry>[
      for (final run in subagentRuns)
        AssistantUiTimelineEntry(
          event: 'subagent_progress',
          subagentId: run.subagentId,
          status: run.status.isNotEmpty ? run.status : 'unknown',
          summary: run.localSummary,
          acceptedEvidenceCount: run.acceptedEvidence.isNotEmpty
              ? run.acceptedEvidence.length
              : run.references.length,
          failureReason: run.failureReason,
          nextAction: run.nextAction,
        ),
    ];
  }
}
