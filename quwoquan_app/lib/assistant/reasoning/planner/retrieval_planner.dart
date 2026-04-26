import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/contracts/search_plan_contract.dart';
import 'package:quwoquan_app/assistant/orchestration/retrieval_tool_selection_policy.dart';
import 'package:quwoquan_app/assistant/reasoning/geo/geo_scope_support.dart';
import 'package:quwoquan_app/assistant/reasoning/planner/problem_framer.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';

class BaselineRetrievalPlan {
  const BaselineRetrievalPlan({
    required this.reasoning,
    required this.calls,
    this.searchPlans = const <SearchPlanItem>[],
    this.blockingDimensions = const <String>[],
  });

  final String reasoning;
  final List<AssistantToolCall> calls;
  final List<SearchPlanItem> searchPlans;
  final List<String> blockingDimensions;
}

/// DEPRECATED: label/dimension/reasoning 字符串应迁至 typed contract 与 asset。
/// 见 [canonical_truth_sources.md]。
class DefaultRetrievalPlanner {
  const DefaultRetrievalPlanner();

  BaselineRetrievalPlan? plan({
    required ProblemFrame frame,
    required List<String> availableTools,
    List<SearchPlanItem>? preComputedSearchPlans,
  }) {
    if (frame.normalizedQuery.isEmpty) return null;
    final searchPlans =
        (preComputedSearchPlans != null && preComputedSearchPlans.isNotEmpty)
        ? preComputedSearchPlans
        : _buildSearchPlans(frame);
    final retrievalToolName = _preferredRetrievalToolName(
      availableTools,
      searchPlans: searchPlans,
    );
    if (retrievalToolName.isEmpty) return null;
    final blockingDimensions = searchPlans
        .map((item) => item.dimension.displayLabel)
        .where((item) => item.trim().isNotEmpty)
        .toList(growable: false);
    return BaselineRetrievalPlan(
      reasoning: '',
      searchPlans: searchPlans,
      blockingDimensions: blockingDimensions,
      calls: <AssistantToolCall>[
        AssistantToolCall(
          name: retrievalToolName,
          arguments: <String, dynamic>{
            'query': frame.normalizedQuery,
            'mode': 'result',
            'queryNormalization': _queryNormalization(frame),
            'resolvedGeoScope': frame.resolvedGeoScope.toJson(),
            if (frame.timeScope.isNotEmpty) 'timeScope': frame.timeScope,
            if (frame.timeRangeStart.isNotEmpty)
              'timeRangeStart': frame.timeRangeStart,
            if (frame.timeRangeEnd.isNotEmpty)
              'timeRangeEnd': frame.timeRangeEnd,
            if (frame.timePoint.isNotEmpty) 'timePoint': frame.timePoint,
            if (frame.timezone.isNotEmpty) 'timezone': frame.timezone,
            if (searchPlans.isNotEmpty)
              'searchPlans': searchPlans
                  .map((item) => item.toJson())
                  .toList(growable: false),
            if (frame.entityRefs.isNotEmpty) 'entityRefs': frame.entityRefs,
            if (frame.negativeKeywords.isNotEmpty)
              'negativeKeywords': frame.negativeKeywords,
          },
        ),
      ],
    );
  }

  String _preferredRetrievalToolName(
    List<String> availableTools, {
    required List<SearchPlanItem> searchPlans,
  }) {
    return const RetrievalToolSelectionPolicy().select(
      availableToolNames: availableTools,
      searchPlans: searchPlans,
    );
  }

  Map<String, dynamic> _queryNormalization(ProblemFrame frame) {
    return <String, dynamic>{
      'normalizedQuery': frame.normalizedQuery,
      'query': frame.normalizedQuery,
      'entityRefs': frame.entityRefs,
      'negativeKeywords': frame.negativeKeywords,
      'answerShape': frame.answerShapeKind.wireName,
      'freshnessNeed': frame.freshnessNeedKind.wireName,
      'excludedScopes': frame.excludedScopes,
      'resolvedGeoScope': frame.resolvedGeoScope.toJson(),
      if (frame.referenceNowIso.isNotEmpty)
        'referenceNowIso': frame.referenceNowIso,
      if (frame.timezone.isNotEmpty) 'timezone': frame.timezone,
      if (frame.resolvedTemporalHints.isNotEmpty)
        'resolvedTemporalHints': frame.resolvedTemporalHints,
      if (frame.timeScope.isNotEmpty) 'timeScope': frame.timeScope,
      if (frame.timeRangeStart.isNotEmpty)
        'timeRangeStart': frame.timeRangeStart,
      if (frame.timeRangeEnd.isNotEmpty) 'timeRangeEnd': frame.timeRangeEnd,
      if (frame.timePoint.isNotEmpty) 'timePoint': frame.timePoint,
    };
  }

