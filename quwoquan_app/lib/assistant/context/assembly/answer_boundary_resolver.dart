import 'package:quwoquan_app/assistant/contracts/answer_boundary_policy.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_plan_view.dart';
import 'package:quwoquan_app/assistant/contracts/context_assembly_result.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/contracts/search_plan_contract.dart';

class AnswerBoundaryResolver {
  const AnswerBoundaryResolver();

  AnswerBoundaryPolicy resolve({
    required AssistantPlanView planView,
    required ContextAssemblyResult contextAssembly,
    required Map<String, dynamic> retrievalPolicy,
    List<SearchPlanItem> searchPlans = const <SearchPlanItem>[],
  }) {
    final effectivePlans = searchPlans.isNotEmpty
        ? searchPlans
        : planView.searchPlans;
    final requiredDimensions = normalizedPlanDimensions(effectivePlans);
    final authorityDomains = _uniqueNonEmpty(<String>[
      ...planView.authorityDomains,
      ...((retrievalPolicy['authorityDomains'] as List?)?.map(
            (item) => item.toString().trim(),
          ) ??
          const Iterable<String>.empty()),
      for (final plan in effectivePlans) ...plan.authorityDomains,
    ]);
    final authorityRequired = retrievalPolicy['authorityRequired'] == true;
    final freshnessHoursMax = _resolveFreshnessHoursMax(
      retrievalPolicy: retrievalPolicy,
      searchPlans: effectivePlans,
    );
    final evidenceRequired =
        planView.requiresExternalEvidence ||
        planView.mustVerifyClaims ||
        contextAssembly.hasRealtimeNeed ||
        authorityRequired ||
        requiredDimensions.isNotEmpty;
    final requireToolResultBeforeSynthesis =
        contextAssembly.hasRealtimeNeed || planView.mustVerifyClaims;
    final allowBoundedAnswer =
        !evidenceRequired ||
        (!authorityRequired &&
            !requireToolResultBeforeSynthesis &&
            requiredDimensions.isEmpty);
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
      summary: '',
    );
  }

  bool requiresSearchPlanDesign({
    required AssistantPlanView planView,
    required Map<String, dynamic> contextEnvelope,
  }) {
    if (planView.searchPlans.isNotEmpty) {
      return false;
    }
    final typedSignals =
        (contextEnvelope['typedSignals'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    return planView.requiresExternalEvidence ||
        planView.mustVerifyClaims ||
        typedSignals['requiresRealtimeEvidence'] == true ||
        planView.authorityDomains.isNotEmpty;
  }

  static List<String> normalizedPlanDimensions(
    Iterable<SearchPlanItem> searchPlans,
  ) {
    return _uniqueNonEmpty(
      searchPlans
          .map((plan) => plan.dimensionCode)
          .where((item) => item.isNotEmpty),
    );
  }

  int _resolveFreshnessHoursMax({
    required Map<String, dynamic> retrievalPolicy,
    required List<SearchPlanItem> searchPlans,
  }) {
    final candidates = <int>[
      for (final plan in searchPlans)
        if (plan.freshnessHoursMax > 0) plan.freshnessHoursMax,
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
