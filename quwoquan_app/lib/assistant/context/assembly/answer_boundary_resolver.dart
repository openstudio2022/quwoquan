import 'package:quwoquan_app/assistant/contracts/answer_boundary_policy.dart';
import 'package:quwoquan_app/assistant/contracts/context_assembly_result.dart';
import 'package:quwoquan_app/assistant/contracts/intent_graph.dart';
import 'package:quwoquan_app/assistant/contracts/query_task_contract.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';

class AnswerBoundaryResolver {
  const AnswerBoundaryResolver();

  AnswerBoundaryPolicy resolve({
    required IntentGraph intentGraph,
    required ContextAssemblyResult contextAssembly,
    required Map<String, dynamic> retrievalPolicy,
    List<QueryTask> queryTasks = const <QueryTask>[],
  }) {
    final effectiveTasks = queryTasks.isNotEmpty
        ? queryTasks
        : intentGraph.queryTasks;
    final requiredDimensions = normalizedTaskDimensions(effectiveTasks);
    final authorityDomains = _uniqueNonEmpty(<String>[
      ...intentGraph.authorityDomains,
      ...((retrievalPolicy['authorityDomains'] as List?)
              ?.map((item) => item.toString().trim()) ??
          const Iterable<String>.empty()),
      for (final task in effectiveTasks) ...task.authorityDomains,
    ]);
    final authorityRequired = retrievalPolicy['authorityRequired'] == true;
    final freshnessHoursMax = _resolveFreshnessHoursMax(
      intentGraph: intentGraph,
      retrievalPolicy: retrievalPolicy,
      queryTasks: effectiveTasks,
    );
    final evidenceRequired =
        intentGraph.requiresExternalEvidence ||
        intentGraph.mustVerifyClaims ||
        contextAssembly.hasRealtimeNeed ||
        authorityRequired ||
        requiredDimensions.isNotEmpty;
    final requireToolResultBeforeSynthesis =
        contextAssembly.hasRealtimeNeed || intentGraph.mustVerifyClaims;
    final allowBoundedAnswer =
        !evidenceRequired ||
        (!authorityRequired &&
            !requireToolResultBeforeSynthesis &&
            requiredDimensions.isEmpty);
    final summary = evidenceRequired
        ? (allowBoundedAnswer
              ? '当前问题允许基于已覆盖证据先给出 bounded answer。'
              : '当前问题需要先满足证据时效、权威或关键维度后再进入成答。')
        : '当前问题不强制依赖外部证据。';
    return AnswerBoundaryPolicy(
      evidenceRequired: evidenceRequired,
      authorityRequired: authorityRequired,
      requireToolResultBeforeSynthesis: requireToolResultBeforeSynthesis,
      allowBoundedAnswer: allowBoundedAnswer,
      freshnessHoursMax: freshnessHoursMax,
      authorityDomains: authorityDomains,
      requiredDimensions: requiredDimensions,
      blockingDimensions: requiredDimensions,
      expansionPolicy: evidenceRequired
          ? ContextScopeExpansionPolicy.expandScopeAndRequery
          : ContextScopeExpansionPolicy.none,
      insufficiencyReason: evidenceRequired
          ? PlannerReasonCode.needMoreEvidence
          : PlannerReasonCode.readyToAnswer,
      summary: summary,
    );
  }

  bool requiresQueryTaskDesign({
    required IntentGraph intentGraph,
    required Map<String, dynamic> contextEnvelope,
  }) {
    if (intentGraph.queryTasks.isNotEmpty) {
      return false;
    }
    final typedSignals =
        (contextEnvelope['typedSignals'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    return intentGraph.requiresExternalEvidence ||
        intentGraph.mustVerifyClaims ||
        typedSignals['requiresRealtimeEvidence'] == true ||
        intentGraph.authorityDomains.isNotEmpty ||
        intentGraph.freshnessHoursMax > 0;
  }

  static List<String> normalizedTaskDimensions(Iterable<QueryTask> queryTasks) {
    return _uniqueNonEmpty(
      queryTasks.map((task) => task.dimensionCode).where((item) => item.isNotEmpty),
    );
  }

  int _resolveFreshnessHoursMax({
    required IntentGraph intentGraph,
    required Map<String, dynamic> retrievalPolicy,
    required List<QueryTask> queryTasks,
  }) {
    final candidates = <int>[
      for (final task in queryTasks)
        if (task.freshnessHoursMax > 0) task.freshnessHoursMax,
      if (intentGraph.freshnessHoursMax > 0) intentGraph.freshnessHoursMax,
    ];
    final policyMax =
        (retrievalPolicy['defaultFreshnessHoursMax'] as num?)?.toInt() ?? 0;
    if (policyMax > 0) {
      candidates.add(policyMax);
    }
    if (candidates.isEmpty) {
      return 72;
    }
    candidates.sort();
    return candidates.first;
  }

  static List<String> _uniqueNonEmpty(Iterable<String> values) {
    final seen = <String>{};
    final normalized = <String>[];
    for (final raw in values) {
      final value = raw.trim();
      if (value.isEmpty || !seen.add(value)) {
        continue;
      }
      normalized.add(value);
    }
    return normalized;
  }
}
