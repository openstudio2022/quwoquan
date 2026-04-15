import 'package:quwoquan_app/assistant/contracts/intent_graph.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';

const int defaultRecentDialogueRoundsLimit = 5;
const int maxRecentDialogueRoundsLimit = 8;

int resolveRecentDialogueRoundsLimit(
  Map<String, dynamic> contextScopeHint, {
  int fallback = defaultRecentDialogueRoundsLimit,
}) {
  final candidates = <Object?>[
    contextScopeHint['recentDialogueRoundsLimit'],
    (contextScopeHint['hints'] as Map?)?.cast<String, dynamic>()['recentDialogueRoundsLimit'],
  ];
  for (final candidate in candidates) {
    final parsed = _positiveInt(candidate);
    if (parsed != null) {
      return parsed > maxRecentDialogueRoundsLimit
          ? maxRecentDialogueRoundsLimit
          : parsed;
    }
  }
  return fallback;
}

List<AssistantRunMessage> trimMessagesToRecentRounds(
  List<AssistantRunMessage> messages, {
  int limit = defaultRecentDialogueRoundsLimit,
}) {
  if (messages.isEmpty) {
    return const <AssistantRunMessage>[];
  }
  if (limit <= 0) {
    return <AssistantRunMessage>[messages.last];
  }
  final userIndices = <int>[];
  for (var index = 0; index < messages.length; index += 1) {
    if (messages[index].role.trim() == 'user') {
      userIndices.add(index);
    }
  }
  if (userIndices.length <= limit) {
    return messages;
  }
  final startIndex = userIndices[userIndices.length - limit];
  return messages.sublist(startIndex);
}

List<Map<String, dynamic>> coerceRecentDialogueRounds(Object? raw) {
  if (raw is! List) {
    return const <Map<String, dynamic>>[];
  }
  return raw
      .whereType<Map>()
      .map((item) => item.cast<String, dynamic>())
      .where((item) => item.isNotEmpty)
      .toList(growable: false);
}

List<Map<String, dynamic>> buildRecentDialogueRounds(
  List<Map<String, dynamic>> sessionHistory, {
  int limit = defaultRecentDialogueRoundsLimit,
}) {
  if (limit <= 0 || sessionHistory.isEmpty) {
    return const <Map<String, dynamic>>[];
  }
  final rounds = <Map<String, dynamic>>[];
  String pendingUserQuery = '';
  String pendingUserTurnId = '';
  for (final rawMessage in sessionHistory) {
    final message = Map<String, dynamic>.from(rawMessage);
    final role = _stringValue(message['role']);
    if (role == 'user') {
      pendingUserQuery = _stringValue(message['content']);
      pendingUserTurnId = _stringValue(message['id']);
      continue;
    }
    if (role != 'assistant' || pendingUserQuery.isEmpty) {
      continue;
    }
    final canonical =
        normalizeCanonicalPersistedAssistantTurnMessage(message) ?? message;
    rounds.add(
      _buildDialogueRound(
        assistantMessage: canonical,
        userQuery: pendingUserQuery,
        fallbackTurnId: pendingUserTurnId,
        fallbackIndex: rounds.length,
      ),
    );
    pendingUserQuery = '';
    pendingUserTurnId = '';
  }
  return rounds.reversed.take(limit).toList(growable: false);
}

List<String> recentUserQueriesFromRounds(List<Map<String, dynamic>> rounds) {
  return rounds
      .map((round) => _stringValue(round['userQuery']))
      .where((item) => item.isNotEmpty)
      .toList(growable: false);
}

