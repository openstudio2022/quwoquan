import 'package:quwoquan_app/assistant/contracts/assistant_structured_response_wire.dart';

class AssistantPhaseOneRoutingDiagnostics {
  const AssistantPhaseOneRoutingDiagnostics({
    required this.phaseOneRoute,
    required this.synthesisReadinessReady,
    required this.synthesisReadinessReason,
    required this.rawDirectAnswerReason,
    required this.directAnswerReason,
    required this.directAnswerShouldSkipSynthesis,
    required this.phaseOneRecoveryApplied,
    required this.phaseOneModelRepairApplied,
    required this.phaseOneModelRepairAttempted,
    required this.phaseOneModelRepairProducedText,
    required this.phaseOneModelRepairFailureCode,
    required this.phaseOneParsedContractTurn,
    required this.phaseOneNextAction,
    required this.phaseOneMessageKind,
    required this.phaseOnePhaseId,
    required this.phaseOneActionCode,
    required this.phaseOneReasonCode,
    required this.phaseOneHasRenderableContent,
    required this.phaseOneExplicitSkillRunPlanCount,
    required this.phaseOneDerivedSkillRunPlanCount,
    required this.phaseOneSkillRunPlanCount,
    required this.typedExecutionReady,
    required this.phaseOneSkillRunPlanSource,
    required this.phaseOneExecutionSignalsPresent,
    required this.phaseOneContinuationCarryover,
    required this.allowPhaseOneContractRepair,
    required this.phaseOneSkillRunPlans,
    required this.templateVersionUsed,
  });

  final String phaseOneRoute;
  final bool synthesisReadinessReady;
  final String synthesisReadinessReason;
  final String rawDirectAnswerReason;
  final String directAnswerReason;
  final bool directAnswerShouldSkipSynthesis;
  final bool phaseOneRecoveryApplied;
  final bool phaseOneModelRepairApplied;
  final bool phaseOneModelRepairAttempted;
  final bool phaseOneModelRepairProducedText;
  final String phaseOneModelRepairFailureCode;
  final bool phaseOneParsedContractTurn;
  final String phaseOneNextAction;
  final String phaseOneMessageKind;
  final String phaseOnePhaseId;
  final String phaseOneActionCode;
  final String phaseOneReasonCode;
  final bool phaseOneHasRenderableContent;
  final int phaseOneExplicitSkillRunPlanCount;
  final int phaseOneDerivedSkillRunPlanCount;
  final int phaseOneSkillRunPlanCount;
  final bool typedExecutionReady;
  final String phaseOneSkillRunPlanSource;
  final bool phaseOneExecutionSignalsPresent;
  final bool phaseOneContinuationCarryover;
  final bool allowPhaseOneContractRepair;
  final List<Map<String, dynamic>> phaseOneSkillRunPlans;
  final String templateVersionUsed;

  Map<String, dynamic> toJson() => <String, dynamic>{
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

class AssistantToolObservation {
  const AssistantToolObservation({
    required this.ok,
    required this.message,
    required this.data,
    required this.toolCallId,
  });

  final bool ok;
  final String message;
  final Map<String, dynamic> data;
  final String toolCallId;

  Map<String, dynamic> toJson() => <String, dynamic>{
        'ok': ok,
        'message': message,
        'data': data,
        'toolCallId': toolCallId,
      };
}

class AssistantUiTimelineEntry {
  const AssistantUiTimelineEntry({
    required this.event,
    required this.subagentId,
    required this.status,
    this.summary = '',
    this.acceptedEvidenceCount = 0,
    this.failureReason = '',
    this.nextAction = '',
  });

  final String event;
  final String subagentId;
  final String status;
  final String summary;
  final int acceptedEvidenceCount;
  final String failureReason;
  final String nextAction;

  Map<String, dynamic> toJson() => <String, dynamic>{
        'event': event,
        'subagentId': subagentId,
        'status': status,
        'summary': summary,
        'acceptedEvidenceCount': acceptedEvidenceCount,
        'failureReason': failureReason,
        'nextAction': nextAction,
      };
}

class AssistantQualityMetrics {
  const AssistantQualityMetrics({
    required this.decisionParseSuccess,
    required this.renderFallback,
    required this.heuristicFallbackUsed,
    required this.evidenceSufficient,
    required this.freshnessSatisfied,
    required this.criticalSlotsResolved,
    required this.answerGateReady,
    required this.answerGateReasonCode,
  });

  final bool decisionParseSuccess;
  final bool renderFallback;
  final bool heuristicFallbackUsed;
  final bool evidenceSufficient;
  final bool freshnessSatisfied;
  final bool criticalSlotsResolved;
  final bool answerGateReady;
  final String answerGateReasonCode;

  Map<String, dynamic> toJson() => <String, dynamic>{
        AssistantStructuredResponseWireFields.decisionParseSuccess:
            decisionParseSuccess,
        'renderFallback': renderFallback,
        'heuristicFallbackUsed': heuristicFallbackUsed,
        'evidenceSufficient': evidenceSufficient,
        'freshnessSatisfied': freshnessSatisfied,
        'criticalSlotsResolved': criticalSlotsResolved,
        'answerGateReady': answerGateReady,
        'answerGateReasonCode': answerGateReasonCode,
      };
}
