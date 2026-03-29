import 'package:quwoquan_app/assistant/contracts/aggregation_state.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/conversation_state_decision.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/contracts/user_events.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_content_filters.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_text_resolver.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_metadata_registry.dart';

class AssistantJourneyProjector {
  AssistantJourneyProjector({
    required ToolMetadataRegistry toolMetadataRegistry,
  }) : _toolMetadataRegistry = toolMetadataRegistry {
    for (final stage in _baseStages()) {
      _stages[stage.stageId] = stage;
    }
  }

  final ToolMetadataRegistry _toolMetadataRegistry;
  final Map<JourneyStageId, AssistantJourneyStage> _stages =
      <JourneyStageId, AssistantJourneyStage>{};
  final List<AssistantJourneyEntry> _entries = <AssistantJourneyEntry>[];
  final Map<String, int> _entryIndexByKey = <String, int>{};

  int _orderSeed = 0;
  AssistantJourneyReadiness _readiness = const AssistantJourneyReadiness();

  AssistantJourney get snapshot {
    final stages = _orderedStages();
    return AssistantJourney(
      stages: stages,
      entries: List<AssistantJourneyEntry>.unmodifiable(_entries),
      summary: _summaryFor(stages),
      referenceSummary: _referenceSummary(),
      readiness: _readiness,
    );
  }

