import 'dart:convert';

import 'package:quwoquan_app/assistant/contracts/answer_boundary_policy.dart';
import 'package:quwoquan_app/assistant/contracts/context_assembly_result.dart';
import 'package:quwoquan_app/assistant/contracts/context_continuity_policy.dart';
import 'package:quwoquan_app/assistant/contracts/dialogue_round_script.dart';
import 'package:quwoquan_app/assistant/contracts/intent_graph.dart';
import 'package:quwoquan_app/assistant/contracts/query_task_contract.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_prompt_keys.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_state_keys.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_template_bundle.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_synthesis_template_bundle.dart';
import 'package:quwoquan_app/assistant/orchestration/state/agent_execution_state.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/reasoning/temporal/relative_time_resolver.dart';
import 'package:quwoquan_app/assistant/skill/domain/skill_manifest.dart';

const List<String> _uiOnlyTemplateContextKeys = <String>[
  AssistantPipelineStateKeys.runArtifacts,
  AssistantPipelineStateKeys.previousRunArtifacts,
  AssistantPipelineStateKeys.machineEnvelope,
  AssistantPipelineStateKeys.displayMarkdown,
  AssistantPipelineStateKeys.displayPlainText,
  AssistantPipelineStateKeys.journey,
  AssistantPipelineStateKeys.uiProcessTimeline,
  AssistantPipelineStateKeys.assistantResponse,
];

Map<String, dynamic> buildCompatibilityContextScopeHint({
  required AssistantRunRequest request,
  required AgentExecutionState state,
}) {
  final bootstrap = state.bootstrapContext;
  final continuationActive = _shouldCarryStructuredHistory(
    bootstrap?.contextContinuityPolicy ?? const ContextContinuityPolicy(),
  );
  final contextScopeHint = sanitizeModelTemplateContext(
    request.contextScopeHint,
    continuationActive: continuationActive,
    previousRunArtifacts: state.previousRunArtifacts,
  );

  if (bootstrap == null) {
    _applyPrecomputedStateScopeHint(contextScopeHint, state);
    return contextScopeHint;
  }

  contextScopeHint[AssistantPipelineStateKeys.precomputedBootstrap] =
      _buildPrecomputedBootstrapPayload(
        bootstrap: bootstrap,
        state: state,
      );
  _applyPrecomputedStateScopeHint(contextScopeHint, state);
  return contextScopeHint;
}

Map<String, dynamic> sanitizeModelTemplateContext(
  Map<String, dynamic> contextScopeHint, {
  required bool continuationActive,
  RunArtifacts? previousRunArtifacts,
}) {
  if (contextScopeHint.isEmpty) {
    return continuationActive && previousRunArtifacts != null
        ? <String, dynamic>{
            'runArtifacts': previousRunArtifacts.toJson(),
          }
        : <String, dynamic>{};
  }
  final sanitized = Map<String, dynamic>.from(contextScopeHint);
  for (final key in _uiOnlyTemplateContextKeys) {
    sanitized.remove(key);
  }
  if (!continuationActive) {
    sanitized.remove(AssistantPipelineStateKeys.dialogueState);
    sanitized.remove(AssistantPipelineStateKeys.currentStateId);
  } else if (previousRunArtifacts != null) {
    sanitized['runArtifacts'] = previousRunArtifacts.toJson();
  }
  return sanitized;
}

void _applyPrecomputedStateScopeHint(
  Map<String, dynamic> contextScopeHint,
  AgentExecutionState state,
) {
  if (state.intentGraph != null) {
    contextScopeHint[AssistantPipelineStateKeys.precomputedIntentGraph] =
        state.intentGraph!.toJson();
  }
  if (state.dialogueRoundScript != null || state.executionPreparation != null) {
    contextScopeHint[AssistantPipelineStateKeys.precomputedUnderstand] =
        _buildPrecomputedUnderstandPayload(
          dialogueRoundScript: state.dialogueRoundScript,
          executionPreparation: state.executionPreparation,
        );
  }
  if (state.executionPreparation != null) {
    contextScopeHint[AssistantPipelineStateKeys.precomputedExecutionPreparation] =
        state.executionPreparation!.toJson();
    contextScopeHint[AssistantPipelineStateKeys.precomputedRetrieval] =
        _buildPrecomputedRetrievalPayload(
          executionPreparation: state.executionPreparation!,
        );
  }
  if (state.queryTasks.isNotEmpty) {
    contextScopeHint[AssistantPipelineStateKeys.precomputedQueryTasks] =
        state.queryTasks.map((item) => item.toJson()).toList(growable: false);
  }
}

