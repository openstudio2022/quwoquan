import 'package:quwoquan_app/assistant/contracts/planner_contracts.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/ui_process_timeline_entry.dart';
import 'package:quwoquan_app/assistant/contracts/user_events.dart';
import 'package:quwoquan_app/assistant/orchestration/trace_user_event_translator.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';

class ProcessJournalBus {
  ProcessJournalBus({this.userGoalSummary = '', this.problemClass = ''});

  final String userGoalSummary;
  final String problemClass;

  final List<ProcessJournalEvent> _events = <ProcessJournalEvent>[];
  int _eventCounter = 0;
  String _currentStage = '';
  ProcessJournalEvent? _liveCursor;

  List<ProcessJournalEvent> get snapshot =>
      List<ProcessJournalEvent>.unmodifiable(_events);

  List<ProcessJournalEvent> get displaySnapshot =>
      List<ProcessJournalEvent>.unmodifiable(
        ProcessJournalBus.toDisplaySnapshot(_events),
      );

  ProcessJournalEvent? get liveCursor => _liveCursor;

  void consumeTraces(Iterable<AssistantTraceEvent> traces) {
    for (final trace in traces) {
      consumeTrace(trace);
    }
  }

  List<ProcessJournalEvent> consumeTrace(AssistantTraceEvent event) {
    final emitted = <ProcessJournalEvent>[];
    if (!event.visibility.isUserVisible) return emitted;

    if (event.type == AssistantTraceEventType.answerDelta ||
        event.type == AssistantTraceEventType.streamDelta) {
      final delta =
          (event.data?['delta'] as String?)?.trim() ?? event.message.trim();
      if (delta.isNotEmpty) {
        emitted.addAll(
          _setStage(
            stage: PlannerPhaseId.answering.wireName,
            timestamp: event.timestamp,
            runId: event.runId ?? '',
            traceId: event.traceId ?? '',
          ),
        );
        emitted.add(
          _appendEvent(
            ProcessJournalEvent(
              eventId: 'answer_delta_${_eventCounter++}',
              type: ProcessJournalEventType.answerDelta,
              stage: PlannerPhaseId.answering.wireName,
              phaseId: PlannerPhaseId.answering.wireName,
              actionCode: PlannerActionCode.streamAnswer.wireName,
              reasonCode: PlannerReasonCode.deliverIncrement.wireName,
              reasonShort: delta,
              source: 'trace_stream',
              nodeId: 'answer.stream',
              message: delta,
              runId: event.runId ?? '',
              traceId: event.traceId ?? '',
              timestamp: event.timestamp,
            ),
          ),
        );
      }
      return emitted;
    }

    final userEvent = TraceUserEventTranslator.translate(
      AssistantTraceEvent.fromJson(event.toJson()),
    );
    if (userEvent != null) {
      emitted.addAll(
        consumeUserEvent(
          userEvent,
          timestamp: event.timestamp,
          traceId: event.traceId ?? '',
        ),
      );
    }

    if (event.type == AssistantTraceEventType.lifecycleEnd &&
        (event.data?['lifecycleOutcome'] as String?) == 'completed') {
      emitted.addAll(
        _flushLiveCursor(
          timestamp: event.timestamp,
          runId: event.runId ?? '',
          traceId: event.traceId ?? '',
        ),
      );
      emitted.addAll(
        _setStage(
          stage: PlannerPhaseId.completed.wireName,
          timestamp: event.timestamp,
          runId: event.runId ?? '',
          traceId: event.traceId ?? '',
        ),
      );
      emitted.add(
        _appendEvent(
          ProcessJournalEvent(
            eventId: 'completed_${_eventCounter++}',
            type: ProcessJournalEventType.completed,
            stage: PlannerPhaseId.completed.wireName,
            phaseId: PlannerPhaseId.completed.wireName,
            actionCode: PlannerActionCode.completeTurn.wireName,
            reasonCode: PlannerReasonCode.readyToAnswer.wireName,
            source: 'trace_stream',
            nodeId: 'run.completed',
            message: '',
            runId: event.runId ?? '',
            traceId: event.traceId ?? '',
            timestamp: event.timestamp,
          ),
        ),
      );
    }

    return emitted;
  }