  AssistantJourney consumeTrace(AssistantTraceEvent event) {
    if (event.visibility == TraceVisibility.internal) {
      return AssistantJourney(
        stages: List<AssistantJourneyStage>.unmodifiable(_stages.values),
        entries: List<AssistantJourneyEntry>.unmodifiable(_entries),
        readiness: _readiness,
      );
    }
    final syntheticUserEvent = _syntheticUserEventFromTrace(event);
    if (syntheticUserEvent != null) {
      return consumeUserEvent(syntheticUserEvent);
    }
    final data = event.data ?? const <String, dynamic>{};
    final provenance = AssistantJourneyProvenance(
      phaseId: parsePlannerPhaseId(
        (data['phaseId'] as String?)?.trim() ??
            (data['phase'] as String?)?.trim() ??
            '',
      ),
      actionCode: parsePlannerActionCode(
        (data['actionCode'] as String?)?.trim() ?? '',
      ),
      reasonCode: parsePlannerReasonCode(
        (data['reasonCode'] as String?)?.trim() ?? '',
      ),
      toolName: _toolNameFromData(data),
      source: 'trace',
    );
    switch (event.type) {
      case AssistantTraceEventType.planStarted:
      case AssistantTraceEventType.thinkingStarted:
        _activateStage(JourneyStageId.analyze);
        break;
      case AssistantTraceEventType.thinkingProgress:
        final stageId = _stageFromPhaseHint(
          (data['phase'] as String?)?.trim() ?? '',
        );
        _activateStage(stageId);
        if (data['extracted'] == true) {
          break;
        }
        final message = _sanitizeThinkingStreamText(event.message);
        final isStreaming =
            data['streaming'] == true || data['extracted'] == true;
        final supportsProcessStreaming =
            stageId == JourneyStageId.analyze ||
            stageId == JourneyStageId.search ||
            stageId == JourneyStageId.answer;
        if (isStreaming && supportsProcessStreaming && message.isNotEmpty) {
          _appendTraceNarrativeEntry(
            key: 'thinking_stream::${stageId.name}',
            stageId: stageId,
            chunk: message,
            provenance: provenance,
            preserveChunk: true,
          );
        }
        break;
      case AssistantTraceEventType.searchQueryGenerated:
        _activateStage(JourneyStageId.search);
        final detail = _searchQueryGeneratedDetail(data: data);
        if (detail.isNotEmpty) {
          _upsertNarrativeEntry(
            key:
                'search_query_generated::${event.toolCallId ?? _searchQueryPlanKey(data)}',
            stageId: JourneyStageId.search,
            headline: '',
            detail: detail,
            status: JourneyStageStatus.active,
            provenance: provenance,
          );
        }
        break;
      case AssistantTraceEventType.searchStarted:
        final message = _sanitizeJourneyText(event.message);
        _activateStage(JourneyStageId.search);
        _upsertToolEntry(
          key: 'search_started::${event.toolCallId ?? _toolNameFromData(data)}',
          toolName: _toolNameFromData(data),
          fallbackStageId: JourneyStageId.search,
          headline: _toolProgressHeadline(
            toolName: _toolNameFromData(data),
            data: data,
            fallback: message,
          ),
          status: JourneyStageStatus.active,
          provenance: provenance,
        );
        break;
      case AssistantTraceEventType.searchCompleted:
        final message = _sanitizeJourneyText(event.message);
        _activateStage(JourneyStageId.verify);
        _completeStage(
          JourneyStageId.search,
          summary: _stageSummaryOrFallback(
            JourneyStageId.search,
            _toolCompletedHeadline(
              toolName: _toolNameFromData(data),
              data: data,
              fallback: message,
            ),
          ),
        );
        _upsertReferenceBundleEntry(
          key:
              'search_completed::${event.toolCallId ?? _toolNameFromData(data)}',
          stageId: JourneyStageId.verify,
          headline: _toolCompletedHeadline(
            toolName: _toolNameFromData(data),
            data: data,
            fallback: message,
          ),
          references: _journeyReferencesFromDynamic(data['references']),
          provenance: provenance,
        );
        break;
      case AssistantTraceEventType.toolStart:
        final message = _sanitizeJourneyText(event.message);
        final toolName = _toolNameFromData(data);
        final stageId = _stageForTool(toolName);
        if (stageId != JourneyStageId.unknown) {
          _activateStage(stageId);
        }
        final headline = _toolStartHeadline(
          toolName: toolName,
          data: data,
          fallback: message,
        );
        if (headline.isNotEmpty) {
          _upsertToolEntry(
            key: 'tool_start::${event.toolCallId ?? toolName}',
            toolName: toolName,
            fallbackStageId: stageId,
            headline: headline,
            status: JourneyStageStatus.active,
            provenance: provenance,
          );
        }
        break;
      case AssistantTraceEventType.toolResult:
        final message = _sanitizeJourneyText(event.message);
        final toolName = _toolNameFromData(data);
        final references = _journeyReferencesFromDynamic(data['references']);
        final isAssessment = data['isAssessment'] == true;
        final stageId = isAssessment
            ? JourneyStageId.verify
            : _stageForToolResult(
                toolName,
                hasReferences: references.isNotEmpty,
              );
        if (stageId != JourneyStageId.unknown) {
          _activateStage(stageId);
        }
        final headline = _toolCompletedHeadline(
          toolName: toolName,
          data: data,
          fallback: message,
        );
        if (references.isNotEmpty || isAssessment) {
          _upsertReferenceBundleEntry(
            key: 'tool_result::${event.toolCallId ?? toolName}',
            stageId: stageId == JourneyStageId.unknown
                ? JourneyStageId.verify
                : stageId,
            headline: headline,
            references: references,
            provenance: provenance,
          );
        } else if (headline.isNotEmpty) {
          _upsertToolEntry(
            key: 'tool_result::${event.toolCallId ?? toolName}',
            toolName: toolName,
            fallbackStageId: stageId,
            headline: headline,
            status: JourneyStageStatus.completed,
            provenance: provenance,
          );
        }
        if (stageId == JourneyStageId.answer) {
          _completeStage(
            JourneyStageId.answer,
            summary: _stageSummaryOrFallback(JourneyStageId.answer, headline),
          );
        }
        break;
      case AssistantTraceEventType.toolError:
        if (data['suppressed'] == true) {
          break;
        }
        final message = _sanitizeJourneyText(event.message);
        final toolName = _toolNameFromData(data);
        final stageId = _stageForTool(toolName);
        if (stageId != JourneyStageId.unknown) {
          _activateStage(stageId);
          if (message.isNotEmpty) {
            _upsertToolEntry(
              key: 'tool_error::${event.toolCallId ?? toolName}',
              toolName: toolName,
              fallbackStageId: stageId,
              headline: message,
              status: JourneyStageStatus.blocked,
              provenance: provenance,
            );
          }
        }
        break;
      case AssistantTraceEventType.answerStarted:
        final message = _sanitizeJourneyText(event.message);
        _activateStage(JourneyStageId.answer);
        _upsertNarrativeEntry(
          key: 'answer_started',
          stageId: JourneyStageId.answer,
          headline: message,
          status: JourneyStageStatus.active,
          provenance: provenance,
        );
        break;
      case AssistantTraceEventType.answerCompleted:
        final message = _sanitizeJourneyText(event.message);
        _completeStage(JourneyStageId.answer, summary: message);
        break;
      case AssistantTraceEventType.replanTriggered:
        final message = _sanitizeJourneyText(event.message);
        _activateStage(JourneyStageId.search);
        if (message.isNotEmpty) {
          _upsertNarrativeEntry(
            key: 'replan',
            stageId: JourneyStageId.search,
            headline: message,
            status: JourneyStageStatus.active,
            kind: JourneyEntryKind.milestone,
            provenance: provenance,
          );
        }
        break;
      case AssistantTraceEventType.selfCheckResult:
        final message = _sanitizeJourneyText(event.message);
        _activateStage(JourneyStageId.verify);
        if (message.isNotEmpty) {
          _upsertNarrativeEntry(
            key: 'self_check',
            stageId: JourneyStageId.verify,
            headline: message,
            status: JourneyStageStatus.completed,
            kind: JourneyEntryKind.milestone,
            provenance: provenance,
          );
        }
        break;
      case AssistantTraceEventType.answerDelta:
      case AssistantTraceEventType.streamDelta:
        _activateStage(JourneyStageId.answer);
        break;
      case AssistantTraceEventType.lifecycleEnd:
        if ((data['lifecycleOutcome'] as String?) == 'completed') {
          _completeStage(JourneyStageId.answer);
        }
        break;
      case AssistantTraceEventType.planCompleted:
      case AssistantTraceEventType.lifecycleStart:
      case AssistantTraceEventType.assistantDelta:
      case AssistantTraceEventType.skillStart:
      case AssistantTraceEventType.skillResult:
      case AssistantTraceEventType.skillError:
      case AssistantTraceEventType.subagentStart:
      case AssistantTraceEventType.subagentResult:
      case AssistantTraceEventType.subagentError:
        break;
    }
    return snapshot;
  }

