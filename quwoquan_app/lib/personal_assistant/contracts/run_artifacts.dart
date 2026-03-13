enum TraceVisibility { userVisible, system, internal }

TraceVisibility parseTraceVisibility(String raw) {
  switch (raw.trim()) {
    case 'internal':
      return TraceVisibility.internal;
    case 'system':
      return TraceVisibility.system;
    case 'user_visible':
    case 'userVisible':
    default:
      return TraceVisibility.userVisible;
  }
}

extension TraceVisibilityX on TraceVisibility {
  String get wireName {
    switch (this) {
      case TraceVisibility.userVisible:
        return 'user_visible';
      case TraceVisibility.system:
        return 'system';
      case TraceVisibility.internal:
        return 'internal';
    }
  }

  bool get isUserVisible => this == TraceVisibility.userVisible;
}

class ProcessSourceReference {
  const ProcessSourceReference({
    required this.title,
    required this.url,
    this.source = '',
  });

  final String title;
  final String url;
  final String source;

  Map<String, dynamic> toJson() => <String, dynamic>{
        'title': title,
        'url': url,
        'source': source,
      };

  factory ProcessSourceReference.fromJson(Map<String, dynamic> json) {
    return ProcessSourceReference(
      title: (json['title'] as String?)?.trim() ?? '',
      url: (json['url'] as String?)?.trim() ?? '',
      source: (json['source'] as String?)?.trim() ?? '',
    );
  }
}

enum ProcessJournalEventType {
  stageSet,
  narrativeCommit,
  liveCursor,
  sourceUpdate,
  answerDelta,
  completed,
}

ProcessJournalEventType parseProcessJournalEventType(String raw) {
  switch (raw.trim()) {
    case 'stage_set':
      return ProcessJournalEventType.stageSet;
    case 'narrative_commit':
      return ProcessJournalEventType.narrativeCommit;
    case 'live_cursor':
      return ProcessJournalEventType.liveCursor;
    case 'source_update':
      return ProcessJournalEventType.sourceUpdate;
    case 'answer_delta':
      return ProcessJournalEventType.answerDelta;
    case 'completed':
      return ProcessJournalEventType.completed;
    default:
      return ProcessJournalEventType.narrativeCommit;
  }
}

String processJournalEventTypeToWire(ProcessJournalEventType type) {
  switch (type) {
    case ProcessJournalEventType.stageSet:
      return 'stage_set';
    case ProcessJournalEventType.narrativeCommit:
      return 'narrative_commit';
    case ProcessJournalEventType.liveCursor:
      return 'live_cursor';
    case ProcessJournalEventType.sourceUpdate:
      return 'source_update';
    case ProcessJournalEventType.answerDelta:
      return 'answer_delta';
    case ProcessJournalEventType.completed:
      return 'completed';
  }
}

class ProcessJournalEvent {
  const ProcessJournalEvent({
    required this.eventId,
    required this.type,
    required this.stage,
    this.phaseId = '',
    this.actionCode = '',
    this.reasonCode = '',
    this.reasonShort = '',
    this.source = '',
    this.nodeId = '',
    this.message = '',
    this.runId = '',
    this.traceId = '',
    this.references = const <ProcessSourceReference>[],
    this.payload = const <String, dynamic>{},
    this.timestamp,
  });

  final String eventId;
  final ProcessJournalEventType type;
  final String stage;
  final String phaseId;
  final String actionCode;
  final String reasonCode;
  final String reasonShort;
  final String source;
  final String nodeId;
  final String message;
  final String runId;
  final String traceId;
  final List<ProcessSourceReference> references;
  final Map<String, dynamic> payload;
  final DateTime? timestamp;