  List<ProcessJournalEvent> consumeUserEvent(
    UserEvent event, {
    DateTime? timestamp,
    String traceId = '',
  }) {
    final emitted = <ProcessJournalEvent>[];
    final stage = _stageFromUserEvent(event);
    final phaseId = _payloadString(event.payload, 'phaseId', fallback: stage);
    final actionCode = _payloadString(event.payload, 'actionCode');
    final reasonCode = _payloadString(event.payload, 'reasonCode');
    final reasonShort = _payloadString(
      event.payload,
      'reasonShort',
      fallback: event.message.trim(),
    );
    final source = _payloadString(
      event.payload,
      'source',
      fallback: 'user_event',
    );
    emitted.addAll(
      _setStage(
        stage: stage,
        timestamp: timestamp,
        runId: event.runId,
        traceId: traceId,
      ),
    );

    final references = _referencesFromPayload(event.payload);
    switch (event.type) {
      case UserEventType.processReplace:
        final message = event.message.trim();
        if (message.isEmpty) return emitted;
        final liveEvent = _appendEvent(
          ProcessJournalEvent(
            eventId: 'live_cursor_${_eventCounter++}::$stage',
            type: ProcessJournalEventType.liveCursor,
            stage: stage,
            phaseId: phaseId,
            actionCode: actionCode,
            reasonCode: reasonCode,
            reasonShort: reasonShort,
            source: source,
            nodeId: event.nodeId,
            message: message,
            runId: event.runId,
            traceId: traceId,
            payload: <String, dynamic>{
              ...event.payload,
              'cursorKey': '$stage::${event.nodeId}',
              'streaming': true,
            },
            timestamp: timestamp,
          ),
        );
        emitted.add(liveEvent);
        _liveCursor = liveEvent;
        return emitted;
      case UserEventType.processAppend:
        emitted.addAll(
          _flushLiveCursor(
            preferredMessage: reasonShort,
            nodeId: event.nodeId,
            stage: stage,
            timestamp: timestamp,
            runId: event.runId,
            traceId: traceId,
          ),
        );
        if (references.isNotEmpty) {
          emitted.add(
            _upsertSourceUpdate(
              stage: stage,
              phaseId: phaseId,
              actionCode: actionCode,
              reasonCode: reasonCode,
              reasonShort: reasonShort,
              source: source,
              nodeId: event.nodeId,
              message: reasonShort,
              references: references,
              runId: event.runId,
              traceId: traceId,
              payload: event.payload,
              timestamp: timestamp,
            ),
          );
        } else {
          final committed = _appendNarrativeCommit(
            stage: stage,
            phaseId: phaseId,
            actionCode: actionCode,
            reasonCode: reasonCode,
            reasonShort: reasonShort,
            source: source,
            nodeId: event.nodeId,
            message: reasonShort,
            runId: event.runId,
            traceId: traceId,
            payload: event.payload,
            timestamp: timestamp,
          );
          if (committed != null) emitted.add(committed);
        }
        return emitted;
      case UserEventType.processCommit:
        emitted.addAll(
          _flushLiveCursor(
            preferredMessage: references.isEmpty ? reasonShort : null,
            nodeId: event.nodeId,
            stage: stage,
            timestamp: timestamp,
            runId: event.runId,
            traceId: traceId,
          ),
        );
        if (references.isNotEmpty) {
          emitted.add(
            _upsertSourceUpdate(
              stage: stage,
              phaseId: phaseId,
              actionCode: actionCode,
              reasonCode: reasonCode,
              reasonShort: reasonShort,
              source: source,
              nodeId: event.nodeId,
              message: reasonShort,
              references: references,
              runId: event.runId,
              traceId: traceId,
              payload: event.payload,
              timestamp: timestamp,
            ),
          );
          if (parsePlannerPhaseId(stage) != PlannerPhaseId.searching) {
            final committed = _appendNarrativeCommit(
              stage: stage,
              phaseId: phaseId,
              actionCode: actionCode,
              reasonCode: reasonCode,
              reasonShort: reasonShort,
              source: source,
              nodeId: event.nodeId,
              message: reasonShort,
              runId: event.runId,
              traceId: traceId,
              payload: event.payload,
              timestamp: timestamp,
            );
            if (committed != null) emitted.add(committed);
          }
        } else {
          final committed = _appendNarrativeCommit(
            stage: stage,
            phaseId: phaseId,
            actionCode: actionCode,
            reasonCode: reasonCode,
            reasonShort: reasonShort,
            source: source,
            nodeId: event.nodeId,
            message: reasonShort,
            runId: event.runId,
            traceId: traceId,
            payload: event.payload,
            timestamp: timestamp,
          );
          if (committed != null) emitted.add(committed);
        }
        return emitted;
      case UserEventType.answerDelta:
        final message = event.message.trim();
        if (message.isEmpty) return emitted;
        emitted.add(
          _appendEvent(
            ProcessJournalEvent(
              eventId: 'answer_delta_${_eventCounter++}',
              type: ProcessJournalEventType.answerDelta,
              stage: PlannerPhaseId.answering.wireName,
              phaseId: phaseId,
              actionCode: actionCode,
              reasonCode: reasonCode,
              reasonShort: message,
              source: source,
              nodeId: 'answer.stream',
              message: message,
              runId: event.runId,
              traceId: traceId,
              payload: event.payload,
              timestamp: timestamp,
            ),
          ),
        );
        return emitted;
      case UserEventType.unknown:
        return emitted;
    }
  }