  AssistantJourney consumeUserEvent(UserEvent event) {
    final payload = event.payload;
    final stageId = _stageFromUserEvent(event);
    _applyReadinessFromUserEventPayload(payload);
    switch (event.type) {
      case UserEventType.answerDelta:
        _activateStage(JourneyStageId.answer);
        break;
      case UserEventType.processReplace:
      case UserEventType.processAppend:
      case UserEventType.processCommit:
        if (stageId == JourneyStageId.unknown) {
          return snapshot;
        }
        final references = _journeyReferencesFromDynamic(
          payload['references'] ?? payload['referenceSummary'],
        );
        final entryKey = _processEntryKey(event, stageId);
        final existingHeadline = _existingEntryHeadline(entryKey);
        final incomingHeadline = _sanitizeJourneyUserEventText(
          payload['headline']?.toString() ?? event.message,
        );
        final detail = _sanitizeJourneyUserEventText(
          (payload['detail'] as String?)?.trim() ?? '',
        );
        final resolvedHeadline = switch (event.type) {
          UserEventType.processReplace => incomingHeadline,
          UserEventType.processAppend => _mergeNarrativeText(
            current: existingHeadline,
            incoming: incomingHeadline,
          ),
          UserEventType.processCommit =>
            incomingHeadline.isNotEmpty ? incomingHeadline : existingHeadline,
          _ => incomingHeadline,
        };
        final provenance = AssistantJourneyProvenance(
          phaseId: parsePlannerPhaseId(
            (payload['phaseId'] as String?)?.trim() ??
                (payload['phase'] as String?)?.trim() ??
                '',
          ),
          actionCode: parsePlannerActionCode(
            (payload['actionCode'] as String?)?.trim() ?? '',
          ),
          reasonCode: parsePlannerReasonCode(
            (payload['reasonCode'] as String?)?.trim() ?? '',
          ),
          toolName: (payload['toolName'] as String?)?.trim() ?? '',
          source: 'user_event',
        );
        _activateStage(stageId);
        if (references.isNotEmpty) {
          _upsertNarrativeEntry(
            key: entryKey,
            stageId: stageId,
            headline: resolvedHeadline,
            detail: detail,
            status: event.type == UserEventType.processCommit
                ? JourneyStageStatus.completed
                : JourneyStageStatus.active,
            kind: JourneyEntryKind.referenceBundle,
            references: references,
            provenance: provenance,
          );
        } else {
          _upsertNarrativeEntry(
            key: entryKey,
            stageId: stageId,
            headline: resolvedHeadline,
            detail: detail,
            status: event.type == UserEventType.processCommit
                ? JourneyStageStatus.completed
                : JourneyStageStatus.active,
            provenance: provenance,
          );
        }
        final explicitSummary = _sanitizeJourneyUserEventText(
          (payload['summary'] as String?)?.trim() ?? '',
        );
        final stageSummary = explicitSummary.isNotEmpty
            ? explicitSummary
            : resolvedHeadline;
        if (stageSummary.isNotEmpty) {
          _updateStage(
            stageId,
            summary: stageSummary,
            referenceCount: references.isNotEmpty ? references.length : null,
            status: event.type == UserEventType.processCommit
                ? JourneyStageStatus.completed
                : JourneyStageStatus.active,
          );
        }
        break;
      case UserEventType.unknown:
        break;
    }
    return snapshot;
  }

  UserEvent? _syntheticUserEventFromTrace(AssistantTraceEvent event) {
    final data = event.data ?? const <String, dynamic>{};
    if (data['syntheticUserEvent'] != true) {
      return null;
    }
    return UserEvent(
      type: _syntheticUserEventType(
        (data['userEventType'] as String?)?.trim() ?? '',
      ),
      scope: _syntheticUserEventScope(
        (data['userEventScope'] as String?)?.trim() ?? '',
      ),
      message: event.message,
      nodeId: (data['nodeId'] as String?)?.trim() ?? '',
      runId: event.runId ?? '',
      payload: data,
    );
  }

  UserEventType _syntheticUserEventType(String raw) {
    switch (raw) {
      case 'process_replace':
        return UserEventType.processReplace;
      case 'process_append':
        return UserEventType.processAppend;
      case 'process_commit':
        return UserEventType.processCommit;
      case 'answer_delta':
        return UserEventType.answerDelta;
      default:
        return UserEventType.unknown;
    }
  }