  SearchPlanItem _searchPlan({
    required ProblemFrame frame,
    required String id,
    required String query,
    required String label,
    required SearchPlanDimension dimension,
  }) {
    return SearchPlanItem(
      id: id,
      query: query,
      label: label,
      dimension: dimension,
      entityRefs: mergeGeoAnchors(frame.entityRefs, frame.resolvedGeoScope),
      negativeKeywords: frame.negativeKeywords,
      timeScope: frame.timeScope,
      timeRangeStart: frame.timeRangeStart,
      timeRangeEnd: frame.timeRangeEnd,
      timePoint: frame.timePoint,
      timezone: frame.timezone,
    );
  }

  List<SearchPlanItem> _buildSearchPlans(ProblemFrame frame) {
    if (!frame.requiresExternalEvidence) return const <SearchPlanItem>[];
    switch (frame.answerShapeKind) {
      case AnswerShape.comparison:
      case AnswerShape.options:
        return <SearchPlanItem>[
          _searchPlan(
            frame: frame,
            id: 'candidate_space',
            query: '${frame.normalizedQuery} 备选 方案',
            label: '候选范围',
            dimension: SearchPlanDimension.candidateSpace,
          ),
          _searchPlan(
            frame: frame,
            id: 'fit_scenarios',
            query: '${frame.normalizedQuery} 适用 场景',
            label: '适用场景',
            dimension: SearchPlanDimension.fitScenarios,
          ),
          _searchPlan(
            frame: frame,
            id: 'risks',
            query: '${frame.normalizedQuery} 风险 注意事项',
            label: '风险边界',
            dimension: SearchPlanDimension.riskBoundaries,
          ),
        ];
      case AnswerShape.decisionReady:
        return <SearchPlanItem>[
          _searchPlan(
            frame: frame,
            id: 'key_facts',
            query: '${frame.normalizedQuery} 关键事实',
            label: '关键事实',
            dimension: SearchPlanDimension.keyFacts,
          ),
          _searchPlan(
            frame: frame,
            id: 'decision_threshold',
            query: '${frame.normalizedQuery} 判断条件',
            label: '判断条件',
            dimension: SearchPlanDimension.decisionThreshold,
          ),
        ];
      default:
        break;
    }
    if (frame.problemClassKind == ProblemClass.complexReasoning) {
      return <SearchPlanItem>[
        _searchPlan(
          frame: frame,
          id: 'candidate_space',
          query: '${frame.normalizedQuery} 备选 方案',
          label: '候选范围',
          dimension: SearchPlanDimension.candidateSpace,
        ),
        _searchPlan(
          frame: frame,
          id: 'fit_scenarios',
          query: '${frame.normalizedQuery} 适用 场景',
          label: '适用场景',
          dimension: SearchPlanDimension.fitScenarios,
        ),
        _searchPlan(
          frame: frame,
          id: 'risks',
          query: '${frame.normalizedQuery} 风险 注意事项',
          label: '风险边界',
          dimension: SearchPlanDimension.riskBoundaries,
        ),
      ];
    }
    if (frame.problemClassKind == ProblemClass.evidenceLookup) {
      return <SearchPlanItem>[
        _searchPlan(
          frame: frame,
          id: 'key_facts',
          query: '${frame.normalizedQuery} 关键事实',
          label: '关键事实',
          dimension: SearchPlanDimension.keyFacts,
        ),
        _searchPlan(
          frame: frame,
          id: 'decision_threshold',
          query: '${frame.normalizedQuery} 判断条件',
          label: '判断条件',
          dimension: SearchPlanDimension.decisionThreshold,
        ),
      ];
    }
    return const <SearchPlanItem>[];
  }
}
