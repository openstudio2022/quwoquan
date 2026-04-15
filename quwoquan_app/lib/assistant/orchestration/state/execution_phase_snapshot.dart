import 'package:quwoquan_app/assistant/contracts/answer_boundary_policy.dart';
import 'package:quwoquan_app/assistant/contracts/context_assembly_result.dart';
import 'package:quwoquan_app/assistant/contracts/dialogue_round_script.dart';
import 'package:quwoquan_app/assistant/contracts/intent_graph.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/synthesis_readiness_result.dart';
import 'package:quwoquan_app/assistant/context/assembly/evidence_evaluator.dart';
import 'package:quwoquan_app/assistant/orchestration/assistant_orchestration_runtime.dart';
import 'package:quwoquan_app/assistant/protocol/run_response.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/skill/domain/skill_manifest.dart';

/// Strongly-typed output of the execution phase, replacing the previous
/// `Map<String, dynamic>` bridge snapshot.
///
/// Uses a sealed hierarchy to distinguish the normal success path from the
/// short-circuit (domain-gate blocked) path.
sealed class ExecutionPhaseSnapshot {
  const ExecutionPhaseSnapshot();
}

/// Short-circuit: the execution phase produced a response without entering
/// the main LLM call (e.g. domain gate blocked).
class ExecutionPhaseShortCircuit extends ExecutionPhaseSnapshot {
  const ExecutionPhaseShortCircuit({required this.response});
  final AssistantRunResponse response;
}

/// Normal execution result containing all state needed by downstream phases
/// (synthesis, finalize).
class ExecutionPhaseSuccess extends ExecutionPhaseSnapshot {
  const ExecutionPhaseSuccess({
    required this.runId,
    required this.traceId,
    required this.runStartAt,
    required this.sessionId,
    required this.latestUserQuery,
    required this.domainId,
    required this.contextAssembly,
    required this.intentGraph,
    required this.dialogueRoundScript,
    required this.domainCatalog,
    required this.domainCatalogVersion,
    required this.allowedToolNames,
    required this.executionShell,
    required this.previousSlotState,
    this.previousDomainPolicyBundle,
    required this.retrievalPolicy,
    required this.answerBoundaryPolicy,
    required this.understandingSnapshot,
    required this.templateVariables,
    required this.messages,
    required this.synthTemplateVersion,
    required this.fusionSynthTemplateVersion,
    required this.phaseOneResult,
    required this.synthesisReadiness,
    required this.evidenceLedger,
    required this.evidenceEvaluation,
    required this.toolResults,
    required this.supplementalTraces,
  });

  final String runId;
  final String traceId;
  final DateTime runStartAt;
  final String sessionId;
  final String latestUserQuery;
  final String domainId;
  final ContextAssemblyResult contextAssembly;
  final IntentGraph intentGraph;
  final DialogueRoundScript dialogueRoundScript;
  final List<String> domainCatalog;
  final String domainCatalogVersion;
  final List<String> allowedToolNames;
  final SkillExecutionShell executionShell;
  final SlotStateSnapshot previousSlotState;
  final DomainPolicyBundle? previousDomainPolicyBundle;

  /// LLM serde boundary: loaded from domain-specific JSON asset.
  final Map<String, dynamic> retrievalPolicy;

  final AnswerBoundaryPolicy answerBoundaryPolicy;

  /// LLM serde boundary: serialized understanding snapshot for synthesis prompt.
  final Map<String, dynamic> understandingSnapshot;

  /// LLM serde boundary: template variable bag consumed by prompt templates.
  final Map<String, dynamic> templateVariables;

  /// LLM serde boundary: chat messages for synthesis context.
  final List<Map<String, dynamic>> messages;

  final String synthTemplateVersion;
  final String fusionSynthTemplateVersion;
  final ReactRuntimeResult phaseOneResult;
  final SynthesisReadinessResult synthesisReadiness;
  final List<EvidenceLedgerEntry> evidenceLedger;
  final EvidenceEvaluationResult evidenceEvaluation;

  /// LLM serde boundary: tool call results for synthesis context.
  final List<Map<String, dynamic>> toolResults;

  final List<AssistantTraceEvent> supplementalTraces;

  /// Backward-compatible map representation consumed by legacy synthesis and
  /// finalize paths during the migration. Will be removed once all consumers
  /// switch to strongly-typed fields.
  @Deprecated('Transitional: will be removed after full pipeline migration')
  Map<String, dynamic> toLegacyMap() => <String, dynamic>{
    'runId': runId,
    'traceId': traceId,
    'runStartAt': runStartAt,
    'sessionId': sessionId,
    'latestUserQuery': latestUserQuery,
    'domainId': domainId,
    'contextAssembly': contextAssembly,
    'intentGraph': intentGraph,
    'dialogueRoundScript': dialogueRoundScript,
    'domainCatalog': domainCatalog,
    'domainCatalogVersion': domainCatalogVersion,
    'allowedToolNames': allowedToolNames,
    'executionShell': executionShell,
    'previousSlotState': previousSlotState,
    'previousDomainPolicyBundle': previousDomainPolicyBundle,
    'retrievalPolicy': retrievalPolicy,
    'answerBoundaryPolicy': answerBoundaryPolicy,
    'understandingSnapshot': understandingSnapshot,
    'templateVariables': templateVariables,
    'messages': messages,
    'synthTemplateVersion': synthTemplateVersion,
    'fusionSynthTemplateVersion': fusionSynthTemplateVersion,
    'phaseOneResult': phaseOneResult,
    'synthesisReadiness': synthesisReadiness,
    'evidenceLedger': evidenceLedger,
    'evidenceEvaluation': evidenceEvaluation,
    'toolResults': toolResults,
    'supplementalTraces': supplementalTraces,
  };
}