  UserEventScope _syntheticUserEventScope(String raw) {
    switch (raw) {
      case 'root':
        return UserEventScope.root;
      case 'skill':
        return UserEventScope.skill;
      case 'aggregation':
        return UserEventScope.aggregation;
      default:
        return UserEventScope.unknown;
    }
  }

  AssistantJourney applyReadiness({
    AggregationState? aggregationState,
    ConversationStateDecision? conversationStateDecision,
  }) {
    _readiness = AssistantJourneyReadiness(
      nextAction:
          conversationStateDecision?.nextActionType ??
          AssistantNextAction.unknown,
      finalAnswerMode:
          conversationStateDecision?.finalAnswerModeType ??
          aggregationState?.finalAnswerMode ??
          FinalAnswerMode.blocked,
      answerEligibility:
          conversationStateDecision?.answerEligibilityType ??
          AnswerEligibility.unknown,
      finalAnswerReady:
          conversationStateDecision?.finalAnswerReady ??
          aggregationState?.finalAnswerReady ??
          false,
      clarificationNeeded:
          aggregationState?.clarificationNeeded == true ||
          conversationStateDecision?.nextActionType ==
              AssistantNextAction.askUser,
      needExpansion: aggregationState?.needExpansion == true,
    );
    if (_readiness.finalAnswerReady) {
      _completeStage(JourneyStageId.answer);
    } else if (_readiness.clarificationNeeded || _readiness.needExpansion) {
      final activeStageId = snapshot.activeStageId;
      if (activeStageId != JourneyStageId.unknown) {
        _updateStage(activeStageId, status: JourneyStageStatus.blocked);
      }
    }
    return snapshot;
  }

  AssistantJourney hydrate(AssistantJourney journey) {
    if (journey.isEmpty) return snapshot;
    _stages
      ..clear()
      ..addEntries(
        journey.stages.map((stage) => MapEntry(stage.stageId, stage)),
      );
    _entries
      ..clear()
      ..addAll(journey.entries);
    _entryIndexByKey
      ..clear()
      ..addEntries(
        _entries.asMap().entries.map(
          (entry) => MapEntry(
            entry.value.entryId.isNotEmpty
                ? entry.value.entryId
                : '${entry.value.stageId.name}_${entry.key}',
            entry.key,
          ),
        ),
      );
    _readiness = journey.readiness;
    return snapshot;
  }

  static AssistantJourney replay({
    required List<AssistantTraceEvent> traces,
    required ToolMetadataRegistry toolMetadataRegistry,
    AggregationState? aggregationState,
    ConversationStateDecision? conversationStateDecision,
    AssistantJourney seed = const AssistantJourney(),
  }) {
    final projector = AssistantJourneyProjector(
      toolMetadataRegistry: toolMetadataRegistry,
    );
    if (!seed.isEmpty) {
      projector.hydrate(seed);
    }
    for (final trace in traces) {
      projector.consumeTrace(trace);
    }
    projector.applyReadiness(
      aggregationState: aggregationState,
      conversationStateDecision: conversationStateDecision,
    );
    return projector.snapshot;
  }

  static List<AssistantJourneyStage> _baseStages() {
    return const <AssistantJourneyStage>[
      AssistantJourneyStage(stageId: JourneyStageId.analyze, order: 0),
      AssistantJourneyStage(stageId: JourneyStageId.search, order: 1),
      AssistantJourneyStage(stageId: JourneyStageId.verify, order: 2),
      AssistantJourneyStage(stageId: JourneyStageId.answer, order: 3),
    ];
  }

  List<AssistantJourneyStage> _orderedStages() {
    final stages = _stages.values.toList(growable: false)
      ..sort((a, b) => a.order.compareTo(b.order));
    return stages;
  }

  String _summaryFor(List<AssistantJourneyStage> stages) {
    final active = stages.lastWhere(
      (stage) =>
          stage.status == JourneyStageStatus.active ||
          stage.status == JourneyStageStatus.blocked,
      orElse: () => stages.lastWhere(
        (stage) => stage.status == JourneyStageStatus.completed,
        orElse: () => const AssistantJourneyStage(),
      ),
    );
    if (active.summary.trim().isNotEmpty) {
      return active.summary.trim();
    }
    return '';
  }

  AssistantJourneyReferenceSummary _referenceSummary() {
    final seen = <String>{};
    final references = <AssistantJourneyReference>[];
    for (final entry in _entries) {
      for (final reference in entry.references) {
        final url = reference.url.trim();
        if (url.isEmpty || !seen.add(url)) continue;
        references.add(reference);
      }
    }
    return AssistantJourneyReferenceSummary(
      count: references.length,
      references: references,
    );
  }

