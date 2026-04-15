import 'package:quwoquan_app/assistant/contracts/aggregation_state.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/context_assembly_result.dart';
import 'package:quwoquan_app/assistant/contracts/context_continuity_policy.dart';
import 'package:quwoquan_app/assistant/contracts/dialogue_round_script.dart';
import 'package:quwoquan_app/assistant/contracts/intent_graph.dart';
import 'package:quwoquan_app/assistant/contracts/query_task_contract.dart';
import 'package:quwoquan_app/assistant/contracts/recall_result.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/subagent_plan.dart';
import 'package:quwoquan_app/assistant/contracts/synthesis_readiness_result.dart';
import 'package:quwoquan_app/assistant/contracts/conversation_state_decision.dart';
import 'package:quwoquan_app/assistant/context/assembly/evidence_evaluator.dart';
import 'package:quwoquan_app/assistant/protocol/run_response.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/synthesis_draft.dart';
import 'package:quwoquan_app/assistant/orchestration/state/execution_phase_snapshot.dart';
import 'package:quwoquan_app/assistant/reasoning/planner/mode_decider.dart';
import 'package:quwoquan_app/assistant/skill/domain/skill_manifest.dart';

class AssistantBootstrapContext {
  const AssistantBootstrapContext({
    this.sessionId = 'default',
    this.latestUserQuery = '',
    this.historySummary = '',
    // ASSISTANT_WEAK_TYPE: LLM serde boundary — session messages
    this.recentDialogueRounds = const <Map<String, dynamic>>[],
    this.recentDialogueRoundsLimit = 5,
    this.recalledTexts = const <String>[],
    this.previousIntentGraph,
    this.previousAnswerSummary = '',
    this.previousUnderstandingSnapshot =
        const RunArtifactsUnderstandingSnapshot(),
    this.previousAnswerProcessing = const RunArtifactsAnswerProcessing(),
    this.historicalThinkingSnapshot =
        const RunArtifactsHistoricalThinkingSnapshot(),
    this.providerReasoningContinuation = '',
    this.contextContinuityPolicy = const ContextContinuityPolicy(),
    this.continuityOverrideSlots = const <String, dynamic>{},
    this.recallResult = const RecallResult(topK: <RecallCandidate>[]),
    this.forceRefreshCatalog = false,
    this.domainCatalog = const <String>[],
    this.domainCatalogVersion = '',
    this.fullSkillCatalog = '',
    this.skillCatalog = '',
  });

  final String sessionId;
  final String latestUserQuery;
  final String historySummary;
  // ASSISTANT_WEAK_TYPE: LLM serde boundary — session message list from persistence
  final List<Map<String, dynamic>> recentDialogueRounds;
  final int recentDialogueRoundsLimit;
  final List<String> recalledTexts;
  final IntentGraph? previousIntentGraph;
  final String previousAnswerSummary;
  final RunArtifactsUnderstandingSnapshot previousUnderstandingSnapshot;
  final RunArtifactsAnswerProcessing previousAnswerProcessing;
  final RunArtifactsHistoricalThinkingSnapshot historicalThinkingSnapshot;
  final String providerReasoningContinuation;
  final ContextContinuityPolicy contextContinuityPolicy;
  // ASSISTANT_WEAK_TYPE: LLM serde boundary — continuity slot overrides from model
  final Map<String, dynamic> continuityOverrideSlots;
  final RecallResult recallResult;
  final bool forceRefreshCatalog;
  final List<String> domainCatalog;
  final String domainCatalogVersion;
  final String fullSkillCatalog;
  final String skillCatalog;