  ProcessJournalEvent copyWith({
    String? eventId,
    ProcessJournalEventType? type,
    String? stage,
    String? phaseId,
    String? actionCode,
    String? reasonCode,
    String? reasonShort,
    String? source,
    String? nodeId,
    String? message,
    String? runId,
    String? traceId,
    List<ProcessSourceReference>? references,
    Map<String, dynamic>? payload,
    DateTime? timestamp,
  }) {
    return ProcessJournalEvent(
      eventId: eventId ?? this.eventId,
      type: type ?? this.type,
      stage: stage ?? this.stage,
      phaseId: phaseId ?? this.phaseId,
      actionCode: actionCode ?? this.actionCode,
      reasonCode: reasonCode ?? this.reasonCode,
      reasonShort: reasonShort ?? this.reasonShort,
      source: source ?? this.source,
      nodeId: nodeId ?? this.nodeId,
      message: message ?? this.message,
      runId: runId ?? this.runId,
      traceId: traceId ?? this.traceId,
      references: references ?? this.references,
      payload: payload ?? this.payload,
      timestamp: timestamp ?? this.timestamp,
    );
  }

  String get displayMessage {
    final preferred = reasonShort.trim();
    if (preferred.isNotEmpty) return preferred;
    return message.trim();
  }

  Map<String, dynamic> toJson() => <String, dynamic>{
        'eventId': eventId,
        'type': processJournalEventTypeToWire(type),
        'stage': stage,
        'phaseId': phaseId,
        'actionCode': actionCode,
        'reasonCode': reasonCode,
        'reasonShort': reasonShort,
        'source': source,
        'nodeId': nodeId,
        'message': message,
        'runId': runId,
        'traceId': traceId,
        'references':
            references.map((item) => item.toJson()).toList(growable: false),
        'payload': payload,
        'timestamp': timestamp?.toIso8601String(),
      };