  void _activateStage(JourneyStageId stageId) {
    if (stageId == JourneyStageId.unknown) return;
    final target = _stages[stageId];
    if (target == null) return;
    for (final entry in _stages.entries) {
      final current = entry.value;
      if (current.stageId == stageId) {
        _stages[entry.key] = AssistantJourneyStage(
          stageId: current.stageId,
          order: current.order,
          referenceCount: current.referenceCount,
          summary: current.summary,
          status: current.status == JourneyStageStatus.completed
              ? JourneyStageStatus.completed
              : JourneyStageStatus.active,
        );
        continue;
      }
      if (current.order < target.order &&
          (current.status == JourneyStageStatus.active ||
              current.status == JourneyStageStatus.pending)) {
        _stages[entry.key] = AssistantJourneyStage(
          stageId: current.stageId,
          order: current.order,
          summary: current.summary,
          referenceCount: current.referenceCount,
          status: JourneyStageStatus.completed,
        );
      }
    }
  }

  void _completeStage(JourneyStageId stageId, {String? summary}) {
    final current = _stages[stageId];
    if (current == null) return;
    _stages[stageId] = AssistantJourneyStage(
      stageId: current.stageId,
      order: current.order,
      status: JourneyStageStatus.completed,
      summary: summary?.trim().isNotEmpty == true
          ? summary!.trim()
          : current.summary,
      referenceCount: current.referenceCount,
    );
  }

  void _updateStage(
    JourneyStageId stageId, {
    JourneyStageStatus? status,
    String? summary,
    int? referenceCount,
  }) {
    final current = _stages[stageId];
    if (current == null) return;
    _stages[stageId] = AssistantJourneyStage(
      stageId: current.stageId,
      order: current.order,
      status: status ?? current.status,
      summary: summary?.trim().isNotEmpty == true
          ? summary!.trim()
          : current.summary,
      referenceCount: referenceCount ?? current.referenceCount,
    );
  }

  void _upsertToolEntry({
    required String key,
    required String toolName,
    required JourneyStageId fallbackStageId,
    required String headline,
    required JourneyStageStatus status,
    required AssistantJourneyProvenance provenance,
  }) {
    final stageId = _stageForTool(toolName);
    _upsertNarrativeEntry(
      key: key,
      stageId: stageId == JourneyStageId.unknown ? fallbackStageId : stageId,
      headline: headline,
      status: status,
      provenance: provenance,
    );
  }

  void _upsertReferenceBundleEntry({
    required String key,
    required JourneyStageId stageId,
    required String headline,
    required List<AssistantJourneyReference> references,
    required AssistantJourneyProvenance provenance,
  }) {
    final normalizedStage = stageId == JourneyStageId.unknown
        ? JourneyStageId.verify
        : stageId;
    _upsertNarrativeEntry(
      key: key,
      stageId: normalizedStage,
      headline: headline,
      status: JourneyStageStatus.completed,
      kind: JourneyEntryKind.referenceBundle,
      references: references,
      provenance: provenance,
    );
    _updateStage(
      normalizedStage,
      status: JourneyStageStatus.completed,
      summary: _stageSummaryOrFallback(normalizedStage, headline),
      referenceCount: references.length,
    );
  }

  void _upsertNarrativeEntry({
    required String key,
    required JourneyStageId stageId,
    required String headline,
    String detail = '',
    required JourneyStageStatus status,
    required AssistantJourneyProvenance provenance,
    JourneyEntryKind kind = JourneyEntryKind.narrative,
    bool preserveHeadline = false,
    List<AssistantJourneyReference> references =
        const <AssistantJourneyReference>[],
  }) {
    final normalizedHeadline = preserveHeadline
        ? headline.trim()
        : _sanitizeJourneyText(headline);
    final normalizedDetail = _sanitizeJourneyUserEventText(detail);
    if ((normalizedHeadline.isEmpty && normalizedDetail.isEmpty) ||
        stageId == JourneyStageId.unknown) {
      return;
    }
    final existingIndex = _entryIndexByKey[key];
    final entry = AssistantJourneyEntry(
      entryId: key,
      stageId: stageId,
      kind: kind,
      status: status,
      order: existingIndex == null
          ? _orderSeed++
          : _entries[existingIndex].order,
      headline: normalizedHeadline,
      detail: normalizedDetail,
      references: references,
      provenance: provenance,
    );
    if (existingIndex == null) {
      _entryIndexByKey[key] = _entries.length;
      _entries.add(entry);
    } else {
      _entries[existingIndex] = entry;
    }
    _updateStage(
      stageId,
      status: status == JourneyStageStatus.completed
          ? JourneyStageStatus.completed
          : JourneyStageStatus.active,
      summary: _stageSummaryOrFallback(
        stageId,
        normalizedHeadline.isNotEmpty ? normalizedHeadline : normalizedDetail,
      ),
      referenceCount: references.isNotEmpty ? references.length : null,
    );
  }

  void _appendTraceNarrativeEntry({
    required String key,
    required JourneyStageId stageId,
    required String chunk,
    required AssistantJourneyProvenance provenance,
    bool preserveChunk = false,
  }) {
    final merged = _mergeNarrativeText(
      current: _existingEntryHeadline(key),
      incoming: chunk,
    );
    if (merged.isEmpty) return;
    _upsertNarrativeEntry(
      key: key,
      stageId: stageId,
      headline: merged,
      status: JourneyStageStatus.active,
      provenance: provenance,
      preserveHeadline: preserveChunk,
    );
  }