  AssistantBootstrapContext copyWith({
    String? sessionId,
    String? latestUserQuery,
    String? historySummary,
    List<Map<String, dynamic>>? recentDialogueRounds,
    int? recentDialogueRoundsLimit,
    List<String>? recalledTexts,
    IntentGraph? previousIntentGraph,
    String? previousAnswerSummary,
    RunArtifactsUnderstandingSnapshot? previousUnderstandingSnapshot,
    RunArtifactsAnswerProcessing? previousAnswerProcessing,
    RunArtifactsHistoricalThinkingSnapshot? historicalThinkingSnapshot,
    String? providerReasoningContinuation,
    ContextContinuityPolicy? contextContinuityPolicy,
    // ASSISTANT_WEAK_TYPE: LLM serde boundary — continuity overrides
    Map<String, dynamic>? continuityOverrideSlots,
    RecallResult? recallResult,
    bool? forceRefreshCatalog,
    List<String>? domainCatalog,
    String? domainCatalogVersion,
    String? fullSkillCatalog,
    String? skillCatalog,
  }) {
    return AssistantBootstrapContext(
      sessionId: sessionId ?? this.sessionId,
      latestUserQuery: latestUserQuery ?? this.latestUserQuery,
      historySummary: historySummary ?? this.historySummary,
      recentDialogueRounds: recentDialogueRounds ?? this.recentDialogueRounds,
      recentDialogueRoundsLimit:
          recentDialogueRoundsLimit ?? this.recentDialogueRoundsLimit,
      recalledTexts: recalledTexts ?? this.recalledTexts,
      previousIntentGraph: previousIntentGraph ?? this.previousIntentGraph,
      previousAnswerSummary:
          previousAnswerSummary ?? this.previousAnswerSummary,
      previousUnderstandingSnapshot:
          previousUnderstandingSnapshot ?? this.previousUnderstandingSnapshot,
      previousAnswerProcessing:
          previousAnswerProcessing ?? this.previousAnswerProcessing,
      historicalThinkingSnapshot:
          historicalThinkingSnapshot ?? this.historicalThinkingSnapshot,
      providerReasoningContinuation:
          providerReasoningContinuation ?? this.providerReasoningContinuation,
      contextContinuityPolicy:
          contextContinuityPolicy ?? this.contextContinuityPolicy,
      continuityOverrideSlots:
          continuityOverrideSlots ?? this.continuityOverrideSlots,
      recallResult: recallResult ?? this.recallResult,
      forceRefreshCatalog: forceRefreshCatalog ?? this.forceRefreshCatalog,
      domainCatalog: domainCatalog ?? this.domainCatalog,
      domainCatalogVersion: domainCatalogVersion ?? this.domainCatalogVersion,
      fullSkillCatalog: fullSkillCatalog ?? this.fullSkillCatalog,
      skillCatalog: skillCatalog ?? this.skillCatalog,
    );
  }
}

class AssistantExecutionPreparation {
  const AssistantExecutionPreparation({
    this.domainId = '',
    this.modeDecision = const ModeDecision(
      mode: AgentMode.singleAgent,
      reason: 'default_single',
    ),
    this.skillName = '',
    this.skillInstructionMarkdown = '',
    this.skillPersona = '',
    this.allowedToolNames = const <String>[],
    this.executionShell = const SkillExecutionShell(),
    this.plannerTemplateVersion = '',
    this.postcheckTemplateVersion = '',
    this.synthTemplateVersion = '',
    this.fusionSynthTemplateVersion = '',
    this.previousSlotState = const SlotStateSnapshot(),
    this.previousDomainPolicyBundle,
  });

  final String domainId;
  final ModeDecision modeDecision;
  final String skillName;
  final String skillInstructionMarkdown;
  final String skillPersona;
  final List<String> allowedToolNames;
  final SkillExecutionShell executionShell;
  final String plannerTemplateVersion;
  final String postcheckTemplateVersion;
  final String synthTemplateVersion;
  final String fusionSynthTemplateVersion;
  final SlotStateSnapshot previousSlotState;
  final DomainPolicyBundle? previousDomainPolicyBundle;

  bool get hasExecutionDetails =>
      skillName.trim().isNotEmpty ||
      skillInstructionMarkdown.trim().isNotEmpty ||
      skillPersona.trim().isNotEmpty ||
      allowedToolNames.isNotEmpty ||
      plannerTemplateVersion.trim().isNotEmpty ||
      postcheckTemplateVersion.trim().isNotEmpty ||
      synthTemplateVersion.trim().isNotEmpty ||
      fusionSynthTemplateVersion.trim().isNotEmpty ||
      previousSlotState.slotValues.isNotEmpty ||
      previousSlotState.missingSlots.isNotEmpty ||
      previousDomainPolicyBundle != null;

