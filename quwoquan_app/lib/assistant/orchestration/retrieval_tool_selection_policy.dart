import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/contracts/search_plan_contract.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_metadata_registry.dart';

/// Runtime-owned deterministic retrieval routing policy.
class RetrievalToolSelectionPolicy {
  const RetrievalToolSelectionPolicy();

  String select({
    required Iterable<String> availableToolNames,
    Iterable<SearchPlanItem> searchPlans = const <SearchPlanItem>[],
  }) {
    final available = availableToolNames
        .map((item) => item.trim())
        .where(AssistantToolNames.isRetrievalName)
        .toSet();
    if (available.isEmpty) return '';

    final plans = searchPlans.toList(growable: false);
    final hasExternalPlans = plans.any(_requiresExternalWeb);
    final hasAppPlans =
        plans.isEmpty ||
        plans.any((plan) {
          return !_requiresExternalWeb(plan);
        });
    if (hasExternalPlans &&
        hasAppPlans &&
        available.contains(AssistantToolNames.search)) {
      return AssistantToolNames.search;
    }
    if (hasExternalPlans && available.contains(AssistantToolNames.webSearch)) {
      return AssistantToolNames.webSearch;
    }
    if (hasAppPlans && available.contains(AssistantToolNames.appSearch)) {
      return AssistantToolNames.appSearch;
    }
    if (available.contains(AssistantToolNames.search)) {
      return AssistantToolNames.search;
    }
    if (available.contains(AssistantToolNames.webSearch)) {
      return AssistantToolNames.webSearch;
    }
    return available.contains(AssistantToolNames.appSearch)
        ? AssistantToolNames.appSearch
        : '';
  }

  bool _requiresExternalWeb(SearchPlanItem plan) {
    return plan.authorityDomains.isNotEmpty ||
        plan.freshnessHoursMax > 0 ||
        plan.freshnessNeed != FreshnessNeed.unspecified ||
        plan.dimension == SearchPlanDimension.latestSignal;
  }
}