  String _existingEntryHeadline(String key) {
    final index = _entryIndexByKey[key];
    if (index == null || index < 0 || index >= _entries.length) {
      return '';
    }
    return _entries[index].headline;
  }

  String _mergeNarrativeText({
    required String current,
    required String incoming,
  }) {
    final existing = current.trim();
    final next = incoming.trim();
    if (next.isEmpty) return existing;
    if (existing.isEmpty) return next;
    if (existing == next ||
        existing.endsWith(next) ||
        existing.contains(next)) {
      return existing;
    }
    if (next.startsWith(existing)) {
      return next;
    }
    final maxOverlap = existing.length < next.length
        ? existing.length
        : next.length;
    for (var size = maxOverlap; size > 0; size--) {
      if (existing.substring(existing.length - size) ==
          next.substring(0, size)) {
        return '$existing${next.substring(size)}';
      }
    }
    return '$existing$next';
  }

  String _processEntryKey(UserEvent event, JourneyStageId stageId) {
    final nodeId = event.nodeId.trim();
    if (nodeId.isNotEmpty) {
      return 'process::${event.scope.name}::$nodeId';
    }
    return 'process::${event.scope.name}::${stageId.name}';
  }

  JourneyStageId _stageFromUserEvent(UserEvent event) {
    final payload = event.payload;
    final explicit = parseJourneyStageId(
      (payload['stageId'] as String?)?.trim() ??
          (payload['journeyStageId'] as String?)?.trim() ??
          (payload['stage'] as String?)?.trim() ??
          '',
    );
    if (explicit != JourneyStageId.unknown) {
      return explicit;
    }
    final phase =
        (payload['phaseId'] as String?)?.trim() ??
        (payload['phase'] as String?)?.trim() ??
        '';
    if (phase.isNotEmpty) {
      return _stageFromPhaseHint(phase);
    }
    switch (event.scope) {
      case UserEventScope.root:
        return JourneyStageId.analyze;
      case UserEventScope.skill:
        return snapshot.activeStageId == JourneyStageId.unknown
            ? JourneyStageId.search
            : snapshot.activeStageId;
      case UserEventScope.aggregation:
        return _readiness.finalAnswerReady
            ? JourneyStageId.answer
            : JourneyStageId.verify;
      case UserEventScope.unknown:
        return snapshot.activeStageId == JourneyStageId.unknown
            ? JourneyStageId.analyze
            : snapshot.activeStageId;
    }
  }

  void _applyReadinessFromUserEventPayload(Map<String, dynamic> payload) {
    final nextAction = parseAssistantNextAction(
      (payload['nextAction'] as String?)?.trim() ?? '',
    );
    final finalAnswerMode = parseFinalAnswerMode(
      (payload['finalAnswerMode'] as String?)?.trim() ?? '',
    );
    final answerEligibility = parseAnswerEligibility(
      (payload['answerEligibility'] as String?)?.trim() ?? '',
    );
    final hasReadinessUpdate =
        nextAction != AssistantNextAction.unknown ||
        finalAnswerMode != FinalAnswerMode.blocked ||
        answerEligibility != AnswerEligibility.unknown ||
        payload['finalAnswerReady'] is bool ||
        payload['clarificationNeeded'] is bool ||
        payload['needExpansion'] is bool;
    if (!hasReadinessUpdate) return;
    _readiness = AssistantJourneyReadiness(
      nextAction: nextAction != AssistantNextAction.unknown
          ? nextAction
          : _readiness.nextAction,
      finalAnswerMode: finalAnswerMode != FinalAnswerMode.blocked
          ? finalAnswerMode
          : _readiness.finalAnswerMode,
      answerEligibility: answerEligibility != AnswerEligibility.unknown
          ? answerEligibility
          : _readiness.answerEligibility,
      finalAnswerReady: payload['finalAnswerReady'] is bool
          ? payload['finalAnswerReady'] == true
          : _readiness.finalAnswerReady,
      clarificationNeeded: payload['clarificationNeeded'] is bool
          ? payload['clarificationNeeded'] == true
          : _readiness.clarificationNeeded,
      needExpansion: payload['needExpansion'] is bool
          ? payload['needExpansion'] == true
          : _readiness.needExpansion,
    );
  }

  JourneyStageId _stageFromPhaseHint(String phase) {
    final normalized = phase.trim().toLowerCase();
    return switch (normalized) {
      'answer' || 'answering' || 'synthesis' => JourneyStageId.answer,
      'search' ||
      'retrieval' ||
      'retrieval_processing' ||
      'retrieval_design' => JourneyStageId.search,
      'verify' || 'verification' || 'evidence_digest' => JourneyStageId.verify,
      _ => JourneyStageId.analyze,
    };
  }