  // ASSISTANT_WEAK_TYPE: JSON serde boundary
  factory AssistantExecutionPreparation.fromJson(Map<String, dynamic> json) {
    return AssistantExecutionPreparation(
      domainId: (json['domainId'] as String?)?.trim() ?? '',
      modeDecision: json['modeDecision'] is Map
          ? ModeDecision.fromJson(
              (json['modeDecision'] as Map).cast<String, dynamic>(),
            )
          : const ModeDecision(
              mode: AgentMode.singleAgent,
              reason: 'default_single',
            ),
      skillName: (json['skillName'] as String?)?.trim() ?? '',
      skillInstructionMarkdown:
          (json['skillInstructionMarkdown'] as String?) ?? '',
      skillPersona: (json['skillPersona'] as String?) ?? '',
      allowedToolNames:
          (json['allowedToolNames'] as List?)
              ?.map((item) => item.toString().trim())
              .where((item) => item.isNotEmpty)
              .toList(growable: false) ??
          const <String>[],
      executionShell: json['executionShell'] is Map
          ? SkillExecutionShell.fromJson(
              (json['executionShell'] as Map).cast<String, dynamic>(),
            )
          : const SkillExecutionShell(),
      plannerTemplateVersion:
          (json['plannerTemplateVersion'] as String?)?.trim() ?? '',
      postcheckTemplateVersion:
          (json['postcheckTemplateVersion'] as String?)?.trim() ?? '',
      synthTemplateVersion:
          (json['synthTemplateVersion'] as String?)?.trim() ?? '',
      fusionSynthTemplateVersion:
          (json['fusionSynthTemplateVersion'] as String?)?.trim() ?? '',
      previousSlotState: json['previousSlotState'] is Map
          ? SlotStateSnapshot.fromJson(
              (json['previousSlotState'] as Map).cast<String, dynamic>(),
            )
          : const SlotStateSnapshot(),
      previousDomainPolicyBundle: json['previousDomainPolicyBundle'] is Map
          ? DomainPolicyBundle.fromJson(
              (json['previousDomainPolicyBundle'] as Map)
                  .cast<String, dynamic>(),
            )
          : null,
    );
  }

  // ASSISTANT_WEAK_TYPE: JSON serde boundary
  Map<String, dynamic> toJson() => <String, dynamic>{
    'domainId': domainId,
    'modeDecision': modeDecision.toJson(),
    'skillName': skillName,
    'skillInstructionMarkdown': skillInstructionMarkdown,
    'skillPersona': skillPersona,
    'allowedToolNames': allowedToolNames,
    'executionShell': executionShell.toJson(),
    'plannerTemplateVersion': plannerTemplateVersion,
    'postcheckTemplateVersion': postcheckTemplateVersion,
    'synthTemplateVersion': synthTemplateVersion,
    'fusionSynthTemplateVersion': fusionSynthTemplateVersion,
    'previousSlotState': previousSlotState.toJson(),
    if (previousDomainPolicyBundle != null)
      'previousDomainPolicyBundle': previousDomainPolicyBundle!.toJson(),
  };

  AssistantExecutionPreparation copyWith({
    String? domainId,
    ModeDecision? modeDecision,
    String? skillName,
    String? skillInstructionMarkdown,
    String? skillPersona,
    List<String>? allowedToolNames,
    SkillExecutionShell? executionShell,
    String? plannerTemplateVersion,
    String? postcheckTemplateVersion,
    String? synthTemplateVersion,
    String? fusionSynthTemplateVersion,
    SlotStateSnapshot? previousSlotState,
    DomainPolicyBundle? previousDomainPolicyBundle,
  }) {
    return AssistantExecutionPreparation(
      domainId: domainId ?? this.domainId,
      modeDecision: modeDecision ?? this.modeDecision,
      skillName: skillName ?? this.skillName,
      skillInstructionMarkdown:
          skillInstructionMarkdown ?? this.skillInstructionMarkdown,
      skillPersona: skillPersona ?? this.skillPersona,
      allowedToolNames: allowedToolNames ?? this.allowedToolNames,
      executionShell: executionShell ?? this.executionShell,
      plannerTemplateVersion:
          plannerTemplateVersion ?? this.plannerTemplateVersion,
      postcheckTemplateVersion:
          postcheckTemplateVersion ?? this.postcheckTemplateVersion,
      synthTemplateVersion: synthTemplateVersion ?? this.synthTemplateVersion,
      fusionSynthTemplateVersion:
          fusionSynthTemplateVersion ?? this.fusionSynthTemplateVersion,
      previousSlotState: previousSlotState ?? this.previousSlotState,
      previousDomainPolicyBundle:
          previousDomainPolicyBundle ?? this.previousDomainPolicyBundle,
    );
  }
}

/// Unified internal execution state for the phase owner pipeline.
///
/// Consolidates runtime-critical state previously scattered across the old
/// local owner implementation and is now owned by [AssistantAgentLoop].
class AgentExecutionState {
  const AgentExecutionState({
    this.bootstrapContext,
    this.executionPreparation,
    this.executionBridgeSnapshot = const <String, dynamic>{},
    this.executionPhaseSnapshot,
    this.intentGraph,
    this.understandingSnapshot = const RunArtifactsUnderstandingSnapshot(),
    this.retrievalProcessing = const RetrievalProcessingSnapshot(),
    this.contextAssembly,
    this.dialogueRoundScript,
    this.slotState,
    this.evidenceLedger = const <EvidenceLedgerEntry>[],
    this.answerEvidenceBindings = const <AnswerEvidenceBinding>[],
    this.evidenceEvaluation,
    this.aggregationState,
    this.queryTasks = const [],
    this.subagentPlans = const [],
    this.previousRunArtifacts,
    this.domainPolicyBundle,
    this.conversationStateDecision,
    this.journey = const AssistantJourney(),
    this.synthesisReadiness,
    this.synthesisDraft,
    this.pendingResponse,
  });