  static List<UiProcessTimelineEntry> toTimelineEntries(
    List<ProcessJournalEvent> events,
  ) {
    final displayEvents = toDisplaySnapshot(events);
    final entries = <UiProcessTimelineEntry>[];
    for (final event in displayEvents) {
      switch (event.type) {
        case ProcessJournalEventType.stageSet:
          continue;
        case ProcessJournalEventType.narrativeCommit:
          entries.add(
            UiProcessTimelineEntry(
              scope: _scopeForStage(event.stage).name,
              type: UserEventType.processCommit.name,
              nodeId: event.nodeId,
              runId: event.runId,
              eventId: event.eventId,
              summary: event.displayMessage,
              payload: _timelinePayload(event),
            ),
          );
          break;
        case ProcessJournalEventType.liveCursor:
          entries.add(
            UiProcessTimelineEntry(
              scope: _scopeForStage(event.stage).name,
              type: UserEventType.processReplace.name,
              nodeId: event.nodeId,
              runId: event.runId,
              eventId: event.eventId,
              summary: event.displayMessage,
              payload: <String, dynamic>{
                ..._timelinePayload(event),
                'streaming': true,
              },
            ),
          );
          break;
        case ProcessJournalEventType.sourceUpdate:
          entries.add(
            UiProcessTimelineEntry(
              scope:
                  parsePlannerPhaseId(event.stage) == PlannerPhaseId.searching
                  ? UserEventScope.skill.name
                  : UserEventScope.aggregation.name,
              type: UserEventType.processCommit.name,
              nodeId: event.nodeId,
              runId: event.runId,
              eventId: event.eventId,
              summary: event.displayMessage,
              payload: _timelinePayload(event),
              references: event.references
                  .map((item) => item.toJson())
                  .toList(growable: false),
            ),
          );
          break;
        case ProcessJournalEventType.answerDelta:
        case ProcessJournalEventType.completed:
          continue;
      }
    }
    return entries;
  }