Map<String, dynamic> _buildPrecomputedBootstrapPayload({
  required AssistantBootstrapContext bootstrap,
  required AgentExecutionState state,
}) {
  return <String, dynamic>{
    AssistantPipelineStateKeys.sessionId: bootstrap.sessionId,
    AssistantPipelineStateKeys.latestUserQuery: bootstrap.latestUserQuery,
    if (bootstrap.compactHistorySummary.trim().isNotEmpty)
      AssistantPipelineStateKeys.historySummary: bootstrap.compactHistorySummary,
    if (bootstrap.recentDialogueRounds.isNotEmpty)
      AssistantPipelineStateKeys.recentDialogueRounds:
          bootstrap.recentDialogueRounds,
    AssistantPipelineStateKeys.recentDialogueRoundsLimit:
        bootstrap.recentDialogueRoundsLimit,
    AssistantPipelineStateKeys.recalledTexts: bootstrap.recalledTexts,
    if (bootstrap.previousIntentGraph != null)
      AssistantPipelineStateKeys.previousIntentGraph:
          bootstrap.previousIntentGraph!.toJson(),
    if (bootstrap.previousAnswerSummary.isNotEmpty)
      AssistantPipelineStateKeys.previousAnswerSummary:
          bootstrap.previousAnswerSummary,
    if (_hasStructuredContent(bootstrap.previousUnderstandingSnapshot.toJson()) &&
        state.previousRunArtifacts == null)
      AssistantPipelineStateKeys.previousUnderstandingSnapshot:
          bootstrap.previousUnderstandingSnapshot.toJson(),
    if (_hasStructuredContent(bootstrap.previousAnswerProcessing.toJson()) &&
        state.previousRunArtifacts == null)
      AssistantPipelineStateKeys.previousAnswerProcessing:
          bootstrap.previousAnswerProcessing.toJson(),
    if (_hasStructuredContent(bootstrap.historicalThinkingSnapshot.toJson()) &&
        state.previousRunArtifacts == null)
      AssistantPipelineStateKeys.historicalThinkingSnapshot:
          bootstrap.historicalThinkingSnapshot.toJson(),
    if (bootstrap.providerReasoningContinuation.trim().isNotEmpty)
      AssistantPipelineStateKeys.providerReasoningContinuation:
          bootstrap.providerReasoningContinuation.trim(),
    if (!bootstrap.sessionHistoryState.isEmpty)
      AssistantPipelineStateKeys.sessionHistoryState:
          bootstrap.sessionHistoryState.toJson(),
    AssistantPipelineStateKeys.contextContinuityPolicy:
        bootstrap.contextContinuityPolicy.toJson(),
    AssistantPipelineStateKeys.continuityOverrideSlots:
        bootstrap.continuityOverrideSlots,
    AssistantPipelineStateKeys.recallResult: bootstrap.recallResult.toJson(),
    AssistantPipelineStateKeys.forceRefreshCatalog:
        bootstrap.forceRefreshCatalog,
    AssistantPipelineStateKeys.domainCatalog: bootstrap.domainCatalog,
    AssistantPipelineStateKeys.domainCatalogVersion:
        bootstrap.domainCatalogVersion,
    AssistantPipelineStateKeys.fullSkillCatalog: bootstrap.fullSkillCatalog,
    AssistantPipelineStateKeys.skillCatalog: bootstrap.skillCatalog,
    if (state.contextAssembly != null)
      AssistantPipelineStateKeys.contextAssembly:
          state.contextAssembly!.toJson(),
    if (state.previousRunArtifacts != null)
      AssistantPipelineStateKeys.previousRunArtifacts:
          state.previousRunArtifacts!.toJson(),
  };
}

Map<String, dynamic> _buildPrecomputedUnderstandPayload({
  DialogueRoundScript? dialogueRoundScript,
  AssistantExecutionPreparation? executionPreparation,
}) {
  return <String, dynamic>{
    if (dialogueRoundScript != null)
      AssistantPipelineStateKeys.dialogueRoundScript:
          dialogueRoundScript.toJson(),
    if (executionPreparation != null)
      AssistantPipelineStateKeys.domainId: executionPreparation.domainId,
    if (executionPreparation != null)
      AssistantPipelineStateKeys.modeDecision:
          executionPreparation.modeDecision.toJson(),
  };
}

