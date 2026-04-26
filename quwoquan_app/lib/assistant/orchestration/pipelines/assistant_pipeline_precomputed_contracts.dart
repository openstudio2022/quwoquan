import 'package:quwoquan_app/assistant/contracts/context_assembly_result.dart';
import 'package:quwoquan_app/assistant/contracts/context_continuity_policy.dart';
import 'package:quwoquan_app/assistant/contracts/dialogue_round_script.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_session_history_state.dart';
import 'package:quwoquan_app/assistant/contracts/recall_result.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/system_context_envelope.dart';
import 'package:quwoquan_app/assistant/contracts/task_graph_contract.dart';
import 'package:quwoquan_app/assistant/contracts/understanding_result_contract.dart';
import 'package:quwoquan_app/assistant/protocol/recent_dialogue_rounds.dart';
import 'package:quwoquan_app/assistant/protocol/understanding_snapshot_codec.dart';
import 'package:quwoquan_app/assistant/orchestration/state/agent_execution_state.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_state_keys.dart';
import 'package:quwoquan_app/assistant/skill/domain/skill_manifest.dart';
import 'package:quwoquan_app/assistant/reasoning/planner/mode_decider.dart';

class PrecomputedBootstrap {
  const PrecomputedBootstrap({
    required this.sessionId,
    required this.latestUserQuery,
    required this.historySummary,
    this.systemContextEnvelope = const SystemContextEnvelope(),
    this.recentDialogueRounds = const <Map<String, dynamic>>[],
    this.recentDialogueRoundsLimit = 10,
    required this.recalledTexts,
    this.previousAnswerSummary = '',
    this.previousUnderstandingResult = const UnderstandingResult(),
    this.previousTaskGraph = const TaskGraph(),
    this.previousUnderstandingSnapshot =
        const RunArtifactsUnderstandingSnapshot(),
    this.previousAnswerProcessing = const RunArtifactsAnswerProcessing(),
    this.historicalThinkingSnapshot =
        const RunArtifactsHistoricalThinkingSnapshot(),
    this.providerReasoningContinuation = '',
    required this.continuityPolicy,
    this.continuityOverrideSlots = const <String, dynamic>{},
    required this.recallResult,
    required this.forceRefreshCatalog,
    required this.domainCatalog,
    required this.domainCatalogVersion,
    required this.fullSkillCatalog,
    required this.skillCatalog,
    this.sessionHistoryState = const AssistantSessionHistoryState(),
    this.contextAssembly,
    this.previousRunArtifacts,
  });

  final String sessionId;
  final String latestUserQuery;
  final String historySummary;
  final SystemContextEnvelope systemContextEnvelope;
  final List<Map<String, dynamic>> recentDialogueRounds;
  final int recentDialogueRoundsLimit;
  final List<String> recalledTexts;
  final String previousAnswerSummary;
  final UnderstandingResult previousUnderstandingResult;
  final TaskGraph previousTaskGraph;
  final RunArtifactsUnderstandingSnapshot previousUnderstandingSnapshot;
  final RunArtifactsAnswerProcessing previousAnswerProcessing;
  final RunArtifactsHistoricalThinkingSnapshot historicalThinkingSnapshot;
  final String providerReasoningContinuation;
  final ContextContinuityPolicy continuityPolicy;
  final Map<String, dynamic> continuityOverrideSlots;
  final RecallResult recallResult;
  final bool forceRefreshCatalog;
  final List<String> domainCatalog;
  final String domainCatalogVersion;
  final String fullSkillCatalog;
  final String skillCatalog;
  final AssistantSessionHistoryState sessionHistoryState;
  final ContextAssemblyResult? contextAssembly;
  final RunArtifacts? previousRunArtifacts;
}

class PrecomputedUnderstand {
  const PrecomputedUnderstand({
    required this.domainId,
    required this.modeDecision,
    this.dialogueRoundScript,
  });

  final String domainId;
  final ModeDecision modeDecision;
  final DialogueRoundScript? dialogueRoundScript;
}

