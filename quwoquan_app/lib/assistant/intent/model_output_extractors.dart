import 'package:quwoquan_app/assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/assistant/contracts/task_graph_contract.dart';
import 'package:quwoquan_app/assistant/contracts/understanding_result_contract.dart';

UnderstandingResult? extractUnderstandingResultFromModelPayload(
  Map<String, dynamic> payload, {
  AssistantTurnOutput? parsedTurn,
}) {
  final turnUnderstanding = parsedTurn?.understandingResult;
  final candidates = <Map<String, dynamic>>[
    if (turnUnderstanding != null && turnUnderstanding.intents.isNotEmpty)
      turnUnderstanding.toJson(),
    if (payload['understandingResult'] is Map)
      (payload['understandingResult'] as Map).cast<String, dynamic>(),
    if (payload['result'] is Map &&
        ((payload['result'] as Map)['understandingResult'] is Map))
      (((payload['result'] as Map)['understandingResult'] as Map)
          .cast<String, dynamic>()),
  ];
  for (final candidate in candidates) {
    final parsed = _tryParseUnderstandingResult(candidate);
    if (parsed != null && parsed.intents.isNotEmpty) {
      return parsed;
    }
  }
  return null;
}

TaskGraph? extractTaskGraphFromModelPayload(
  Map<String, dynamic> payload, {
  AssistantTurnOutput? parsedTurn,
}) {
  final turnTaskGraph = parsedTurn?.taskGraph;
  final candidates = <Map<String, dynamic>>[
    if (turnTaskGraph != null && turnTaskGraph.tasks.isNotEmpty)
      turnTaskGraph.toJson(),
    if (payload['taskGraph'] is Map)
      (payload['taskGraph'] as Map).cast<String, dynamic>(),
    if (payload['result'] is Map && ((payload['result'] as Map)['taskGraph'] is Map))
      (((payload['result'] as Map)['taskGraph'] as Map).cast<String, dynamic>()),
  ];
  for (final candidate in candidates) {
    final parsed = _tryParseTaskGraph(candidate);
    if (parsed != null && parsed.tasks.isNotEmpty) {
      return parsed;
    }
  }
  return null;
}

UnderstandingResult? _tryParseUnderstandingResult(Map<String, dynamic> candidate) {
  try {
    return UnderstandingResult.fromJson(candidate);
  } catch (_) {
    return null;
  }
}

TaskGraph? _tryParseTaskGraph(Map<String, dynamic> candidate) {
  try {
    return TaskGraph.fromJson(candidate);
  } catch (_) {
    return null;
  }
}