  final AssistantBootstrapContext? bootstrapContext;
  final AssistantExecutionPreparation? executionPreparation;
  @Deprecated('Use executionPhaseSnapshot instead')
  final Map<String, dynamic> executionBridgeSnapshot;
  final ExecutionPhaseSnapshot? executionPhaseSnapshot;
  final IntentGraph? intentGraph;
  final RunArtifactsUnderstandingSnapshot understandingSnapshot;
  final RetrievalProcessingSnapshot retrievalProcessing;
  final ContextAssemblyResult? contextAssembly;
  final DialogueRoundScript? dialogueRoundScript;
  final SlotStateSnapshot? slotState;
  final List<EvidenceLedgerEntry> evidenceLedger;
  final List<AnswerEvidenceBinding> answerEvidenceBindings;
  final EvidenceEvaluationResult? evidenceEvaluation;
  final AggregationState? aggregationState;
  final List<QueryTask> queryTasks;
  final List<SubagentPlan> subagentPlans;
  final RunArtifacts? previousRunArtifacts;
  final DomainPolicyBundle? domainPolicyBundle;
  final ConversationStateDecision? conversationStateDecision;
  final AssistantJourney journey;
  final SynthesisReadinessResult? synthesisReadiness;
  final SynthesisDraft? synthesisDraft;
  final AssistantRunResponse? pendingResponse;

  AgentExecutionState copyWith({
    AssistantBootstrapContext? bootstrapContext,
    AssistantExecutionPreparation? executionPreparation,
    @Deprecated('Use executionPhaseSnapshot')
    Map<String, dynamic>? executionBridgeSnapshot,
    ExecutionPhaseSnapshot? executionPhaseSnapshot,
    IntentGraph? intentGraph,
    RunArtifactsUnderstandingSnapshot? understandingSnapshot,
    RetrievalProcessingSnapshot? retrievalProcessing,
    ContextAssemblyResult? contextAssembly,
    DialogueRoundScript? dialogueRoundScript,
    SlotStateSnapshot? slotState,
    List<EvidenceLedgerEntry>? evidenceLedger,
    List<AnswerEvidenceBinding>? answerEvidenceBindings,
    EvidenceEvaluationResult? evidenceEvaluation,
    AggregationState? aggregationState,
    List<QueryTask>? queryTasks,
    List<SubagentPlan>? subagentPlans,
    RunArtifacts? previousRunArtifacts,
    DomainPolicyBundle? domainPolicyBundle,
    ConversationStateDecision? conversationStateDecision,
    AssistantJourney? journey,
    SynthesisReadinessResult? synthesisReadiness,
    SynthesisDraft? synthesisDraft,
    AssistantRunResponse? pendingResponse,
  }) {
    return AgentExecutionState(
      bootstrapContext: bootstrapContext ?? this.bootstrapContext,
      executionPreparation: executionPreparation ?? this.executionPreparation,
      executionBridgeSnapshot:
          executionBridgeSnapshot ?? this.executionBridgeSnapshot,
      executionPhaseSnapshot:
          executionPhaseSnapshot ?? this.executionPhaseSnapshot,
      intentGraph: intentGraph ?? this.intentGraph,
      understandingSnapshot: understandingSnapshot ?? this.understandingSnapshot,
      retrievalProcessing: retrievalProcessing ?? this.retrievalProcessing,
      contextAssembly: contextAssembly ?? this.contextAssembly,
      dialogueRoundScript: dialogueRoundScript ?? this.dialogueRoundScript,
      slotState: slotState ?? this.slotState,
      evidenceLedger: evidenceLedger ?? this.evidenceLedger,
      answerEvidenceBindings:
          answerEvidenceBindings ?? this.answerEvidenceBindings,
      evidenceEvaluation: evidenceEvaluation ?? this.evidenceEvaluation,
      aggregationState: aggregationState ?? this.aggregationState,
      queryTasks: queryTasks ?? this.queryTasks,
      subagentPlans: subagentPlans ?? this.subagentPlans,
      previousRunArtifacts: previousRunArtifacts ?? this.previousRunArtifacts,
      domainPolicyBundle: domainPolicyBundle ?? this.domainPolicyBundle,
      conversationStateDecision:
          conversationStateDecision ?? this.conversationStateDecision,
      journey: journey ?? this.journey,
      synthesisReadiness: synthesisReadiness ?? this.synthesisReadiness,
      synthesisDraft: synthesisDraft ?? this.synthesisDraft,
      pendingResponse: pendingResponse ?? this.pendingResponse,
    );
  }
}