  JourneyStageId _stageForTool(String toolName) {
    final explicit = _toolMetadataRegistry.journeyStageIdForTool(toolName);
    if (explicit != JourneyStageId.unknown) {
      return explicit;
    }
    return switch (_toolMetadataRegistry.toolKindByName(toolName)) {
      'retrieval' => JourneyStageId.search,
      'context' => JourneyStageId.analyze,
      'media' => JourneyStageId.search,
      'action' => JourneyStageId.answer,
      _ => JourneyStageId.unknown,
    };
  }

  JourneyStageId _stageForToolResult(
    String toolName, {
    required bool hasReferences,
  }) {
    final stageId = _stageForTool(toolName);
    if (hasReferences && stageId == JourneyStageId.search) {
      return JourneyStageId.verify;
    }
    return stageId;
  }

  String _toolNameFromData(Map<String, dynamic> data) {
    return (data['toolName'] as String?)?.trim() ??
        (data['tool'] as String?)?.trim() ??
        '';
  }

  String _searchQueryGeneratedDetail({required Map<String, dynamic> data}) {
    final queryTasks = _queryTasksFromData(data);
    if (queryTasks.isNotEmpty) {
      return _formattedQueryTaskLines(queryTasks).join('\n').trim();
    }
    final query = (data['query'] as String?)?.trim() ?? '';
    if (query.isEmpty) {
      return '';
    }
    return '- $query';
  }

  List<Map<String, dynamic>> _queryTasksFromData(Map<String, dynamic> data) {
    final raw = data['queryTasks'];
    if (raw is! List) {
      return const <Map<String, dynamic>>[];
    }
    return raw
        .whereType<Map>()
        .map((item) => item.cast<String, dynamic>())
        .toList(growable: false);
  }

  List<String> _formattedQueryTaskLines(List<Map<String, dynamic>> queryTasks) {
    final lines = <String>[];
    final seen = <String>{};
    for (final task in queryTasks) {
      final line = _queryTaskDisplayLine(task);
      if (line.isEmpty || !seen.add(line)) {
        continue;
      }
      lines.add(line);
    }
    return lines;
  }

  String _queryTaskDisplayLine(Map<String, dynamic> task) {
    final query = (task['query'] as String?)?.trim() ?? '';
    if (query.isEmpty) {
      return '';
    }
    final objectLabel = _queryTaskObjectLabel(task, query: query);
    final displayLabel = _queryTaskDisplayLabel(task, query: query);
    final prefixParts = <String>[
      if (objectLabel.isNotEmpty) objectLabel,
      if (displayLabel.isNotEmpty) displayLabel,
    ];
    final prefix = prefixParts.join('｜');
    if (prefix.isEmpty ||
        _normalizedCompact(prefix) == _normalizedCompact(query)) {
      return '- $query';
    }
    return '- $prefix';
  }

  String _queryTaskDisplayLabel(
    Map<String, dynamic> task, {
    required String query,
  }) {
    final label = (task['label'] as String?)?.trim() ?? '';
    if (label.isNotEmpty &&
        _normalizedCompact(label) != _normalizedCompact(query)) {
      return label;
    }
    final dimension = (task['dimensionLabel'] as String?)?.trim() ?? '';
    if (dimension.isNotEmpty &&
        _normalizedCompact(dimension) != _normalizedCompact(query)) {
      return dimension;
    }
    return '';
  }

  String _queryTaskObjectLabel(
    Map<String, dynamic> task, {
    required String query,
  }) {
    final anchors =
        (task['entityAnchors'] as List?)
            ?.whereType<String>()
            .map((item) => item.trim())
            .where((item) => item.isNotEmpty)
            .toSet()
            .toList(growable: false) ??
        const <String>[];
    if (anchors.isEmpty) {
      return '';
    }
    final joined = anchors.join(' / ');
    return _normalizedCompact(joined) == _normalizedCompact(query)
        ? ''
        : joined;
  }

  String _normalizedCompact(String raw) {
    return raw.trim().toLowerCase().replaceAll(
      RegExp(r'[\s:：|｜/、,，。！？!?._-]+'),
      '',
    );
  }

  String _searchQueryPlanKey(Map<String, dynamic> data) {
    final query = (data['query'] as String?)?.trim() ?? '';
    if (query.isNotEmpty) {
      return query;
    }
    final queryTasks = _queryTasksFromData(data);
    if (queryTasks.isEmpty) {
      return _toolNameFromData(data);
    }
    return _formattedQueryTaskLines(queryTasks).join('|');
  }

