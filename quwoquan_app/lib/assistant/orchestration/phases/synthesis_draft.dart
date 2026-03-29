import 'package:quwoquan_app/assistant/contracts/aggregation_state.dart';
import 'package:quwoquan_app/assistant/contracts/answer_boundary_policy.dart';
import 'package:quwoquan_app/assistant/contracts/context_assembly_result.dart';
import 'package:quwoquan_app/assistant/contracts/dialogue_round_script.dart';
import 'package:quwoquan_app/assistant/contracts/intent_graph.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/skill_run.dart';
import 'package:quwoquan_app/assistant/contracts/subagent_plan.dart';
import 'package:quwoquan_app/assistant/contracts/synthesis_readiness_result.dart';
import 'package:quwoquan_app/assistant/protocol/profile_update_proposal.dart';
import 'package:quwoquan_app/assistant/orchestration/assistant_orchestration_runtime.dart';
import 'package:quwoquan_app/assistant/skill/domain/skill_manifest.dart';

/// Typed seam between synthesis execution and final response materialization.
class SynthesisDraft {
  const SynthesisDraft({
    required this.runId,
    required this.traceId,
    required this.sessionId,
    required this.contextAssembly,
    required this.synthesisReadiness,
    required this.finalResult,
    required this.intentGraph,
    required this.skillRuns,
    required this.aggregationState,
    required this.subagentPlan,
    required this.subagentRuns,
    required this.dialogueRoundScript,
    required this.candidateDomains,
    required this.skillExecutionShell,
    required this.templateVersionUsed,
    required this.domainCatalogVersion,
    required this.retrievalPolicy,
    required this.answerBoundaryPolicy,
    required this.previousSlotState,
    this.phaseOneRoutingDiagnostics = const <String, dynamic>{},
    this.understandingSnapshot = const <String, dynamic>{},
    this.retrievalProcessing = const <String, dynamic>{},
    this.historicalThinkingSnapshot = const <String, dynamic>{},
    this.streamedAnswerReadinessSummary = '',
    this.previousDomainPolicyBundle,
    this.profileUpdateProposal,
    this.responseDegraded = false,
    this.blockedProcessStepId = ProcessStepId.unknown,
    this.blockedProcessMessage = '',
  });

  final String runId;
  final String traceId;
  final String sessionId;
  final ContextAssemblyResult contextAssembly;
  final SynthesisReadinessResult synthesisReadiness;
  final ReactRuntimeResult finalResult;
  final IntentGraph intentGraph;
  final List<SkillRun> skillRuns;
  final AggregationState aggregationState;
  final List<SubagentPlan> subagentPlan;
  final List<Map<String, dynamic>> subagentRuns;
  final DialogueRoundScript dialogueRoundScript;
  final List<String> candidateDomains;
  final SkillExecutionShell skillExecutionShell;
  final String templateVersionUsed;
  final String domainCatalogVersion;
  final Map<String, dynamic> retrievalPolicy;
  final AnswerBoundaryPolicy answerBoundaryPolicy;
  final SlotStateSnapshot previousSlotState;
  final Map<String, dynamic> phaseOneRoutingDiagnostics;
  final Map<String, dynamic> understandingSnapshot;
  final Map<String, dynamic> retrievalProcessing;
  final Map<String, dynamic> historicalThinkingSnapshot;
  final String streamedAnswerReadinessSummary;
  final DomainPolicyBundle? previousDomainPolicyBundle;
  final ProfileUpdateProposal? profileUpdateProposal;
  final bool responseDegraded;
  final ProcessStepId blockedProcessStepId;
  final String blockedProcessMessage;
}
