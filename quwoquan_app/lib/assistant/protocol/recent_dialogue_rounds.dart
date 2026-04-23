import 'package:quwoquan_app/assistant/contracts/intent_graph.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';

const int defaultRecentDialogueRoundsLimit = 10;
const int maxRecentDialogueRoundsLimit = 10;
const int defaultOlderRecentDialogueRoundsLimit = 5;
const int maxOlderRecentDialogueRoundsLimit = 5;
const Duration recentDialogueRoundsFreshWindow = Duration(days: 1);

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

int resolveOlderRecentDialogueRoundsLimit(
  Map<String, dynamic> contextScopeHint, {
  int fallback = defaultOlderRecentDialogueRoundsLimit,
}) {
  final candidates = <Object?>[
    contextScopeHint['recentDialogueRoundsOlderLimit'],
    contextScopeHint['olderRecentDialogueRoundsLimit'],
    (contextScopeHint['hints'] as Map?)?.cast<String, dynamic>()['recentDialogueRoundsOlderLimit'],
    (contextScopeHint['hints'] as Map?)?.cast<String, dynamic>()['olderRecentDialogueRoundsLimit'],
  ];
  for (final candidate in candidates) {
    final parsed = _positiveInt(candidate);
    if (parsed != null) {
      return parsed > maxOlderRecentDialogueRoundsLimit
          ? maxOlderRecentDialogueRoundsLimit
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
  return _coerceRecentDialogueRoundRecords(raw)
      .map((item) => item.toJson())
      .toList(growable: false);
}

List<Map<String, dynamic>> buildRecentDialogueRounds(
  List<Map<String, dynamic>> sessionHistory, {
  int limit = defaultRecentDialogueRoundsLimit,
  int olderLimit = defaultOlderRecentDialogueRoundsLimit,
  DateTime? referenceTime,
}) {
  if ((limit <= 0 && olderLimit <= 0) || sessionHistory.isEmpty) {
    return const <Map<String, dynamic>>[];
  }
  final rounds = <_RecentDialogueRoundRecord>[];
  String pendingUserQuery = '';
  String pendingUserTurnId = '';
  DateTime? pendingUserTimestamp;
  for (final rawMessage in sessionHistory) {
    final message = _SessionHistoryMessageRecord.fromMap(rawMessage);
    if (message.role == 'user') {
      pendingUserQuery = message.content;
      pendingUserTurnId = message.turnId;
      pendingUserTimestamp = message.timestamp;
      continue;
    }
    if (message.role != 'assistant' || pendingUserQuery.isEmpty) {
      continue;
    }
    final canonical =
        normalizeCanonicalPersistedAssistantTurnMessage(message.raw) ??
        message.raw;
    rounds.add(
      _buildDialogueRound(
        assistantMessage: canonical,
        userQuery: pendingUserQuery,
        fallbackTurnId: pendingUserTurnId,
        fallbackTimestamp: pendingUserTimestamp,
        fallbackIndex: rounds.length,
      ),
    );
    pendingUserQuery = '';
    pendingUserTurnId = '';
    pendingUserTimestamp = null;
  }
  return _selectRecentDialogueRounds(
    rounds,
    recentLimit: limit,
    olderLimit: olderLimit,
    referenceTime: referenceTime,
  ).map((item) => item.toJson()).toList(growable: false);
}

List<String> recentUserQueriesFromRounds(List<Map<String, dynamic>> rounds) {
  return _coerceRecentDialogueRoundRecords(rounds)
      .map((round) => round.userQuery)
      .where((item) => item.isNotEmpty)
      .toList(growable: false);
}

String buildRecentDialogueRoundsTranscript(List<Map<String, dynamic>> rounds) {
  final records = _coerceRecentDialogueRoundRecords(rounds);
  if (records.isEmpty) {
    return '';
  }
  final chronological = records.reversed.toList(growable: false);
  final chunks = <String>[];
  for (final round in chronological) {
    final userQuery = round.userQuery.trim();
    final understandingSummary =
        round.understandingSnapshot.userFacingSummary.trim();
    final answerSummary = round.assistantSummary.trim();
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

_RecentDialogueRoundRecord _buildDialogueRound({
  required Map<String, dynamic> assistantMessage,
  required String userQuery,
  required String fallbackTurnId,
  required DateTime? fallbackTimestamp,
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
  final answerSummary = _resolveDialogueRoundAssistantSummary(assistantMessage);
  final journey = resolvePersistedAssistantJourney(assistantMessage);
  final displayState = resolvePersistedAssistantDisplayState(assistantMessage);
  final turnId = _firstNonEmpty(<String>[
    _stringValue(assistantMessage['id']),
    _stringValue(assistantMessage['runId']),
    fallbackTurnId,
    'round_$fallbackIndex',
  ]);
  final roundTimestamp =
      _resolveMessageTime(assistantMessage) ?? fallbackTimestamp;
  final finalAnswerReady =
      displayState.process.finalAnswerReady || journey.readiness.finalAnswerReady;
  return _RecentDialogueRoundRecord(
    turnId: turnId,
    userQuery: userQuery,
    timestamp: roundTimestamp,
    assistantSummary: _truncateText(answerSummary, maxLength: 240),
    finalAnswerReady: finalAnswerReady,
    finalAnswerMode: journey.readiness.finalAnswerMode.wireName,
    intentGraph: intentGraph,
    understandingSnapshot: understandingSnapshot,
    retrievalProcessing: retrievalProcessing,
    answerProcessing: answerProcessing,
    historicalThinkingSnapshot: historicalThinkingSnapshot,
  );
}

String _resolveDialogueRoundAssistantSummary(Map<String, dynamic> message) {
  final displayState = resolvePersistedAssistantDisplayState(message);
  final answerSummary = displayState.answer.summary.trim();
  if (answerSummary.isNotEmpty) {
    return answerSummary;
  }
  final resultSummary =
      (((message['result'] as Map?)?['summary']) as String?)?.trim() ?? '';
  if (resultSummary.isNotEmpty) {
    return resultSummary;
  }
  return resolvePersistedAssistantDisplayPlainText(message);
}

List<_RecentDialogueRoundRecord> _selectRecentDialogueRounds(
  List<_RecentDialogueRoundRecord> rounds, {
  required int recentLimit,
  required int olderLimit,
  DateTime? referenceTime,
}) {
  if (rounds.isEmpty) {
    return const <_RecentDialogueRoundRecord>[];
  }
  final fresh = <_RecentDialogueRoundRecord>[];
  final older = <_RecentDialogueRoundRecord>[];
  final effectiveReferenceTime = (referenceTime ?? DateTime.now()).toUtc();
  for (final round in rounds.reversed) {
    if (_isWithinFreshWindow(round, referenceTime: effectiveReferenceTime)) {
      fresh.add(round);
    } else {
      older.add(round);
    }
  }
  return <_RecentDialogueRoundRecord>[
    if (recentLimit > 0) ...fresh.take(recentLimit),
    if (olderLimit > 0) ...older.take(olderLimit),
  ];
}

bool _isWithinFreshWindow(
  _RecentDialogueRoundRecord round, {
  required DateTime referenceTime,
}) {
  final roundTime = round.timestamp;
  if (roundTime == null) {
    return true;
  }
  return !roundTime.isBefore(referenceTime.subtract(recentDialogueRoundsFreshWindow));
}

DateTime? _resolveMessageTime(Map<String, dynamic> message) {
  final direct = _firstNonNull<DateTime>(<DateTime?>[
    _dateTimeValue(message['timestamp']),
    _dateTimeValue(message['createdAt']),
    _dateTimeValue(message['updatedAt']),
  ]);
  if (direct != null) {
    return direct;
  }
  final runArtifacts = (message['runArtifacts'] as Map?)?.cast<String, dynamic>();
  if (runArtifacts != null && runArtifacts.isNotEmpty) {
    return _firstNonNull<DateTime>(<DateTime?>[
      _dateTimeValue(runArtifacts['timestamp']),
      _dateTimeValue(runArtifacts['createdAt']),
      _dateTimeValue(runArtifacts['updatedAt']),
    ]);
  }
  return null;
}

DateTime? _dateTimeValue(Object? raw) {
  if (raw is DateTime) {
    return raw.toUtc();
  }
  final text = _stringValue(raw);
  if (text.isEmpty) {
    return null;
  }
  return DateTime.tryParse(text)?.toUtc();
}

List<_RecentDialogueRoundRecord> _coerceRecentDialogueRoundRecords(Object? raw) {
  if (raw is! List) {
    return const <_RecentDialogueRoundRecord>[];
  }
  final records = <_RecentDialogueRoundRecord>[];
  for (final item in raw.whereType<Map>()) {
    final parsed = _RecentDialogueRoundRecord.tryFromMap(
      item.cast<String, dynamic>(),
    );
    if (parsed != null) {
      records.add(parsed);
    }
  }
  return records;
}

class _SessionHistoryMessageRecord {
  const _SessionHistoryMessageRecord({
    required this.raw,
    required this.role,
    required this.content,
    required this.turnId,
    required this.timestamp,
  });

  factory _SessionHistoryMessageRecord.fromMap(Map<String, dynamic> raw) {
    final message = Map<String, dynamic>.from(raw);
    return _SessionHistoryMessageRecord(
      raw: message,
      role: _stringValue(message['role']),
      content: _stringValue(message['content']),
      turnId: _stringValue(message['id']),
      timestamp: _resolveMessageTime(message),
    );
  }

  final Map<String, dynamic> raw;
  final String role;
  final String content;
  final String turnId;
  final DateTime? timestamp;
}

class _RecentDialogueRoundRecord {
  const _RecentDialogueRoundRecord({
    required this.turnId,
    required this.userQuery,
    required this.timestamp,
    required this.assistantSummary,
    required this.finalAnswerReady,
    required this.finalAnswerMode,
    required this.intentGraph,
    required this.understandingSnapshot,
    required this.retrievalProcessing,
    required this.answerProcessing,
    required this.historicalThinkingSnapshot,
  });

  final String turnId;
  final String userQuery;
  final DateTime? timestamp;
  final String assistantSummary;
  final bool finalAnswerReady;
  final String finalAnswerMode;
  final IntentGraph? intentGraph;
  final RunArtifactsUnderstandingSnapshot understandingSnapshot;
  final RetrievalProcessingSnapshot retrievalProcessing;
  final RunArtifactsAnswerProcessing answerProcessing;
  final RunArtifactsHistoricalThinkingSnapshot historicalThinkingSnapshot;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'turnId': turnId,
      'userQuery': userQuery,
      if (timestamp != null) 'timestamp': timestamp!.toIso8601String(),
      'assistantSummary': assistantSummary,
      'finalAnswerReady': finalAnswerReady,
      if (finalAnswerMode.isNotEmpty) 'finalAnswerMode': finalAnswerMode,
      'intentGraph': _compactIntentGraph(intentGraph),
      'understandingSnapshot': _compactUnderstandingSnapshot(
        understandingSnapshot,
      ),
      'retrievalProcessing': _compactRetrievalProcessing(retrievalProcessing),
      'answerProcessing': _compactAnswerProcessing(answerProcessing),
      'historicalThinkingSnapshot': _compactHistoricalThinkingSnapshot(
        historicalThinkingSnapshot,
      ),
    };
  }

  static _RecentDialogueRoundRecord? tryFromMap(Map<String, dynamic> raw) {
    final turnId = _stringValue(raw['turnId']);
    final userQuery = _stringValue(raw['userQuery']);
    final assistantSummary = _stringValue(raw['assistantSummary']);
    if (turnId.isEmpty && userQuery.isEmpty && assistantSummary.isEmpty) {
      return null;
    }
    return _RecentDialogueRoundRecord(
      turnId: turnId,
      userQuery: userQuery,
      timestamp: _dateTimeValue(raw['timestamp']),
      assistantSummary: assistantSummary,
      finalAnswerReady: raw['finalAnswerReady'] == true,
      finalAnswerMode: _stringValue(raw['finalAnswerMode']),
      intentGraph: _intentGraphFromMap(raw['intentGraph']),
      understandingSnapshot: _understandingSnapshotFromMap(
        raw['understandingSnapshot'],
      ),
      retrievalProcessing: _retrievalProcessingFromMap(
        raw['retrievalProcessing'],
      ),
      answerProcessing: _answerProcessingFromMap(raw['answerProcessing']),
      historicalThinkingSnapshot: _historicalThinkingSnapshotFromMap(
        raw['historicalThinkingSnapshot'],
      ),
    );
  }
}

T? _firstNonNull<T>(Iterable<T?> values) {
  for (final value in values) {
    if (value != null) {
      return value;
    }
  }
  return null;
}

IntentGraph? _intentGraphFromMap(Object? raw) {
  if (raw is! Map) {
    return null;
  }
  try {
    final parsed = IntentGraph.fromJson(raw.cast<String, dynamic>());
    return parsed.primarySkill.trim().isEmpty &&
            parsed.userGoal.trim().isEmpty &&
            parsed.queryTasks.isEmpty
        ? null
        : parsed;
  } catch (_) {
    return null;
  }
}

RunArtifactsUnderstandingSnapshot _understandingSnapshotFromMap(Object? raw) {
  if (raw is! Map) {
    return const RunArtifactsUnderstandingSnapshot();
  }
  try {
    return RunArtifactsUnderstandingSnapshot.fromJson(raw.cast<String, dynamic>());
  } catch (_) {
    return const RunArtifactsUnderstandingSnapshot();
  }
}

RetrievalProcessingSnapshot _retrievalProcessingFromMap(Object? raw) {
  if (raw is! Map) {
    return const RetrievalProcessingSnapshot();
  }
  try {
    return RetrievalProcessingSnapshot.fromJson(raw.cast<String, dynamic>());
  } catch (_) {
    return const RetrievalProcessingSnapshot();
  }
}

RunArtifactsAnswerProcessing _answerProcessingFromMap(Object? raw) {
  if (raw is! Map) {
    return const RunArtifactsAnswerProcessing();
  }
  try {
    return RunArtifactsAnswerProcessing.fromJson(raw.cast<String, dynamic>());
  } catch (_) {
    return const RunArtifactsAnswerProcessing();
  }
}

RunArtifactsHistoricalThinkingSnapshot _historicalThinkingSnapshotFromMap(
  Object? raw,
) {
  if (raw is! Map) {
    return const RunArtifactsHistoricalThinkingSnapshot();
  }
  try {
    return RunArtifactsHistoricalThinkingSnapshot.fromJson(
      raw.cast<String, dynamic>(),
    );
  } catch (_) {
    return const RunArtifactsHistoricalThinkingSnapshot();
  }
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
    if (snapshot.retrievalDesignNarrative.trim().isNotEmpty)
      'retrievalDesignNarrative': snapshot.retrievalDesignNarrative.trim(),
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
