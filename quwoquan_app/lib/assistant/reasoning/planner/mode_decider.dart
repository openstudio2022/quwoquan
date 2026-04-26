import 'package:quwoquan_app/assistant/contracts/recall_result.dart';
import 'package:quwoquan_app/assistant/contracts/task_graph_contract.dart';
import 'package:quwoquan_app/assistant/contracts/understanding_result_contract.dart';

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

  factory ModeDecision.fromJson(Map<String, dynamic> json) {
    final rawMode = (json['mode'] as String?)?.trim() ?? '';
    return ModeDecision(
      mode: rawMode == 'multiAgent' || rawMode == 'multi_agent'
          ? AgentMode.multiAgent
          : AgentMode.singleAgent,
      reason: (json['reason'] as String?)?.trim() ?? 'default_single',
      subagentCount: (json['subagentCount'] as num?)?.toInt() ?? 1,
      budgetMultiplier: (json['budgetMultiplier'] as num?)?.toDouble() ?? 1.0,
    );
  }

  Map<String, dynamic> toJson() => <String, dynamic>{
    'mode': mode.name,
    'reason': reason,
    'subagentCount': subagentCount,
    'budgetMultiplier': budgetMultiplier,
  };
}

/// Decides whether to use single-agent or multi-agent orchestration based on
/// the intent graph and recall result.
///
/// Current implementation is rule-based. Future versions may use an LLM call
/// or ML classifier to make the decision.
class ModeDecider {
  const ModeDecider({this.multiAgentThreshold = 2});

  /// Minimum number of distinct domains to trigger multi-agent mode.
  final int multiAgentThreshold;

  ModeDecision decide({
    required UnderstandingResult understandingResult,
    required TaskGraph taskGraph,
    RecallResult? recallResult,
  }) {
    final intentCount = understandingResult.intents.length;
    final toolCount = taskGraph.tasks
        .map((task) => task.toolName.trim())
        .where((toolName) => toolName.isNotEmpty)
        .toSet()
        .length;
    if (intentCount >= multiAgentThreshold && toolCount >= multiAgentThreshold) {
      return ModeDecision(
        mode: AgentMode.multiAgent,
        reason: 'multi_intent_task_graph',
        subagentCount: intentCount,
        budgetMultiplier: 0.8,
      );
    }
    return const ModeDecision(
      mode: AgentMode.singleAgent,
      reason: 'typed_default_single',
    );
  }
}
