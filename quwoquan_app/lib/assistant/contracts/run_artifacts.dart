export 'package:quwoquan_app/assistant/generated/contracts/run_artifacts.g.dart';
export 'package:quwoquan_app/assistant/contracts/runtime_enums.dart'
    show
        TraceVisibility,
        ProcessJournalEventType,
        SlotValueStatus,
        parseTraceVisibility,
        parseProcessJournalEventType,
        parseSlotValueStatus;

import 'package:quwoquan_app/assistant/contracts/planner_contracts.dart';
import 'package:quwoquan_app/assistant/contracts/process_protocol.dart';
import 'package:quwoquan_app/assistant/contracts/query_task_contract.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/generated/contracts/run_artifacts.g.dart';

String processJournalEventTypeToWire(ProcessJournalEventType type) =>
    type.wireName;

String slotValueStatusToWire(SlotValueStatus status) => status.wireName;

RunArtifacts parseRunArtifacts(Map<String, dynamic> json) =>
    RunArtifacts.fromJson(json);

ProcessJournalEvent parseProcessJournalEvent(Map<String, dynamic> json) =>
    ProcessJournalEvent.fromJson(json);

SlotStateSnapshot parseSlotStateSnapshot(Map<String, dynamic> json) =>
    SlotStateSnapshot.fromJson(json);

SlotValueSnapshot parseSlotValueSnapshot(Map<String, dynamic> json) =>
    SlotValueSnapshot.fromJson(json);

extension TraceVisibilityCompat on TraceVisibility {
  bool get isUserVisible => this == TraceVisibility.userVisible;
}

extension ProcessJournalEventCompat on ProcessJournalEvent {
  PlannerPhaseId get stageType => parsePlannerPhaseId(stage);

  PlannerPhaseId get phaseIdType => parsePlannerPhaseId(phaseId);

  PlannerActionCode get actionCodeType => parsePlannerActionCode(actionCode);

  PlannerReasonCode get reasonCodeType => parsePlannerReasonCode(reasonCode);

  ProcessProtocolCode get protocolCode => ProcessProtocolCode.fromWire(
    stage: stage,
    phaseId: phaseId,
    actionCode: actionCode,
    reasonCode: reasonCode,
  );

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
}

extension EvidenceLedgerEntryCompat on EvidenceLedgerEntry {
  QueryTaskDimension get dimensionType => parseQueryTaskDimension(
    dimension.trim().isNotEmpty ? dimension : dimensionLabel,
  );

  String get effectiveDimensionLabel => dimensionLabel.trim().isNotEmpty
      ? dimensionLabel.trim()
      : dimensionType.displayLabel;

  EvidenceSourceTier get sourceTierType => parseEvidenceSourceTier(sourceTier);
}

const Object _slotValueNoop = Object();

extension SlotValueSnapshotCompat on SlotValueSnapshot {
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

extension SlotStateSnapshotCompat on SlotStateSnapshot {
  SlotValueSnapshot? slotValueOf(String slotId) {
    final normalized = slotId.trim();
    if (normalized.isEmpty) return null;
    final exact = slotValues[normalized];
    if (exact != null) {
      return exact.slotId.trim().isNotEmpty
          ? exact
          : exact.copyWith(slotId: normalized);
    }
    for (final entry in slotValues.entries) {
      if (entry.key.trim() == normalized) {
        final value = entry.value;
        return value.slotId.trim().isNotEmpty
            ? value
            : value.copyWith(slotId: normalized);
      }
      if (entry.value.slotId.trim() == normalized) {
        return entry.value;
      }
    }
    final unnamed = slotValues[''];
    if (unnamed != null && slotValues.length == 1) {
      return unnamed.copyWith(slotId: normalized);
    }
    return null;
  }
}
