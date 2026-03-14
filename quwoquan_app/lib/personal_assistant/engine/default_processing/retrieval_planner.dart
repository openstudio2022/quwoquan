import 'package:quwoquan_app/personal_assistant/contracts/query_task_contract.dart';
import 'package:quwoquan_app/personal_assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/personal_assistant/engine/default_processing/problem_framer.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_schema.dart';

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
  }) {
    if (frame.normalizedQuery.isEmpty) return null;
    if (!availableTools.contains('web_search')) return null;
    switch (frame.answerShapeKind) {
      case AnswerShape.comparison:
      case AnswerShape.options:
      case AnswerShape.decisionReady:
      default:
        break;
    }
    return BaselineRetrievalPlan(
      reasoning: '',
      queryTasks: const <QueryTask>[],
      blockingDimensions: const <String>[],
      calls: <AssistantToolCall>[
        AssistantToolCall(
          name: 'web_search',
          arguments: <String, dynamic>{
            'query': frame.normalizedQuery,
            'queryNormalization': _queryNormalization(frame),
            if (frame.entityAnchors.isNotEmpty)
              'entityAnchors': frame.entityAnchors,
            if (frame.negativeKeywords.isNotEmpty)
              'negativeKeywords': frame.negativeKeywords,
          },
        ),
      ],
    );
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
}
