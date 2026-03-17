import 'package:quwoquan_app/assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/assistant/contracts/intent_graph.dart';
import 'package:quwoquan_app/assistant/contracts/query_task_contract.dart';

IntentGraph? extractIntentGraphFromModelPayload(
  Map<String, dynamic> payload, {
  AssistantTurnOutput? parsedTurn,
}) {
  final turnIntentGraph = parsedTurn?.intentGraph;
  final candidates = <Map<String, dynamic>>[
    if (turnIntentGraph != null) turnIntentGraph.toJson(),
    if (payload['intentGraph'] is Map)
      (payload['intentGraph'] as Map).cast<String, dynamic>(),
    if (payload['result'] is Map &&
        ((payload['result'] as Map)['intentGraph'] is Map))
      (((payload['result'] as Map)['intentGraph'] as Map)
          .cast<String, dynamic>()),
    if (_looksLikeIntentGraphPayload(payload)) payload,
  ];
  for (final candidate in candidates) {
    final parsed = _tryParseIntentGraph(candidate);
    if (parsed != null) {
      return parsed;
    }
  }
  return null;
}

List<QueryTask> extractQueryTasksFromModelPayload(
  Map<String, dynamic> payload, {
  AssistantTurnOutput? parsedTurn,
  IntentGraph? extractedIntentGraph,
}) {
  final turnIntentGraph = parsedTurn?.intentGraph;
  final candidates = <Object?>[
    payload['queryTasks'],
    if (turnIntentGraph?.queryTasks.isNotEmpty ?? false)
      QueryTask.toJsonList(turnIntentGraph!.queryTasks),
    if (payload['intentGraph'] is Map)
      (payload['intentGraph'] as Map)['queryTasks'],
    if (payload['result'] is Map) (payload['result'] as Map)['queryTasks'],
    _extractToolCallQueryTasks(payload),
    if (extractedIntentGraph?.queryTasks.isNotEmpty ?? false)
      QueryTask.toJsonList(extractedIntentGraph!.queryTasks),
  ];
  for (final candidate in candidates) {
    final normalized = QueryTask.normalizeList(candidate);
    if (normalized.isNotEmpty) {
      return normalized;
    }
  }
  return const <QueryTask>[];
}

IntentGraph? _tryParseIntentGraph(Map<String, dynamic> candidate) {
  try {
    return IntentGraph.fromJson(candidate);
  } catch (_) {
    return null;
  }
}

Object? _extractToolCallQueryTasks(Map<String, dynamic> payload) {
  final toolCalls = payload['toolCalls'];
  if (toolCalls is! List) {
    return null;
  }
  for (final rawCall in toolCalls) {
    if (rawCall is! Map) {
      continue;
    }
    final arguments = (rawCall['arguments'] as Map?)?.cast<String, dynamic>();
    if (arguments == null) {
      continue;
    }
    final queryTasks = arguments['queryTasks'];
    if (queryTasks is List && queryTasks.isNotEmpty) {
      return queryTasks;
    }
  }
  return null;
}

bool _looksLikeIntentGraphPayload(Map<String, dynamic> payload) {
  var score = 0;
  const keys = <String>[
    'userGoal',
    'problemShape',
    'primarySkill',
    'problemClass',
    'inferredMotive',
    'secondarySkills',
    'queryNormalization',
    'contextSlots',
    'globalConstraints',
    'clarificationNeeded',
  ];
  for (final key in keys) {
    final value = payload[key];
    if (value == null) {
      continue;
    }
    if (value is String && value.trim().isEmpty) {
      continue;
    }
    if (value is List && value.isEmpty) {
      continue;
    }
    if (value is Map && value.isEmpty) {
      continue;
    }
    score += 1;
  }
  return score >= 2;
}