Map<String, dynamic> _buildPrecomputedRetrievalPayload({
  required AssistantExecutionPreparation executionPreparation,
}) {
  return <String, dynamic>{
    AssistantPipelineStateKeys.skillName:
        executionPreparation.skillName,
    AssistantPipelineStateKeys.skillInstructionMarkdown:
        executionPreparation.skillInstructionMarkdown,
    AssistantPipelineStateKeys.skillPersona:
        executionPreparation.skillPersona,
    AssistantPipelineStateKeys.allowedToolNames:
        executionPreparation.allowedToolNames,
    AssistantPipelineStateKeys.executionShell:
        executionPreparation.executionShell.toJson(),
    AssistantPipelineStateKeys.plannerTemplateVersion:
        executionPreparation.plannerTemplateVersion,
    AssistantPipelineStateKeys.postcheckTemplateVersion:
        executionPreparation.postcheckTemplateVersion,
    AssistantPipelineStateKeys.synthTemplateVersion:
        executionPreparation.synthTemplateVersion,
    AssistantPipelineStateKeys.fusionSynthTemplateVersion:
        executionPreparation.fusionSynthTemplateVersion,
    AssistantPipelineStateKeys.previousSlotState:
        executionPreparation.previousSlotState.toJson(),
    if (executionPreparation.previousDomainPolicyBundle != null)
      AssistantPipelineStateKeys.previousDomainPolicyBundle:
          executionPreparation.previousDomainPolicyBundle!.toJson(),
  };
}

Map<String, dynamic> buildPlannerTemplateVariables({
  required String userQuery,
  required String skillCatalog,
  required String conversationSpineJson,
  required String sharedContextJson,
  required String currentRuntimeStateJson,
  required String dialogueContinuityJson,
  required String recentDialogueRoundsJson,
  required String searchIterationStateJson,
  String continuityMode = '',
  String problemClass = '',
}) {
  return <String, dynamic>{
    AssistantPipelinePromptKeys.userQuery: userQuery,
    AssistantPipelinePromptKeys.conversationSpine: conversationSpineJson,
    AssistantPipelinePromptKeys.skillCatalog: skillCatalog,
    AssistantPipelinePromptKeys.sharedContext: sharedContextJson,
    AssistantPipelinePromptKeys.currentRuntimeState: currentRuntimeStateJson,
    AssistantPipelinePromptKeys.dialogueContinuity: dialogueContinuityJson,
    AssistantPipelinePromptKeys.recentDialogueRounds: recentDialogueRoundsJson,
    AssistantPipelinePromptKeys.searchIterationState: searchIterationStateJson,
    AssistantPipelinePromptKeys.continuityMode: continuityMode,
    AssistantPipelineStateKeys.problemClass: problemClass,
  };
}

Map<String, dynamic> buildPipelineTemplateVariables({
  required AssistantPipelineTemplateBundle bundle,
  required List<Map<String, dynamic>> recentDialogueRounds,
}) {
  final query = bundle.request.messages.isEmpty
      ? ''
      : bundle.request.messages.last.content;
  return buildPlannerTemplateVariables(
    userQuery: query,
    skillCatalog: bundle.skillCatalog,
    conversationSpineJson: jsonEncode(bundle.conversationSpine),
    sharedContextJson: jsonEncode(_buildSharedContext(bundle)),
    currentRuntimeStateJson: jsonEncode(_buildCurrentRuntimeState(bundle)),
    dialogueContinuityJson: jsonEncode(_buildDialogueContinuity(bundle)),
    recentDialogueRoundsJson: jsonEncode(recentDialogueRounds),
    searchIterationStateJson: jsonEncode(bundle.searchIterationState.toJson()),
  );
}

Map<String, dynamic> buildSynthesisTemplateVariables({
  required AssistantPipelineSynthesisTemplateBundle bundle,
}) {
  return <String, dynamic>{
    ...bundle.templateVariables,
    AssistantPipelinePromptKeys.conversationSpine:
        jsonEncode(bundle.conversationSpine),
    AssistantPipelineStateKeys.userGoal: bundle.userGoal,
    AssistantPipelineStateKeys.understandingSnapshot:
        jsonEncode(bundle.understandingSnapshot),
    AssistantPipelineStateKeys.retrievalProcessing:
        jsonEncode(bundle.retrievalProcessing),
    AssistantPipelinePromptKeys.sharedContext: jsonEncode(bundle.sharedContext),
    AssistantPipelinePromptKeys.currentRuntimeState:
        jsonEncode(bundle.currentRuntimeState),
    AssistantPipelinePromptKeys.dialogueContinuity:
        jsonEncode(bundle.dialogueContinuity),
    AssistantPipelinePromptKeys.evidenceContext:
        jsonEncode(bundle.evidenceContext),
    AssistantPipelinePromptKeys.searchIterationState:
        jsonEncode(bundle.searchIterationState),
    AssistantPipelinePromptKeys.intentGraphJson: bundle.intentGraphJson,
    AssistantPipelinePromptKeys.queryTasksJson:
        jsonEncode(bundle.queryTasksJson),
    AssistantPipelinePromptKeys.entityAnchors: bundle.entityAnchors,
    AssistantPipelinePromptKeys.queryTasks: bundle.queryTasks,
    AssistantPipelineStateKeys.answerShape: bundle.answerShape,
    AssistantPipelinePromptKeys.recentDialogueRounds:
        jsonEncode(bundle.recentDialogueRounds),
  };
}