String buildRecentDialogueRoundsTranscript(List<Map<String, dynamic>> rounds) {
  if (rounds.isEmpty) {
    return '';
  }
  final chronological = rounds.reversed.toList(growable: false);
  final chunks = <String>[];
  for (final round in chronological) {
    final userQuery = _stringValue(round['userQuery']);
    final understandingSnapshot =
        (round['understandingSnapshot'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final understandingSummary = _stringValue(
      understandingSnapshot['userFacingSummary'],
    );
    final answerSummary = _stringValue(round['assistantSummary']);
    final lines = <String>[
      if (userQuery.isNotEmpty) 'user: $userQuery',
      if (understandingSummary.isNotEmpty) 'understanding: $understandingSummary',
      if (answerSummary.isNotEmpty) 'assistant: $answerSummary',
    ];
    if (lines.isNotEmpty) {
      chunks.add(lines.join('\n'));
    }
  }
  return chunks.join('\n\n').trim();
}

Map<String, dynamic> _buildDialogueRound({
  required Map<String, dynamic> assistantMessage,
  required String userQuery,
  required String fallbackTurnId,
  required int fallbackIndex,
}) {
  final intentGraph = resolvePersistedAssistantIntentGraph(assistantMessage);
  final understandingSnapshot =
      resolvePersistedAssistantUnderstandingSnapshot(assistantMessage);
  final retrievalProcessing =
      resolvePersistedAssistantRetrievalProcessing(assistantMessage);
  final answerProcessing =
      resolvePersistedAssistantAnswerProcessing(assistantMessage);
  final historicalThinkingSnapshot =
      resolvePersistedAssistantHistoricalThinkingSnapshot(assistantMessage);
  final answerSummary = resolvePersistedAssistantDisplayPlainText(
    assistantMessage,
  );
  final journey = resolvePersistedAssistantJourney(assistantMessage);
  final displayState = resolvePersistedAssistantDisplayState(assistantMessage);
  final turnId = _firstNonEmpty(<String>[
    _stringValue(assistantMessage['id']),
    _stringValue(assistantMessage['runId']),
    fallbackTurnId,
    'round_$fallbackIndex',
  ]);
  final finalAnswerReady =
      displayState.process.finalAnswerReady || journey.readiness.finalAnswerReady;
  return <String, dynamic>{
    'turnId': turnId,
    'userQuery': userQuery,
    'assistantSummary': _truncateText(answerSummary, maxLength: 240),
    'finalAnswerReady': finalAnswerReady,
    if (journey.readiness.finalAnswerMode.wireName.isNotEmpty)
      'finalAnswerMode': journey.readiness.finalAnswerMode.wireName,
    'intentGraph': _compactIntentGraph(intentGraph),
    'understandingSnapshot': _compactUnderstandingSnapshot(understandingSnapshot),
    'retrievalProcessing': _compactRetrievalProcessing(retrievalProcessing),
    'answerProcessing': _compactAnswerProcessing(answerProcessing),
    'historicalThinkingSnapshot':
        _compactHistoricalThinkingSnapshot(historicalThinkingSnapshot),
  };
}

Map<String, dynamic> _compactIntentGraph(IntentGraph? intentGraph) {
  if (intentGraph == null) {
    return const <String, dynamic>{};
  }
  return <String, dynamic>{
    if (intentGraph.primarySkill.trim().isNotEmpty)
      'primarySkill': intentGraph.primarySkill.trim(),
    if (intentGraph.problemClassWireName.trim().isNotEmpty)
      'problemClass': intentGraph.problemClassWireName.trim(),
    if (intentGraph.answerShapeWireName.trim().isNotEmpty)
      'answerShape': intentGraph.answerShapeWireName.trim(),
    if (intentGraph.userGoal.trim().isNotEmpty)
      'userGoal': intentGraph.userGoal.trim(),
    if (intentGraph.entityAnchors.isNotEmpty)
      'entityAnchors': intentGraph.entityAnchors.take(4).toList(growable: false),
    if (intentGraph.queryNormalization.normalizedQuery.trim().isNotEmpty)
      'queryNormalization': <String, dynamic>{
        'normalizedQuery': intentGraph.queryNormalization.normalizedQuery.trim(),
      },
    if (intentGraph.queryTasks.isNotEmpty)
      'queryTasks': intentGraph.queryTasks
          .take(2)
          .map(
            (task) => <String, dynamic>{
              if (task.query.trim().isNotEmpty) 'query': task.query.trim(),
              if (task.effectiveLabel.trim().isNotEmpty)
                'label': task.effectiveLabel.trim(),
              if (task.dimensionLabel.trim().isNotEmpty)
                'dimensionLabel': task.dimensionLabel.trim(),
            },
          )
          .toList(growable: false),
    if (_hasStructuredMap(intentGraph.resolvedGeoScope.toJson()))
      'resolvedGeoScope': intentGraph.resolvedGeoScope.toJson(),
  };
}

Map<String, dynamic> _compactUnderstandingSnapshot(
  RunArtifactsUnderstandingSnapshot snapshot,
) {
  return <String, dynamic>{
    if (snapshot.userFacingSummary.trim().isNotEmpty)
      'userFacingSummary': snapshot.userFacingSummary.trim(),
    if (snapshot.resolutionItems.isNotEmpty)
      'resolutionItems': snapshot.resolutionItems
          .where(
            (item) =>
                item.detail.trim().isNotEmpty ||
                item.resolvedValue.trim().isNotEmpty ||
                item.title.trim().isNotEmpty,
          )
          .take(3)
          .map(
            (item) => <String, dynamic>{
              if (item.kind.trim().isNotEmpty) 'kind': item.kind.trim(),
              if (item.title.trim().isNotEmpty) 'title': item.title.trim(),
              if (item.detail.trim().isNotEmpty) 'detail': item.detail.trim(),
              if (item.resolvedValue.trim().isNotEmpty)
                'resolvedValue': item.resolvedValue.trim(),
              if (item.defaultApplied) 'defaultApplied': true,
            },
          )
          .toList(growable: false),
    if (snapshot.carryForwardFacts.isNotEmpty)
      'carryForwardFacts': snapshot.carryForwardFacts
          .take(3)
          .toList(growable: false),
    if (snapshot.discardedAssumptions.isNotEmpty)
      'discardedAssumptions': snapshot.discardedAssumptions
          .take(3)
          .toList(growable: false),
  };
}

Map<String, dynamic> _compactRetrievalProcessing(
  RetrievalProcessingSnapshot snapshot,
) {
  return <String, dynamic>{
    if (snapshot.processingSummary.trim().isNotEmpty)
      'processingSummary': snapshot.processingSummary.trim(),
    if (snapshot.selectedKeyPoints.isNotEmpty)
      'selectedKeyPoints': snapshot.selectedKeyPoints
          .take(3)
          .toList(growable: false),
    if (snapshot.acceptedDocumentCount > 0)
      'acceptedDocumentCount': snapshot.acceptedDocumentCount,
    if (snapshot.acceptedReferences.isNotEmpty)
      'acceptedReferences': snapshot.acceptedReferences
          .take(3)
          .map(
            (item) => <String, dynamic>{
              if (item.title.trim().isNotEmpty) 'title': item.title.trim(),
              if (item.source.trim().isNotEmpty) 'source': item.source.trim(),
              if (item.url.trim().isNotEmpty) 'url': item.url.trim(),
            },
          )
          .toList(growable: false),
  };
}

Map<String, dynamic> _compactAnswerProcessing(
  RunArtifactsAnswerProcessing snapshot,
) {
  return <String, dynamic>{
    if (snapshot.readinessSummary.trim().isNotEmpty)
      'readinessSummary': snapshot.readinessSummary.trim(),
    if (snapshot.keyFacts.isNotEmpty)
      'keyFacts': snapshot.keyFacts.take(3).toList(growable: false),
    if (snapshot.missingDimensions.isNotEmpty)
      'missingDimensions': snapshot.missingDimensions
          .take(3)
          .toList(growable: false),
    if (snapshot.retrieveMoreReason.trim().isNotEmpty)
      'retrieveMoreReason': snapshot.retrieveMoreReason.trim(),
  };
}

Map<String, dynamic> _compactHistoricalThinkingSnapshot(
  RunArtifactsHistoricalThinkingSnapshot snapshot,
) {
  return <String, dynamic>{
    if (snapshot.continuityMode.trim().isNotEmpty)
      'continuityMode': snapshot.continuityMode.trim(),
    if (snapshot.mismatchSignal.trim().isNotEmpty)
      'mismatchSignal': snapshot.mismatchSignal.trim(),
    if (snapshot.carryForwardFacts.isNotEmpty)
      'carryForwardFacts': snapshot.carryForwardFacts
          .take(3)
          .toList(growable: false),
    if (snapshot.needsRecheckFacts.isNotEmpty)
      'needsRecheckFacts': snapshot.needsRecheckFacts
          .take(3)
          .toList(growable: false),
    if (snapshot.discardedAssumptions.isNotEmpty)
      'discardedAssumptions': snapshot.discardedAssumptions
          .take(3)
          .toList(growable: false),
  };
}

int? _positiveInt(Object? raw) {
  if (raw is num && raw.toInt() > 0) {
    return raw.toInt();
  }
  final parsed = int.tryParse(raw?.toString() ?? '');
  if (parsed != null && parsed > 0) {
    return parsed;
  }
  return null;
}

String _stringValue(Object? raw) => raw?.toString().trim() ?? '';

String _firstNonEmpty(List<String> values) {
  for (final value in values) {
    if (value.trim().isNotEmpty) {
      return value.trim();
    }
  }
  return '';
}

String _truncateText(String raw, {required int maxLength}) {
  final text = raw.trim();
  if (text.isEmpty || text.length <= maxLength) {
    return text;
  }
  return '${text.substring(0, maxLength)}...';
}

bool _hasStructuredMap(Map<String, dynamic> value) {
  for (final item in value.values) {
    if (item is String && item.trim().isNotEmpty) return true;
    if (item is num && item != 0) return true;
    if (item is bool && item) return true;
    if (item is List && item.isNotEmpty) return true;
    if (item is Map && item.isNotEmpty) return true;
  }
  return false;
}