class PrecomputedRetrieval {
  const PrecomputedRetrieval({
    required this.skillName,
    required this.skillInstructionMarkdown,
    required this.skillPersona,
    required this.allowedToolNames,
    required this.executionShell,
    required this.plannerTemplateVersion,
    required this.postcheckTemplateVersion,
    required this.synthTemplateVersion,
    required this.fusionSynthTemplateVersion,
    required this.previousSlotState,
    this.previousDomainPolicyBundle,
  });

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
}

PrecomputedBootstrap? recoverPrecomputedBootstrap(
  Map<String, dynamic> contextScopeHint, {
  int defaultRecentDialogueRoundsLimit = 5,
}) {
  final raw = (contextScopeHint['precomputedBootstrap'] as Map?)
      ?.cast<String, dynamic>();
  if (raw == null || raw.isEmpty) return null;
  try {
    final previousRunArtifacts = raw['previousRunArtifacts'] is Map
        ? parseRunArtifacts(
            (raw['previousRunArtifacts'] as Map).cast<String, dynamic>(),
          )
        : null;
    final previousUnderstandingSnapshot =
        raw['previousUnderstandingSnapshot'] is Map
        ? parseRunArtifactsUnderstandingSnapshotFromMap(
            (raw['previousUnderstandingSnapshot'] as Map)
                .cast<String, dynamic>(),
          )
        : (previousRunArtifacts?.understandingSnapshot ??
              const RunArtifactsUnderstandingSnapshot());
    final previousAnswerProcessing = raw['previousAnswerProcessing'] is Map
        ? RunArtifactsAnswerProcessing.fromJson(
            (raw['previousAnswerProcessing'] as Map).cast<String, dynamic>(),
          )
        : (previousRunArtifacts?.answerProcessing ??
              const RunArtifactsAnswerProcessing());
    final historicalThinkingSnapshot = raw['historicalThinkingSnapshot'] is Map
        ? RunArtifactsHistoricalThinkingSnapshot.fromJson(
            (raw['historicalThinkingSnapshot'] as Map).cast<String, dynamic>(),
          )
        : (previousRunArtifacts?.historicalThinkingSnapshot ??
              const RunArtifactsHistoricalThinkingSnapshot());
    final sessionHistoryState = raw['sessionHistoryState'] is Map
        ? AssistantSessionHistoryState.fromJson(
            (raw['sessionHistoryState'] as Map).cast<String, dynamic>(),
          )
        : const AssistantSessionHistoryState();
    final systemContextEnvelope = raw['systemContextEnvelope'] is Map
        ? SystemContextEnvelope.fromJson(
            (raw['systemContextEnvelope'] as Map).cast<String, dynamic>(),
          )
        : const SystemContextEnvelope();
    final previousUnderstandingResult = raw['previousUnderstandingResult'] is Map
        ? UnderstandingResult.fromJson(
            (raw['previousUnderstandingResult'] as Map).cast<String, dynamic>(),
          )
        : const UnderstandingResult();
    final previousTaskGraph = raw['previousTaskGraph'] is Map
        ? TaskGraph.fromJson(
            (raw['previousTaskGraph'] as Map).cast<String, dynamic>(),
          )
        : const TaskGraph();
    return PrecomputedBootstrap(
      sessionId: (raw['sessionId'] as String?)?.trim() ?? 'default',
      latestUserQuery: (raw['latestUserQuery'] as String?)?.trim() ?? '',
      historySummary: (raw['historySummary'] as String?) ?? '',
      systemContextEnvelope: systemContextEnvelope,
      recalledTexts:
          (raw['recalledTexts'] as List?)
              ?.map((item) => item.toString().trim())
              .where((item) => item.isNotEmpty)
              .toList(growable: false) ??
          const <String>[],
      previousAnswerSummary:
          (raw['previousAnswerSummary'] as String?)?.trim() ?? '',
      previousUnderstandingResult: previousUnderstandingResult,
      previousTaskGraph: previousTaskGraph,
      recentDialogueRounds: coerceRecentDialogueRounds(
        raw['recentDialogueRounds'],
      ),
      recentDialogueRoundsLimit:
          (raw['recentDialogueRoundsLimit'] as num?)?.toInt() ??
          defaultRecentDialogueRoundsLimit,
      previousUnderstandingSnapshot: previousUnderstandingSnapshot,
      previousAnswerProcessing: previousAnswerProcessing,
      historicalThinkingSnapshot: historicalThinkingSnapshot,
      providerReasoningContinuation:
          (raw['providerReasoningContinuation'] as String?)?.trim() ?? '',
      continuityPolicy: raw['contextContinuityPolicy'] is Map
          ? ContextContinuityPolicy.fromJson(
              (raw['contextContinuityPolicy'] as Map).cast<String, dynamic>(),
            )
          : const ContextContinuityPolicy(),
      continuityOverrideSlots:
          (raw['continuityOverrideSlots'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      recallResult: raw['recallResult'] is Map
          ? RecallResult.fromJson(
              (raw['recallResult'] as Map).cast<String, dynamic>(),
            )
          : const RecallResult(topK: <RecallCandidate>[]),
      forceRefreshCatalog: raw['forceRefreshCatalog'] == true,
      domainCatalog:
          (raw['domainCatalog'] as List?)
              ?.map((item) => item.toString().trim())
              .where((item) => item.isNotEmpty)
              .toList(growable: false) ??
          const <String>[],
      domainCatalogVersion:
          (raw['domainCatalogVersion'] as String?)?.trim() ?? '',
      fullSkillCatalog: (raw['fullSkillCatalog'] as String?) ?? '',
      skillCatalog: (raw['skillCatalog'] as String?) ?? '',
      sessionHistoryState: sessionHistoryState,
      contextAssembly: raw['contextAssembly'] is Map
          ? ContextAssemblyResult.fromJson(
              (raw['contextAssembly'] as Map).cast<String, dynamic>(),
            )
          : null,
      previousRunArtifacts: previousRunArtifacts,
    );
  } catch (_) {
    return null;
  }
}

PrecomputedUnderstand? recoverPrecomputedUnderstand(
  Map<String, dynamic> contextScopeHint,
) {
  final raw = (contextScopeHint['precomputedUnderstand'] as Map?)
      ?.cast<String, dynamic>();
  if (raw == null || raw.isEmpty) return null;
  try {
    final modeRaw =
        (raw['modeDecision'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    return PrecomputedUnderstand(
      domainId: (raw['domainId'] as String?)?.trim() ?? '',
      dialogueRoundScript: raw['dialogueRoundScript'] is Map
          ? _dialogueRoundScriptFromJson(
              (raw['dialogueRoundScript'] as Map).cast<String, dynamic>(),
            )
          : null,
      modeDecision: ModeDecision.fromJson(modeRaw),
    );
  } catch (_) {
    return null;
  }
}

PrecomputedRetrieval? recoverPrecomputedRetrieval(
  Map<String, dynamic> contextScopeHint,
) {
  final raw = (contextScopeHint['precomputedRetrieval'] as Map?)
      ?.cast<String, dynamic>();
  if (raw == null || raw.isEmpty) return null;
  try {
    return PrecomputedRetrieval(
      skillName: (raw['skillName'] as String?)?.trim() ?? '',
      skillInstructionMarkdown:
          (raw['skillInstructionMarkdown'] as String?) ?? '',
      skillPersona: (raw['skillPersona'] as String?) ?? '',
      allowedToolNames:
          (raw['allowedToolNames'] as List?)
              ?.map((item) => item.toString().trim())
              .where((item) => item.isNotEmpty)
              .toList(growable: false) ??
          const <String>[],
      executionShell: raw['executionShell'] is Map
          ? SkillExecutionShell.fromJson(
              (raw['executionShell'] as Map).cast<String, dynamic>(),
            )
          : const SkillExecutionShell(),
      plannerTemplateVersion:
          (raw['plannerTemplateVersion'] as String?)?.trim() ?? '',
      postcheckTemplateVersion:
          (raw['postcheckTemplateVersion'] as String?)?.trim() ?? '',
      synthTemplateVersion:
          (raw['synthTemplateVersion'] as String?)?.trim() ?? '',
      fusionSynthTemplateVersion:
          (raw['fusionSynthTemplateVersion'] as String?)?.trim() ?? '',
      previousSlotState: raw['previousSlotState'] is Map
          ? SlotStateSnapshot.fromJson(
              (raw['previousSlotState'] as Map).cast<String, dynamic>(),
            )
          : const SlotStateSnapshot(),
      previousDomainPolicyBundle: raw['previousDomainPolicyBundle'] is Map
          ? DomainPolicyBundle.fromJson(
              (raw['previousDomainPolicyBundle'] as Map)
                  .cast<String, dynamic>(),
            )
          : null,
    );
  } catch (_) {
    return null;
  }
}

AssistantExecutionPreparation? recoverPrecomputedExecutionPreparation(
  Map<String, dynamic> contextScopeHint, {
  PrecomputedUnderstand? precomputedUnderstand,
  PrecomputedRetrieval? precomputedRetrieval,
}) {
  final raw =
      (contextScopeHint[AssistantPipelineStateKeys
                  .precomputedExecutionPreparation]
              as Map?)
          ?.cast<String, dynamic>();
  if (raw != null && raw.isNotEmpty) {
    try {
      return AssistantExecutionPreparation.fromJson(raw);
    } catch (_) {
      // Fall through to compatibility recovery.
    }
  }
  if (precomputedUnderstand == null && precomputedRetrieval == null) {
    return null;
  }
  return AssistantExecutionPreparation(
    domainId: precomputedUnderstand?.domainId ?? '',
    modeDecision:
        precomputedUnderstand?.modeDecision ??
        const ModeDecision(
          mode: AgentMode.singleAgent,
          reason: 'default_single',
        ),
    skillName: precomputedRetrieval?.skillName ?? '',
    skillInstructionMarkdown:
        precomputedRetrieval?.skillInstructionMarkdown ?? '',
    skillPersona: precomputedRetrieval?.skillPersona ?? '',
    allowedToolNames:
        precomputedRetrieval?.allowedToolNames ?? const <String>[],
    executionShell:
        precomputedRetrieval?.executionShell ?? const SkillExecutionShell(),
    plannerTemplateVersion: precomputedRetrieval?.plannerTemplateVersion ?? '',
    postcheckTemplateVersion:
        precomputedRetrieval?.postcheckTemplateVersion ?? '',
    synthTemplateVersion: precomputedRetrieval?.synthTemplateVersion ?? '',
    fusionSynthTemplateVersion:
        precomputedRetrieval?.fusionSynthTemplateVersion ?? '',
    previousSlotState:
        precomputedRetrieval?.previousSlotState ?? const SlotStateSnapshot(),
    previousDomainPolicyBundle:
        precomputedRetrieval?.previousDomainPolicyBundle,
  );
}

RunArtifacts? recoverPreviousRunArtifacts(
  Map<String, dynamic> contextScopeHint,
) {
  final raw =
      (contextScopeHint[AssistantPipelineStateKeys.runArtifacts] as Map?)
          ?.cast<String, dynamic>();
  if (raw == null || raw.isEmpty) return null;
  try {
    return parseRunArtifacts(raw);
  } catch (_) {
    return null;
  }
}

DialogueRoundScript _dialogueRoundScriptFromJson(Map<String, dynamic> json) {
  final dto = DialogueRoundScriptDto.fromJson(json);
  return DialogueRoundScript(
    domainId: dto.domainId,
    enabled: dto.enabled,
    currentStateId: dto.currentStateId,
    detectedEvent: dto.detectedEvent,
    suggestedNextStateId: dto.suggestedNextStateId,
    nextStateCandidates: dto.nextStateCandidates,
    requiredFieldsForNextState: dto.requiredFieldsForNextState,
    totalSubTotalRequired: dto.totalSubTotalRequired,
    optionalEnrichment: dto.optionalEnrichment,
    maxQuestionsPerTurn: dto.maxQuestionsPerTurn,
    hardFailCodes: dto.hardFailCodes,
    passCriteriaRound: dto.passCriteriaRound,
    statePromptExcerpt: dto.statePromptExcerpt,
    stateMachineExcerpt: dto.stateMachineExcerpt,
    routingCatalogVersion: dto.routingCatalogVersion,
    eventCatalogVersion: dto.eventCatalogVersion,
  );
}