  String _toolStartHeadline({
    required String toolName,
    required Map<String, dynamic> data,
    required String fallback,
  }) {
    final interaction = _toolMetadataRegistry.userInteractionForTool(toolName);
    final executing =
        (interaction?['executing'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final startLabel = (executing['startLabel'] as String?)?.trim() ?? '';
    if (startLabel.isNotEmpty &&
        _toolMetadataRegistry.canResolveTemplate(startLabel, data)) {
      return _toolMetadataRegistry.resolveTemplate(startLabel, data);
    }
    final phaseTitle = (interaction?['phaseTitle'] as String?)?.trim() ?? '';
    if (phaseTitle.isNotEmpty) {
      return phaseTitle;
    }
    return fallback;
  }

  String _toolProgressHeadline({
    required String toolName,
    required Map<String, dynamic> data,
    required String fallback,
  }) {
    final interaction = _toolMetadataRegistry.userInteractionForTool(toolName);
    final executing =
        (interaction?['executing'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final progressTemplate =
        (executing['progressTemplate'] as String?)?.trim() ?? '';
    if (progressTemplate.isNotEmpty &&
        _toolMetadataRegistry.canResolveTemplate(progressTemplate, data)) {
      return _toolMetadataRegistry.resolveTemplate(progressTemplate, data);
    }
    final phaseTitle = (interaction?['phaseTitle'] as String?)?.trim() ?? '';
    if (phaseTitle.isNotEmpty) {
      return phaseTitle;
    }
    return _toolStartHeadline(
      toolName: toolName,
      data: data,
      fallback: fallback,
    );
  }

  String _toolCompletedHeadline({
    required String toolName,
    required Map<String, dynamic> data,
    required String fallback,
  }) {
    final interaction = _toolMetadataRegistry.userInteractionForTool(toolName);
    final executing =
        (interaction?['executing'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final completedTemplate =
        (executing['completedTemplate'] as String?)?.trim() ?? '';
    if (completedTemplate.isNotEmpty &&
        _toolMetadataRegistry.canResolveTemplate(completedTemplate, data)) {
      return _toolMetadataRegistry.resolveTemplate(completedTemplate, data);
    }
    final userMessage = _sanitizeJourneyText(
      (data['userMessage'] as String?)?.trim() ?? '',
    );
    return userMessage.isNotEmpty ? userMessage : fallback;
  }

  List<AssistantJourneyReference> _journeyReferencesFromDynamic(dynamic raw) {
    if (raw is Map) {
      final nested = raw['references'];
      if (nested is List) {
        return _journeyReferencesFromDynamic(nested);
      }
      return const <AssistantJourneyReference>[];
    }
    if (raw is! List) return const <AssistantJourneyReference>[];
    final seen = <String>{};
    final references = <AssistantJourneyReference>[];
    for (final item in raw.whereType<Map>()) {
      final map = item.cast<String, dynamic>();
      final title = (map['title'] as String?)?.trim() ?? '';
      final url = (map['url'] as String?)?.trim() ?? '';
      if (title.isEmpty || url.isEmpty || !seen.add(url)) continue;
      references.add(
        AssistantJourneyReference(
          title: title,
          url: url,
          source: (map['source'] as String?)?.trim() ?? '',
        ),
      );
    }
    return references;
  }

  String _stageSummaryOrFallback(JourneyStageId stageId, String fallback) {
    final summary = fallback.trim();
    if (summary.isNotEmpty) return summary;
    return '';
  }

  String _sanitizeJourneyText(String raw) {
    final text = AssistantDisplayTextResolver.stripRomanizedQueryLeakSentences(
      raw,
    ).trim();
    if (text.isEmpty) return '';
    if (_looksLikeRomanizedQueryFragment(text)) return '';
    if (AssistantDisplayTextResolver.containsInternalProcessFragment(text) ||
        AssistantDisplayTextResolver.containsInternalAssistantProtocolFragment(
          text,
        ) ||
        AssistantDisplayTextResolver.containsTechnicalFailureFragment(text) ||
        AssistantContentFilters.isJsonEnvelope(text) ||
        AssistantContentFilters.isDegradedText(text)) {
      return '';
    }
    return text;
  }

  String _sanitizeJourneyUserEventText(String raw) {
    final text = AssistantDisplayTextResolver.stripRomanizedQueryLeakSentences(
      raw,
    ).trim();
    if (text.isEmpty) return '';
    if (_looksLikeRomanizedQueryFragment(text)) return '';
    if (AssistantDisplayTextResolver.containsInternalProcessFragment(text) ||
        AssistantDisplayTextResolver.containsInternalAssistantProtocolFragment(
          text,
        ) ||
        AssistantDisplayTextResolver.containsTechnicalFailureFragment(text) ||
        AssistantContentFilters.isDegradedText(text) ||
        AssistantContentFilters.isJsonEnvelope(text)) {
      return '';
    }
    return text;
  }

  String _sanitizeThinkingStreamText(String raw) {
    final text =
        AssistantDisplayTextResolver.normalizeUserFacingProcessNarration(
          raw,
        ).trim();
    if (text.isEmpty) return '';
    if (_looksLikeRomanizedQueryFragment(text)) return '';
    return text;
  }

  bool _looksLikeRomanizedQueryFragment(String text) {
    return RegExp(
      r'^[a-z]+(?:\s+[a-z]+){1,7}$',
      caseSensitive: false,
    ).hasMatch(text);
  }
}
