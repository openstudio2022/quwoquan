import 'package:quwoquan_app/personal_assistant/contracts/aggregation_state.dart';
import 'package:quwoquan_app/personal_assistant/contracts/intent_graph.dart';
import 'package:quwoquan_app/personal_assistant/contracts/skill_run.dart';
import 'package:quwoquan_app/personal_assistant/contracts/subagent_plan.dart';
import 'package:quwoquan_app/personal_assistant/engine/aggregation_gate.dart';
import 'package:quwoquan_app/personal_assistant/engine/mode_decider.dart';
import 'package:quwoquan_app/personal_assistant/skills/skill_manifest.dart';

/// Budget envelope for a single sub-agent within a multi-agent run.
class SubagentBudget {
  const SubagentBudget({
    required this.subagentId,
    required this.domainId,
    this.maxIterations = 3,
    this.toolBudget = 4,
    this.reflectionBudget = 0,
    this.freshnessHoursMax = 72,
  });

  final String subagentId;
  final String domainId;
  final int maxIterations;
  final int toolBudget;
  final int reflectionBudget;
  final int freshnessHoursMax;

  SkillExecutionShell toExecutionShell({
    required SkillExecutionShell baseShell,
  }) {
    return baseShell.copyWith(
      maxIterations: maxIterations,
      toolBudget: toolBudget,
      reflectionBudget: reflectionBudget,
      freshnessHoursMax: freshnessHoursMax,
    );
  }

  Map<String, dynamic> toJson() => <String, dynamic>{
        'subagentId': subagentId,
        'domainId': domainId,
        'maxIterations': maxIterations,
        'toolBudget': toolBudget,
        'reflectionBudget': reflectionBudget,
        'freshnessHoursMax': freshnessHoursMax,
      };
}

/// Dispatching result from the supervisor, ready for the agent loop to execute.
class SupervisorDispatch {
  const SupervisorDispatch({
    required this.subagentBudgets,
    required this.executionOrder,
    this.canParallelize = false,
    this.totalBudgetCeiling = 24,
  });

  final List<SubagentBudget> subagentBudgets;

  /// Groups of subagent IDs that can execute in parallel.
  /// Each inner list is a "wave" — all IDs in a wave may run concurrently,
  /// and waves are executed sequentially.
  final List<List<String>> executionOrder;

  final bool canParallelize;
  final int totalBudgetCeiling;

  int get totalToolBudget =>
      subagentBudgets.fold(0, (sum, b) => sum + b.toolBudget);
}

/// Orchestrates multi-agent runs: splits the intent graph into sub-agent
/// tasks, assigns budgets, decides execution order, and evaluates the
/// aggregated results.
///
/// For single-agent mode, this class is not used.
class MultiAgentSupervisor {
  MultiAgentSupervisor({
    AggregationGate? gate,
    this.maxParallelSubagents = 3,
    this.totalBudgetCeiling = 24,
  }) : _gate = gate ?? const AggregationGate();

  final AggregationGate _gate;
  final int maxParallelSubagents;
  final int totalBudgetCeiling;

  /// Dispatch sub-agents based on the intent graph and mode decision.
  SupervisorDispatch dispatch({
    required IntentGraph intentGraph,
    required ModeDecision modeDecision,
    required List<SubagentPlan> subagentPlans,
  }) {
    if (!modeDecision.isMultiAgent || subagentPlans.isEmpty) {
      return const SupervisorDispatch(
        subagentBudgets: <SubagentBudget>[],
        executionOrder: <List<String>>[],
      );
    }

    final budgetPerAgent = (totalBudgetCeiling / subagentPlans.length)
        .floor()
        .clamp(1, 8);

    final budgets = subagentPlans.map((plan) {
      final isFast = plan.problemClass == 'realtime_info' ||
          plan.problemClass == 'simple_qa';
      return SubagentBudget(
        subagentId: plan.subagentId,
        domainId: plan.domainId,
        maxIterations: isFast ? 2 : 4,
        toolBudget: isFast ? 1 : budgetPerAgent,
        reflectionBudget: isFast ? 0 : 1,
        freshnessHoursMax:
            plan.problemClass == 'realtime_info' ? 1 : 72,
      );
    }).toList(growable: false);

    final canParallel = budgets.length <= maxParallelSubagents;
    final order = canParallel
        ? <List<String>>[budgets.map((b) => b.subagentId).toList()]
        : budgets.map((b) => <String>[b.subagentId]).toList(growable: false);

    return SupervisorDispatch(
      subagentBudgets: budgets,
      executionOrder: order,
      canParallelize: canParallel,
      totalBudgetCeiling: totalBudgetCeiling,
    );
  }

  /// Evaluate whether all sub-agents have completed and determine next step.
  AggregationState evaluateAggregation({
    required IntentGraph intentGraph,
    required List<SkillRun> skillRuns,
    required Map<String, dynamic> answerPayload,
  }) {
    return _gate.evaluate(
      intentGraph: intentGraph,
      skillRuns: skillRuns,
      answerPayload: answerPayload,
    );
  }
}
