import 'package:quwoquan_app/personal_assistant/contracts/intent_graph.dart';
import 'package:quwoquan_app/personal_assistant/contracts/recall_result.dart';
import 'package:quwoquan_app/personal_assistant/contracts/runtime_enums.dart';

/// Execution mode for the current assistant turn.
enum AgentMode {
  /// Single agent handles the entire query end-to-end.
  singleAgent,

  /// Multiple sub-agents run in parallel, results are aggregated.
  multiAgent,
}

/// Decision output describing the chosen agent mode and its rationale.
class ModeDecision {
  const ModeDecision({
    required this.mode,
    required this.reason,
    this.subagentCount = 1,
    this.budgetMultiplier = 1.0,
  });

  final AgentMode mode;
  final String reason;
  final int subagentCount;

  /// Multiplier applied to tool/iteration budgets for multi-agent runs.
  final double budgetMultiplier;

  bool get isMultiAgent => mode == AgentMode.multiAgent;
}

/// Decides whether to use single-agent or multi-agent orchestration based on
/// the intent graph and recall result.
///
/// Current implementation is rule-based. Future versions may use an LLM call
/// or ML classifier to make the decision.
class ModeDecider {
  const ModeDecider({
    this.multiAgentThreshold = 2,
  });

  /// Minimum number of distinct domains to trigger multi-agent mode.
  final int multiAgentThreshold;

  ModeDecision decide({
    required IntentGraph intentGraph,
    RecallResult? recallResult,
  }) {
    if (intentGraph.isFastConvergence) {
      return const ModeDecision(
        mode: AgentMode.singleAgent,
        reason: 'fast_convergence_problem',
      );
    }

    if (intentGraph.isMultiSkill &&
        intentGraph.secondarySkills.length >= multiAgentThreshold - 1) {
      return ModeDecision(
        mode: AgentMode.multiAgent,
        reason: 'multi_skill_intent',
        subagentCount: 1 + intentGraph.secondarySkills.length,
        budgetMultiplier: 0.7,
      );
    }

    if (intentGraph.problemClassType == ProblemClass.complexReasoning &&
        intentGraph.secondarySkills.isNotEmpty) {
      return ModeDecision(
        mode: AgentMode.multiAgent,
        reason: 'complex_reasoning_with_secondary',
        subagentCount: 1 + intentGraph.secondarySkills.length,
        budgetMultiplier: 0.8,
      );
    }

    return const ModeDecision(
      mode: AgentMode.singleAgent,
      reason: 'default_single',
    );
  }
}