  List<ProcessSourceReference> _referencesFromPayload(
    Map<String, dynamic> payload,
  ) {
    return (payload['references'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .map(ProcessSourceReference.fromJson)
            .where((item) => item.title.isNotEmpty && item.url.isNotEmpty)
            .toList(growable: false) ??
        const <ProcessSourceReference>[];
  }

  List<ProcessJournalEvent> _setStage({
    required String stage,
    DateTime? timestamp,
    String runId = '',
    String traceId = '',
  }) {
    if (stage.isEmpty || stage == _currentStage) {
      return const <ProcessJournalEvent>[];
    }
    final emitted = <ProcessJournalEvent>[];
    emitted.addAll(
      _flushLiveCursor(timestamp: timestamp, runId: runId, traceId: traceId),
    );
    _currentStage = stage;
    emitted.add(
      _appendEvent(
        ProcessJournalEvent(
          eventId: 'stage_set_${_eventCounter++}::$stage',
          type: ProcessJournalEventType.stageSet,
          stage: stage,
          phaseId: stage,
          actionCode: PlannerActionCode.setStage.wireName,
          reasonCode: PlannerReasonCode.alignGoal.wireName,
          source: 'journal_bus',
          nodeId: 'stage.$stage',
          message: '',
          runId: runId,
          traceId: traceId,
          timestamp: timestamp,
        ),
      ),
    );
    return emitted;
  }

  List<ProcessJournalEvent> _flushLiveCursor({
    String? preferredMessage,
    String? nodeId,
    String? stage,
    DateTime? timestamp,
    String runId = '',
    String traceId = '',
  }) {
    final current = _liveCursor;
    if (current == null) return const <ProcessJournalEvent>[];
    _liveCursor = null;
    final message = _preferredLiveMessage(
      preferredMessage,
      current.displayMessage,
    );
    if (message.isEmpty) return const <ProcessJournalEvent>[];
    final committed = _appendNarrativeCommit(
      stage: stage ?? current.stage,
      phaseId: current.phaseId.isNotEmpty ? current.phaseId : current.stage,
      actionCode: current.actionCode,
      reasonCode: current.reasonCode,
      reasonShort: message,
      source: current.source,
      nodeId: nodeId ?? current.nodeId,
      message: message,
      runId: runId.isNotEmpty ? runId : current.runId,
      traceId: traceId.isNotEmpty ? traceId : current.traceId,
      payload: <String, dynamic>{...current.payload, 'fromLiveCursor': true},
      timestamp: timestamp ?? current.timestamp,
    );
    return committed == null
        ? const <ProcessJournalEvent>[]
        : <ProcessJournalEvent>[committed];
  }

  String _preferredLiveMessage(String? preferred, String current) {
    final incoming = preferred?.trim() ?? '';
    final existing = current.trim();
    if (incoming.isEmpty) return existing;
    if (existing.isEmpty) return incoming;
    return incoming.length >= existing.length ? incoming : existing;
  }

  ProcessJournalEvent? _appendNarrativeCommit({
    required String stage,
    required String phaseId,
    required String actionCode,
    required String reasonCode,
    required String reasonShort,
    required String source,
    required String nodeId,
    required String message,
    required String runId,
    required String traceId,
    required Map<String, dynamic> payload,
    DateTime? timestamp,
  }) {
    final normalized = message.trim();
    if (normalized.isEmpty) return null;
    if (_isDuplicateNarrative(
      phaseId: phaseId,
      actionCode: actionCode,
      reasonCode: reasonCode,
      nodeId: nodeId,
      message: normalized,
    )) {
      return null;
    }
    return _appendEvent(
      ProcessJournalEvent(
        eventId: 'narrative_${_eventCounter++}',
        type: ProcessJournalEventType.narrativeCommit,
        stage: stage,
        phaseId: phaseId,
        actionCode: actionCode,
        reasonCode: reasonCode,
        reasonShort: reasonShort,
        source: source,
        nodeId: nodeId,
        message: normalized,
        runId: runId,
        traceId: traceId,
        payload: payload,
        timestamp: timestamp,
      ),
    );
  }

  bool _isDuplicateNarrative({
    required String phaseId,
    required String actionCode,
    required String reasonCode,
    required String nodeId,
    required String message,
  }) {
    final expectedKey = _displaySemanticKey(
      phaseId: phaseId,
      actionCode: actionCode,
      reasonCode: reasonCode,
      nodeId: nodeId,
    );
    for (var i = _events.length - 1; i >= 0; i--) {
      final event = _events[i];
      if (event.type != ProcessJournalEventType.narrativeCommit &&
          event.type != ProcessJournalEventType.sourceUpdate) {
        continue;
      }
      if (_displaySemanticKeyFromEvent(event) != expectedKey) continue;
      if (_canonicalNarrative(event.displayMessage) ==
          _canonicalNarrative(message)) {
        return true;
      }
    }
    return false;
  }

  ProcessJournalEvent _upsertSourceUpdate({
    required String stage,
    required String phaseId,
    required String actionCode,
    required String reasonCode,
    required String reasonShort,
    required String source,
    required String nodeId,
    required String message,
    required List<ProcessSourceReference> references,
    required String runId,
    required String traceId,
    required Map<String, dynamic> payload,
    DateTime? timestamp,
  }) {
    final deduped = <ProcessSourceReference>[];
    final seenUrls = <String>{};
    for (final ref in references) {
      if (ref.title.isEmpty || ref.url.isEmpty || !seenUrls.add(ref.url)) {
        continue;
      }
      deduped.add(ref);
    }
    return _appendEvent(
      ProcessJournalEvent(
        eventId: 'source_update_${_eventCounter++}::$nodeId',
        type: ProcessJournalEventType.sourceUpdate,
        stage: stage,
        phaseId: phaseId,
        actionCode: actionCode,
        reasonCode: reasonCode,
        reasonShort: reasonShort,
        source: source,
        nodeId: nodeId,
        message: message.trim(),
        runId: runId,
        traceId: traceId,
        references: deduped,
        payload: payload,
        timestamp: timestamp,
      ),
    );
  }

  ProcessJournalEvent _appendEvent(ProcessJournalEvent event) {
    _events.add(event);
    return event;
  }

  static List<ProcessJournalEvent> toDisplaySnapshot(
    List<ProcessJournalEvent> events,
  ) {
    final projected = <ProcessJournalEvent>[];
    final indexBySemanticKey = <String, int>{};
    ProcessJournalEvent? currentLiveCursor;
    for (final event in events) {
      switch (event.type) {
        case ProcessJournalEventType.liveCursor:
          currentLiveCursor = event;
          break;
        case ProcessJournalEventType.stageSet:
        case ProcessJournalEventType.narrativeCommit:
        case ProcessJournalEventType.sourceUpdate:
          currentLiveCursor = null;
          final semanticKey = _projectionSemanticKey(event);
          final existingIndex = indexBySemanticKey[semanticKey];
          if (existingIndex == null) {
            indexBySemanticKey[semanticKey] = projected.length;
            projected.add(event);
          } else {
            projected[existingIndex] = _preferDisplayEvent(
              projected[existingIndex],
              event,
            );
          }
          break;
        case ProcessJournalEventType.answerDelta:
        case ProcessJournalEventType.completed:
          currentLiveCursor = null;
          projected.add(event);
          break;
      }
    }
    if (currentLiveCursor != null) {
      final semanticKey = _projectionSemanticKey(currentLiveCursor);
      final existingIndex = indexBySemanticKey[semanticKey];
      if (existingIndex == null) {
        projected.add(currentLiveCursor);
      } else {
        projected[existingIndex] = _preferDisplayEvent(
          projected[existingIndex],
          currentLiveCursor,
        );
      }
    }
    return projected;
  }

  static String _semanticKey({
    required ProcessJournalEventType type,
    required String phaseId,
    required String actionCode,
    required String reasonCode,
    required String nodeId,
  }) {
    return <String>[
      processJournalEventTypeToWire(type),
      phaseId,
      actionCode,
      reasonCode,
      nodeId,
    ].join('::');
  }

  static String _semanticKeyFromEvent(ProcessJournalEvent event) {
    return _semanticKey(
      type: event.type,
      phaseId: event.phaseId.isNotEmpty ? event.phaseId : event.stage,
      actionCode: event.actionCode,
      reasonCode: event.reasonCode,
      nodeId: event.nodeId,
    );
  }

  static String _displaySemanticKey({
    required String phaseId,
    required String actionCode,
    required String reasonCode,
    required String nodeId,
  }) {
    return <String>[phaseId, actionCode, reasonCode, nodeId].join('::');
  }

  static String _displaySemanticKeyFromEvent(ProcessJournalEvent event) {
    return _displaySemanticKey(
      phaseId: event.phaseId.isNotEmpty ? event.phaseId : event.stage,
      actionCode: event.actionCode,
      reasonCode: event.reasonCode,
      nodeId: event.nodeId,
    );
  }

  static String _projectionSemanticKey(ProcessJournalEvent event) {
    switch (event.type) {
      case ProcessJournalEventType.narrativeCommit:
      case ProcessJournalEventType.liveCursor:
      case ProcessJournalEventType.sourceUpdate:
        return _displaySemanticKeyFromEvent(event);
      case ProcessJournalEventType.stageSet:
      case ProcessJournalEventType.answerDelta:
      case ProcessJournalEventType.completed:
        return _semanticKeyFromEvent(event);
    }
  }

  static String _canonicalNarrative(String text) {
    return text
        .replaceAll(RegExp(r'\s+'), ' ')
        .replaceAll(RegExp(r'[。！，、,.!]+$'), '')
        .trim();
  }

  static ProcessJournalEvent _preferDisplayEvent(
    ProcessJournalEvent existing,
    ProcessJournalEvent incoming,
  ) {
    final mergedReferences = _mergeReferences(
      existing.references,
      incoming.references,
    );
    final preferredDisplayMessage = _preferDisplayMessage(
      existing.displayMessage,
      incoming.displayMessage,
    );
    final preferredEvent =
        incoming.references.length > existing.references.length
        ? incoming
        : incoming.displayMessage.length >= existing.displayMessage.length
        ? incoming
        : existing;
    return preferredEvent.copyWith(
      reasonShort: preferredDisplayMessage,
      message: preferredDisplayMessage,
      references: mergedReferences,
    );
  }

  static List<ProcessSourceReference> _mergeReferences(
    List<ProcessSourceReference> primary,
    List<ProcessSourceReference> secondary,
  ) {
    if (primary.isEmpty) return secondary;
    if (secondary.isEmpty) return primary;
    final merged = <ProcessSourceReference>[];
    final seenUrls = <String>{};
    for (final ref in <ProcessSourceReference>[...primary, ...secondary]) {
      if (ref.title.isEmpty || ref.url.isEmpty || !seenUrls.add(ref.url)) {
        continue;
      }
      merged.add(ref);
    }
    return merged;
  }

  static String _preferDisplayMessage(String existing, String incoming) {
    final existingNormalized = existing.trim();
    final incomingNormalized = incoming.trim();
    if (incomingNormalized.isEmpty) return existingNormalized;
    if (existingNormalized.isEmpty) return incomingNormalized;
    return incomingNormalized.length >= existingNormalized.length
        ? incomingNormalized
        : existingNormalized;
  }

  static UserEventScope _scopeForStage(String stage) {
    final phaseType = parsePlannerPhaseId(stage);
    switch (phaseType) {
      case PlannerPhaseId.searching:
        return UserEventScope.skill;
      case PlannerPhaseId.analyzing:
      case PlannerPhaseId.answering:
      case PlannerPhaseId.completed:
        return UserEventScope.aggregation;
      case PlannerPhaseId.understanding:
        return UserEventScope.root;
      default:
        return UserEventScope.root;
    }
  }

  String _stageFromUserEvent(UserEvent event) {
    final raw = (event.payload['stage'] as String?)?.trim().toLowerCase() ?? '';
    if (raw.isNotEmpty) return raw;
    switch (event.scope) {
      case UserEventScope.root:
        return PlannerPhaseId.understanding.wireName;
      case UserEventScope.skill:
        return PlannerPhaseId.searching.wireName;
      case UserEventScope.aggregation:
        return event.type == UserEventType.answerDelta
            ? PlannerPhaseId.answering.wireName
            : PlannerPhaseId.analyzing.wireName;
      case UserEventScope.unknown:
        return _currentStage.isEmpty
            ? PlannerPhaseId.understanding.wireName
            : _currentStage;
    }
  }

  static Map<String, dynamic> _timelinePayload(ProcessJournalEvent event) {
    return <String, dynamic>{
      'stage': event.stage,
      'phaseId': event.phaseId,
      'actionCode': event.actionCode,
      'reasonCode': event.reasonCode,
      'reasonShort': event.displayMessage,
      'source': event.source,
      ...event.payload,
    };
  }

  static String _payloadString(
    Map<String, dynamic> payload,
    String key, {
    String fallback = '',
  }) {
    final value = (payload[key] as String?)?.trim() ?? '';
    if (value.isNotEmpty) return value;
    return fallback;
  }
}