  factory ProcessJournalEvent.fromJson(Map<String, dynamic> json) {
    final rawTimestamp = (json['timestamp'] as String?)?.trim() ?? '';
    return ProcessJournalEvent(
      eventId: (json['eventId'] as String?)?.trim() ?? '',
      type: parseProcessJournalEventType((json['type'] as String?)?.trim() ?? ''),
      stage: (json['stage'] as String?)?.trim() ?? '',
      phaseId:
          (json['phaseId'] as String?)?.trim() ??
          (json['stage'] as String?)?.trim() ??
          '',
      actionCode: (json['actionCode'] as String?)?.trim() ?? '',
      reasonCode: (json['reasonCode'] as String?)?.trim() ?? '',
      reasonShort:
          (json['reasonShort'] as String?)?.trim() ??
          (json['message'] as String?)?.trim() ??
          '',
      source: (json['source'] as String?)?.trim() ?? '',
      nodeId: (json['nodeId'] as String?)?.trim() ?? '',
      message: (json['message'] as String?)?.trim() ?? '',
      runId: (json['runId'] as String?)?.trim() ?? '',
      traceId: (json['traceId'] as String?)?.trim() ?? '',
      references: (json['references'] as List?)
              ?.whereType<Map>()
              .map(
                (item) =>
                    ProcessSourceReference.fromJson(item.cast<String, dynamic>()),
              )
              .toList(growable: false) ??
          const <ProcessSourceReference>[],
      payload:
          (json['payload'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      timestamp: rawTimestamp.isEmpty ? null : DateTime.tryParse(rawTimestamp),
    );
  }
}

class EvidenceLedgerEntry {
  const EvidenceLedgerEntry({
    required this.evidenceId,
    this.domainId = '',
    this.dimension = '',
    this.queryTaskId = '',
    this.title = '',
    this.url = '',
    this.sourceHost = '',
    this.sourceTier = '',
    this.freshnessHours = 0,
    this.authorityScore = 0,
    this.relevanceScore = 0,
    this.slotContributions = const <String, dynamic>{},
    this.snippet = '',
    this.retrievedAt = '',
  });

  final String evidenceId;
  final String domainId;
  final String dimension;
  final String queryTaskId;
  final String title;
  final String url;
  final String sourceHost;
  final String sourceTier;
  final int freshnessHours;
  final double authorityScore;
  final double relevanceScore;
  final Map<String, dynamic> slotContributions;
  final String snippet;
  final String retrievedAt;

  Map<String, dynamic> toJson() => <String, dynamic>{
        'evidenceId': evidenceId,
        'domainId': domainId,
        'dimension': dimension,
        'queryTaskId': queryTaskId,
        'title': title,
        'url': url,
        'sourceHost': sourceHost,
        'sourceTier': sourceTier,
        'freshnessHours': freshnessHours,
        'authorityScore': authorityScore,
        'relevanceScore': relevanceScore,
        'slotContributions': slotContributions,
        'snippet': snippet,
        'retrievedAt': retrievedAt,
      };

  factory EvidenceLedgerEntry.fromJson(Map<String, dynamic> json) {
    return EvidenceLedgerEntry(
      evidenceId: (json['evidenceId'] as String?)?.trim() ?? '',
      domainId: (json['domainId'] as String?)?.trim() ?? '',
      dimension: (json['dimension'] as String?)?.trim() ?? '',
      queryTaskId: (json['queryTaskId'] as String?)?.trim() ?? '',
      title: (json['title'] as String?)?.trim() ?? '',
      url: (json['url'] as String?)?.trim() ?? '',
      sourceHost: (json['sourceHost'] as String?)?.trim() ?? '',
      sourceTier: (json['sourceTier'] as String?)?.trim() ?? '',
      freshnessHours: (json['freshnessHours'] as num?)?.toInt() ?? 0,
      authorityScore: (json['authorityScore'] as num?)?.toDouble() ?? 0,
      relevanceScore: (json['relevanceScore'] as num?)?.toDouble() ?? 0,
      slotContributions:
          (json['slotContributions'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      snippet: (json['snippet'] as String?)?.trim() ?? '',
      retrievedAt: (json['retrievedAt'] as String?)?.trim() ?? '',
    );
  }
}

class AnswerEvidenceBinding {
  const AnswerEvidenceBinding({
    required this.bindingId,
    this.label = '',
    this.claim = '',
    this.evidenceId = '',
    this.url = '',
    this.title = '',
    this.source = '',
    this.snippet = '',
  });

  final String bindingId;
  final String label;
  final String claim;
  final String evidenceId;
  final String url;
  final String title;
  final String source;
  final String snippet;

  Map<String, dynamic> toJson() => <String, dynamic>{
        'bindingId': bindingId,
        'label': label,
        'claim': claim,
        'evidenceId': evidenceId,
        'url': url,
        'title': title,
        'source': source,
        'snippet': snippet,
      };

  factory AnswerEvidenceBinding.fromJson(Map<String, dynamic> json) {
    return AnswerEvidenceBinding(
      bindingId: (json['bindingId'] as String?)?.trim() ?? '',
      label: (json['label'] as String?)?.trim() ?? '',
      claim: (json['claim'] as String?)?.trim() ?? '',
      evidenceId: (json['evidenceId'] as String?)?.trim() ?? '',
      url: (json['url'] as String?)?.trim() ?? '',
      title: (json['title'] as String?)?.trim() ?? '',
      source: (json['source'] as String?)?.trim() ?? '',
      snippet: (json['snippet'] as String?)?.trim() ?? '',
    );
  }
}

enum SlotValueStatus {
  missing,
  inferred,
  confirmed,
  stale,
  conflicted,
}

SlotValueStatus parseSlotValueStatus(String raw) {
  switch (raw.trim()) {
    case 'missing':
      return SlotValueStatus.missing;
    case 'inferred':
      return SlotValueStatus.inferred;
    case 'confirmed':
      return SlotValueStatus.confirmed;
    case 'stale':
      return SlotValueStatus.stale;
    case 'conflicted':
      return SlotValueStatus.conflicted;
    default:
      return SlotValueStatus.inferred;
  }
}

String slotValueStatusToWire(SlotValueStatus status) {
  switch (status) {
    case SlotValueStatus.missing:
      return 'missing';
    case SlotValueStatus.inferred:
      return 'inferred';
    case SlotValueStatus.confirmed:
      return 'confirmed';
    case SlotValueStatus.stale:
      return 'stale';
    case SlotValueStatus.conflicted:
      return 'conflicted';
  }
}

class SlotValueSnapshot {
  const SlotValueSnapshot({
    required this.slotId,
    this.status = SlotValueStatus.inferred,
    this.value,
    this.source = '',
    this.confidence = 0,
    this.updatedAt = '',
    this.note = '',
    this.candidates = const <String>[],
    this.evidenceIds = const <String>[],
  });

  final String slotId;
  final SlotValueStatus status;
  final dynamic value;
  final String source;
  final double confidence;
  final String updatedAt;
  final String note;
  final List<String> candidates;
  final List<String> evidenceIds;

  Map<String, dynamic> toJson() => <String, dynamic>{
        'slotId': slotId,
        'status': slotValueStatusToWire(status),
        'value': value,
        'source': source,
        'confidence': confidence,
        'updatedAt': updatedAt,
        'note': note,
        'candidates': candidates,
        'evidenceIds': evidenceIds,
      };

  factory SlotValueSnapshot.fromJson(
    String fallbackSlotId,
    Map<String, dynamic> json,
  ) {
    return SlotValueSnapshot(
      slotId: (json['slotId'] as String?)?.trim().isNotEmpty == true
          ? (json['slotId'] as String).trim()
          : fallbackSlotId,
      status: parseSlotValueStatus((json['status'] as String?)?.trim() ?? ''),
      value: json['value'],
      source: (json['source'] as String?)?.trim() ?? '',
      confidence: (json['confidence'] as num?)?.toDouble() ?? 0,
      updatedAt: (json['updatedAt'] as String?)?.trim() ?? '',
      note: (json['note'] as String?)?.trim() ?? '',
      candidates: (json['candidates'] as List?)
              ?.map((item) => item.toString().trim())
              .where((item) => item.isNotEmpty)
              .toList(growable: false) ??
          const <String>[],
      evidenceIds: (json['evidenceIds'] as List?)
              ?.map((item) => item.toString().trim())
              .where((item) => item.isNotEmpty)
              .toList(growable: false) ??
          const <String>[],
    );
  }

  SlotValueSnapshot copyWith({
    String? slotId,
    SlotValueStatus? status,
    dynamic value = _slotValueNoop,
    String? source,
    double? confidence,
    String? updatedAt,
    String? note,
    List<String>? candidates,
    List<String>? evidenceIds,
  }) {
    return SlotValueSnapshot(
      slotId: slotId ?? this.slotId,
      status: status ?? this.status,
      value: identical(value, _slotValueNoop) ? this.value : value,
      source: source ?? this.source,
      confidence: confidence ?? this.confidence,
      updatedAt: updatedAt ?? this.updatedAt,
      note: note ?? this.note,
      candidates: candidates ?? this.candidates,
      evidenceIds: evidenceIds ?? this.evidenceIds,
    );
  }
}

const Object _slotValueNoop = Object();

class SlotStateSnapshot {
  const SlotStateSnapshot({
    this.domainId = '',
    this.slots = const <String, dynamic>{},
    this.slotValues = const <String, SlotValueSnapshot>{},
    this.missingSlots = const <String>[],
    this.updatedAt = '',
  });

  final String domainId;
  final Map<String, dynamic> slots;
  final Map<String, SlotValueSnapshot> slotValues;
  final List<String> missingSlots;
  final String updatedAt;

  Map<String, dynamic> toJson() => <String, dynamic>{
        'domainId': domainId,
        'slots': slots,
        'slotValues': <String, dynamic>{
          for (final entry in slotValues.entries) entry.key: entry.value.toJson(),
        },
        'missingSlots': missingSlots,
        'updatedAt': updatedAt,
      };

  factory SlotStateSnapshot.fromJson(Map<String, dynamic> json) {
    final slots =
        (json['slots'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final slotValues =
        (json['slotValues'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    return SlotStateSnapshot(
      domainId: (json['domainId'] as String?)?.trim() ?? '',
      slots: slots,
      slotValues: slotValues.isNotEmpty
          ? <String, SlotValueSnapshot>{
              for (final entry in slotValues.entries)
                entry.key: entry.value is Map
                    ? SlotValueSnapshot.fromJson(
                        entry.key,
                        (entry.value as Map).cast<String, dynamic>(),
                      )
                    : SlotValueSnapshot(
                        slotId: entry.key,
                        status: SlotValueStatus.inferred,
                        value: entry.value,
                      ),
            }
          : _deriveSlotValues(
              slots,
              (json['missingSlots'] as List?)
                      ?.whereType<String>()
                      .toList(growable: false) ??
                  const <String>[],
            ),
      missingSlots:
          (json['missingSlots'] as List?)
              ?.whereType<String>()
              .toList(growable: false) ??
          const <String>[],
      updatedAt: (json['updatedAt'] as String?)?.trim() ?? '',
    );
  }

  SlotValueSnapshot? slotValueOf(String slotId) => slotValues[slotId];

  static Map<String, SlotValueSnapshot> _deriveSlotValues(
    Map<String, dynamic> slots,
    List<String> missingSlots,
  ) {
    final derived = <String, SlotValueSnapshot>{};
    for (final entry in slots.entries) {
      final value = entry.value;
      if (value is Map && value['status'] != null) {
        derived[entry.key] = SlotValueSnapshot.fromJson(
          entry.key,
          value.cast<String, dynamic>(),
        );
        continue;
      }
      derived[entry.key] = SlotValueSnapshot(
        slotId: entry.key,
        status: SlotValueStatus.confirmed,
        value: value,
      );
    }
    for (final slotId in missingSlots) {
      derived.putIfAbsent(
        slotId,
        () => SlotValueSnapshot(
          slotId: slotId,
          status: SlotValueStatus.missing,
        ),
      );
    }
    return derived;
  }
}

class DomainPolicyBundle {
  const DomainPolicyBundle({
    this.domainId = '',
    this.executionPolicy = const <String, dynamic>{},
    this.slotSchema = const <String, dynamic>{},
    this.dialoguePolicy = const <String, dynamic>{},
    this.authorityPolicy = const <String, dynamic>{},
    this.retrievalPolicy = const <String, dynamic>{},
    this.answerPolicy = const <String, dynamic>{},
    this.narrativePolicy = const <String, dynamic>{},
  });

  final String domainId;
  final Map<String, dynamic> executionPolicy;
  final Map<String, dynamic> slotSchema;
  final Map<String, dynamic> dialoguePolicy;
  final Map<String, dynamic> authorityPolicy;
  final Map<String, dynamic> retrievalPolicy;
  final Map<String, dynamic> answerPolicy;
  final Map<String, dynamic> narrativePolicy;

  Map<String, dynamic> toJson() => <String, dynamic>{
        'domainId': domainId,
        'executionPolicy': executionPolicy,
        'slotSchema': slotSchema,
        'dialoguePolicy': dialoguePolicy,
        'authorityPolicy': authorityPolicy,
        'retrievalPolicy': retrievalPolicy,
        'answerPolicy': answerPolicy,
        'narrativePolicy': narrativePolicy,
      };

  factory DomainPolicyBundle.fromJson(Map<String, dynamic> json) {
    return DomainPolicyBundle(
      domainId: (json['domainId'] as String?)?.trim() ?? '',
      executionPolicy:
          (json['executionPolicy'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      slotSchema:
          (json['slotSchema'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      dialoguePolicy:
          (json['dialoguePolicy'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      authorityPolicy:
          (json['authorityPolicy'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      retrievalPolicy:
          (json['retrievalPolicy'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      answerPolicy:
          (json['answerPolicy'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      narrativePolicy:
          (json['narrativePolicy'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
    );
  }
}

class RunArtifacts {
  const RunArtifacts({
    this.machineEnvelope = '',
    this.displayMarkdown = '',
    this.displayPlainText = '',
    this.processJournal = const <ProcessJournalEvent>[],
    this.liveCursor,
    this.evidenceLedger = const <EvidenceLedgerEntry>[],
    this.answerEvidenceBindings = const <AnswerEvidenceBinding>[],
    this.slotState = const SlotStateSnapshot(),
    this.answerDecision = const <String, dynamic>{},
    this.diagnostics = const <String, dynamic>{},
    this.domainPolicyBundle,
  });

  final String machineEnvelope;
  final String displayMarkdown;
  final String displayPlainText;
  final List<ProcessJournalEvent> processJournal;
  final ProcessJournalEvent? liveCursor;
  final List<EvidenceLedgerEntry> evidenceLedger;
  final List<AnswerEvidenceBinding> answerEvidenceBindings;
  final SlotStateSnapshot slotState;
  final Map<String, dynamic> answerDecision;
  final Map<String, dynamic> diagnostics;
  final DomainPolicyBundle? domainPolicyBundle;

  Map<String, dynamic> toJson() => <String, dynamic>{
        'machineEnvelope': machineEnvelope,
        'displayMarkdown': displayMarkdown,
        'displayPlainText': displayPlainText,
        'processJournal':
            processJournal.map((item) => item.toJson()).toList(growable: false),
        'liveCursor': liveCursor?.toJson(),
        'evidenceLedger':
            evidenceLedger.map((item) => item.toJson()).toList(growable: false),
        'answerEvidenceBindings': answerEvidenceBindings
            .map((item) => item.toJson())
            .toList(growable: false),
        'slotState': slotState.toJson(),
        'answerDecision': answerDecision,
        'diagnostics': diagnostics,
        'domainPolicyBundle': domainPolicyBundle?.toJson(),
      };

  factory RunArtifacts.fromJson(Map<String, dynamic> json) {
    final liveCursorMap = (json['liveCursor'] as Map?)?.cast<String, dynamic>();
    final policyMap =
        (json['domainPolicyBundle'] as Map?)?.cast<String, dynamic>();
    return RunArtifacts(
      machineEnvelope: (json['machineEnvelope'] as String?)?.trim() ?? '',
      displayMarkdown: (json['displayMarkdown'] as String?)?.trim() ?? '',
      displayPlainText: (json['displayPlainText'] as String?)?.trim() ?? '',
      processJournal: (json['processJournal'] as List?)
              ?.whereType<Map>()
              .map((item) => ProcessJournalEvent.fromJson(item.cast<String, dynamic>()))
              .toList(growable: false) ??
          const <ProcessJournalEvent>[],
      liveCursor: liveCursorMap == null
          ? null
          : ProcessJournalEvent.fromJson(liveCursorMap),
      evidenceLedger: (json['evidenceLedger'] as List?)
              ?.whereType<Map>()
              .map((item) => EvidenceLedgerEntry.fromJson(item.cast<String, dynamic>()))
              .toList(growable: false) ??
          const <EvidenceLedgerEntry>[],
      answerEvidenceBindings: (json['answerEvidenceBindings'] as List?)
              ?.whereType<Map>()
              .map(
                (item) => AnswerEvidenceBinding.fromJson(
                  item.cast<String, dynamic>(),
                ),
              )
              .toList(growable: false) ??
          const <AnswerEvidenceBinding>[],
      slotState: (json['slotState'] as Map?) != null
          ? SlotStateSnapshot.fromJson(
              (json['slotState'] as Map).cast<String, dynamic>(),
            )
          : const SlotStateSnapshot(),
      answerDecision:
          (json['answerDecision'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      diagnostics:
          (json['diagnostics'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      domainPolicyBundle: policyMap == null
          ? null
          : DomainPolicyBundle.fromJson(policyMap),
    );
  }
}