Map<String, dynamic> buildFusionTemplateVariables({
  required AssistantPipelineSynthesisTemplateBundle bundle,
  required List<Map<String, dynamic>> skillRuns,
  required Map<String, dynamic> aggregationState,
  required List<Map<String, dynamic>> subagentRuns,
  required Map<String, dynamic> skillSynthesis,
}) {
  return <String, dynamic>{
    ...buildSynthesisTemplateVariables(bundle: bundle),
    AssistantPipelinePromptKeys.skillRuns: jsonEncode(skillRuns),
    AssistantPipelinePromptKeys.aggregationState:
        jsonEncode(aggregationState),
    AssistantPipelinePromptKeys.subagentRuns: jsonEncode(subagentRuns),
    AssistantPipelinePromptKeys.skillSynthesis: jsonEncode(skillSynthesis),
  };
}

Map<String, dynamic> _buildSharedContext(AssistantPipelineTemplateBundle bundle) {
  return <String, dynamic>{
    AssistantPipelinePromptKeys.contextEnvelope:
        bundle.contextAssembly.contextEnvelope,
    AssistantPipelinePromptKeys.temporalReference: <String, dynamic>{
      AssistantPipelinePromptKeys.referenceNowIso:
          bundle.temporalReference.referenceNowIso,
      AssistantPipelinePromptKeys.timezone: bundle.temporalReference.timezone,
      AssistantPipelinePromptKeys.calendarContext: bundle.calendarContext,
    },
  };
}

Map<String, dynamic> _buildCurrentRuntimeState(
  AssistantPipelineTemplateBundle bundle,
) {
  final precomputedBootstrap = _contextHintMap(
    bundle.request.contextScopeHint[AssistantPipelineStateKeys.precomputedBootstrap],
  );
  final sessionHistoryState = _contextHintMap(
    precomputedBootstrap[AssistantPipelineStateKeys.sessionHistoryState],
  );
  return <String, dynamic>{
    AssistantPipelinePromptKeys.dialogueState: <String, dynamic>{
      AssistantPipelinePromptKeys.calendarContext: bundle.calendarContext,
      AssistantPipelinePromptKeys.referenceNowIso:
          bundle.temporalReference.referenceNowIso,
      AssistantPipelinePromptKeys.timezone: bundle.temporalReference.timezone,
    },
    if (sessionHistoryState.isNotEmpty)
      AssistantPipelineStateKeys.sessionHistoryState: sessionHistoryState,
  };
}

Map<String, dynamic> _buildDialogueContinuity(
  AssistantPipelineTemplateBundle bundle,
) {
  return <String, dynamic>{
    AssistantPipelinePromptKeys.continuityMode:
        bundle.continuityPolicy.continuityMode.wireName,
  };
}

Map<String, dynamic> _buildSkillExecutionShellTemplate(
  AssistantPipelineTemplateBundle bundle,
) {
  return <String, dynamic>{
    ...bundle.skillExecutionShell.toJson(),
    if (bundle.intentGraph?.queryTasks != null &&
        bundle.intentGraph!.queryTasks.isNotEmpty)
      AssistantPipelineStateKeys.executionShellPrecomputedQueryTasks:
          bundle.intentGraph!.queryTasks
              .map((t) => t.toJson())
              .toList(growable: false),
  };
}

Map<String, dynamic> _contextHintMap(Object? raw) {
  if (raw is Map) {
    return raw.cast<String, dynamic>();
  }
  return const <String, dynamic>{};
}

bool _shouldCarryStructuredHistory(ContextContinuityPolicy policy) {
  switch (policy.continuityMode) {
    case ContextContinuityMode.sameTopic:
    case ContextContinuityMode.explicitFollowUp:
      return true;
    case ContextContinuityMode.freshTopic:
    case ContextContinuityMode.unknown:
      return false;
  }
}

bool _hasStructuredContent(Map<String, dynamic> value) {
  for (final entry in value.entries) {
    final v = entry.value;
    if (v == null) continue;
    if (v is String && v.trim().isEmpty) continue;
    if (v is List && v.isEmpty) continue;
    if (v is Map && v.isEmpty) continue;
    return true;
  }
  return false;
}

