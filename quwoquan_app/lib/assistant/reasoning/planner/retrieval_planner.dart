import 'package:quwoquan_app/assistant/contracts/query_task_contract.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/reasoning/planner/problem_framer.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';

class BaselineRetrievalPlan {
  const BaselineRetrievalPlan({
    required this.reasoning,
    required this.calls,
    this.queryTasks = const <QueryTask>[],
    this.blockingDimensions = const <String>[],
  });

  final String reasoning;
  final List<AssistantToolCall> calls;
  final List<QueryTask> queryTasks;
  final List<String> blockingDimensions;
}

/// DEPRECATED: label/dimension/reasoning 字符串应迁至 typed contract 与 asset。
/// 见 [canonical_truth_sources.md]。
class DefaultRetrievalPlanner {
  const DefaultRetrievalPlanner();

  BaselineRetrievalPlan? plan({
    required ProblemFrame frame,
    required List<String> availableTools,
    List<QueryTask>? preComputedQueryTasks,
  }) {
    if (frame.normalizedQuery.isEmpty) return null;
    final retrievalToolName = _preferredRetrievalToolName(availableTools);
    if (retrievalToolName.isEmpty) return null;
    final queryTasks =
        (preComputedQueryTasks != null && preComputedQueryTasks.isNotEmpty)
        ? preComputedQueryTasks
        : _buildQueryTasks(frame);
    final blockingDimensions = queryTasks
        .map((item) => item.dimension.displayLabel)
        .where((item) => item.trim().isNotEmpty)
        .toList(growable: false);
    return BaselineRetrievalPlan(
      reasoning: '',
      queryTasks: queryTasks,
      blockingDimensions: blockingDimensions,
      calls: <AssistantToolCall>[
        AssistantToolCall(
          name: retrievalToolName,
          arguments: <String, dynamic>{
            'query': frame.normalizedQuery,
            'mode': 'result',
            'queryNormalization': _queryNormalization(frame),
            if (queryTasks.isNotEmpty)
              'queryTasks': queryTasks
                  .map((item) => item.toJson())
                  .toList(growable: false),
            if (frame.entityAnchors.isNotEmpty)
              'entityAnchors': frame.entityAnchors,
            if (frame.negativeKeywords.isNotEmpty)
              'negativeKeywords': frame.negativeKeywords,
          },
        ),
      ],
    );
  }

  String _preferredRetrievalToolName(List<String> availableTools) {
    if (availableTools.contains('search')) {
      return 'search';
    }
    if (availableTools.contains('web_search')) {
      return 'web_search';
    }
    return '';
  }

  Map<String, dynamic> _queryNormalization(ProblemFrame frame) {
    return <String, dynamic>{
      'normalizedQuery': frame.normalizedQuery,
      'query': frame.normalizedQuery,
      'entityAnchors': frame.entityAnchors,
      'negativeKeywords': frame.negativeKeywords,
      'answerShape': frame.answerShapeKind.wireName,
      'freshnessNeed': frame.freshnessNeedKind.wireName,
      'excludedScopes': frame.excludedScopes,
    };
  }

  List<QueryTask> _buildQueryTasks(ProblemFrame frame) {
    if (!frame.requiresExternalEvidence) return const <QueryTask>[];
    switch (frame.answerShapeKind) {
      case AnswerShape.comparison:
      case AnswerShape.options:
        return <QueryTask>[
          QueryTask(
            id: 'candidate_space',
            query: '${frame.normalizedQuery} 备选 方案',
            label: '候选范围',
            dimension: QueryTaskDimension.candidateSpace,
            entityAnchors: frame.entityAnchors,
            negativeKeywords: frame.negativeKeywords,
          ),
          QueryTask(
            id: 'fit_scenarios',
            query: '${frame.normalizedQuery} 适用 场景',
            label: '适用场景',
            dimension: QueryTaskDimension.fitScenarios,
            entityAnchors: frame.entityAnchors,
            negativeKeywords: frame.negativeKeywords,
          ),
          QueryTask(
            id: 'risks',
            query: '${frame.normalizedQuery} 风险 注意事项',
            label: '风险边界',
            dimension: QueryTaskDimension.riskBoundaries,
            entityAnchors: frame.entityAnchors,
            negativeKeywords: frame.negativeKeywords,
          ),
        ];
      case AnswerShape.decisionReady:
        return <QueryTask>[
          QueryTask(
            id: 'key_facts',
            query: '${frame.normalizedQuery} 关键事实',
            label: '关键事实',
            dimension: QueryTaskDimension.keyFacts,
            entityAnchors: frame.entityAnchors,
            negativeKeywords: frame.negativeKeywords,
          ),
          QueryTask(
            id: 'decision_threshold',
            query: '${frame.normalizedQuery} 判断条件',
            label: '判断条件',
            dimension: QueryTaskDimension.decisionThreshold,
            entityAnchors: frame.entityAnchors,
            negativeKeywords: frame.negativeKeywords,
          ),
        ];
      default:
        break;
    }
    if (frame.problemClassKind == ProblemClass.complexReasoning) {
      return <QueryTask>[
        QueryTask(
          id: 'candidate_space',
          query: '${frame.normalizedQuery} 备选 方案',
          label: '候选范围',
          dimension: QueryTaskDimension.candidateSpace,
          entityAnchors: frame.entityAnchors,
          negativeKeywords: frame.negativeKeywords,
        ),
        QueryTask(
          id: 'fit_scenarios',
          query: '${frame.normalizedQuery} 适用 场景',
          label: '适用场景',
          dimension: QueryTaskDimension.fitScenarios,
          entityAnchors: frame.entityAnchors,
          negativeKeywords: frame.negativeKeywords,
        ),
        QueryTask(
          id: 'risks',
          query: '${frame.normalizedQuery} 风险 注意事项',
          label: '风险边界',
          dimension: QueryTaskDimension.riskBoundaries,
          entityAnchors: frame.entityAnchors,
          negativeKeywords: frame.negativeKeywords,
        ),
      ];
    }
    if (frame.problemClassKind == ProblemClass.evidenceLookup) {
      return <QueryTask>[
        QueryTask(
          id: 'key_facts',
          query: '${frame.normalizedQuery} 关键事实',
          label: '关键事实',
          dimension: QueryTaskDimension.keyFacts,
          entityAnchors: frame.entityAnchors,
          negativeKeywords: frame.negativeKeywords,
        ),
        QueryTask(
          id: 'decision_threshold',
          query: '${frame.normalizedQuery} 判断条件',
          label: '判断条件',
          dimension: QueryTaskDimension.decisionThreshold,
          entityAnchors: frame.entityAnchors,
          negativeKeywords: frame.negativeKeywords,
        ),
      ];
    }
    return const <QueryTask>[];
  }
}
