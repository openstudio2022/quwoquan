export 'package:quwoquan_app/assistant/generated/contracts/run_artifacts.g.dart';
export 'package:quwoquan_app/assistant/contracts/run_artifacts_map_partition.dart';
export 'package:quwoquan_app/assistant/generated/contracts/run_artifacts_map_stable_keys.g.dart';
export 'package:quwoquan_app/assistant/contracts/slot_value_codec.dart';
export 'package:quwoquan_app/assistant/contracts/runtime_enums.dart'
    show
        DisplayBlockKind,
        DisplayListStyle,
        ProcessStepId,
        ProcessDisplayBlockKind,
        SlotValueStatus,
        TraceVisibility,
        parseDisplayBlockKind,
        parseDisplayListStyle,
        parseProcessStepId,
        parseProcessDisplayBlockKind,
        parseSlotValueStatus,
        parseTraceVisibility;

import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/contracts/search_plan_contract.dart';
import 'package:quwoquan_app/assistant/generated/contracts/run_artifacts.g.dart';

String slotValueStatusToWire(SlotValueStatus status) => status.wireName;

RunArtifacts parseRunArtifacts(Map<String, dynamic> json) =>
    RunArtifacts.fromJson(_normalizeRunArtifactsWireMap(json));

const Set<String> _runArtifactsStringWireKeys = <String>{
  'activeStepId',
  'answerEligibility',
  'blockId',
  'body',
  'claim',
  'continuityMode',
  'detail',
  'dimension',
  'dimensionLabel',
  'displayMarkdown',
  'displayPlainText',
  'domainId',
  'evidenceId',
  'evidenceSummary',
  'expansionReason',
  'finalAnswerMode',
  'frameId',
  'headline',
  'intentSummary',
  'itemId',
  'kind',
  'label',
  'listStyle',
  'machineEnvelope',
  'mismatchSignal',
  'nextAction',
  'note',
  'originalValue',
  'processingSummary',
  'readinessSummary',
  'reasoning',
  'renderFallback',
  'renderMode',
  'resolvedValue',
  'retrieveMoreReason',
  'retrievalDesignNarrative',
  'searchPlanId',
  'slotId',
  'snippet',
  'source',
  'sourceHost',
  'sourceTier',
  'status',
  'stepId',
  'summary',
  'synthesisReason',
  'title',
  'updatedAt',
  'url',
  'userFacingSummary',
};

Map<String, dynamic> _normalizeRunArtifactsWireMap(Map<String, dynamic> json) {
  return json.map((key, value) {
    if (_runArtifactsStringWireKeys.contains(key) &&
        value != null &&
        value is! String) {
      return MapEntry(key, value.toString());
    }
    if (value is Map) {
      return MapEntry(
        key,
        _normalizeRunArtifactsWireMap(value.cast<String, dynamic>()),
      );
    }
    if (value is List) {
      return MapEntry(
        key,
        value
            .map(
              (item) => item is Map
                  ? _normalizeRunArtifactsWireMap(item.cast<String, dynamic>())
                  : item,
            )
            .toList(growable: false),
      );
    }
    return MapEntry(key, value);
  });
}

AssistantJourney parseAssistantJourney(Map<String, dynamic> json) =>
    AssistantJourney.fromJson(json);

SlotStateSnapshot parseSlotStateSnapshot(Map<String, dynamic> json) =>
    SlotStateSnapshot.fromJson(json);

SlotValueSnapshot parseSlotValueSnapshot(Map<String, dynamic> json) =>
    SlotValueSnapshot.fromJson(json);

extension TraceVisibilityCompat on TraceVisibility {
  bool get isUserVisible => this == TraceVisibility.userVisible;
}

extension EvidenceLedgerEntryCompat on EvidenceLedgerEntry {
  SearchPlanDimension get dimensionType => parseSearchPlanDimension(
    dimension.trim().isNotEmpty ? dimension : dimensionLabel,
  );

  String get effectiveDimensionLabel => dimensionLabel.trim().isNotEmpty
      ? dimensionLabel.trim()
      : dimensionType.displayLabel;

  EvidenceSourceTier get sourceTierType => parseEvidenceSourceTier(sourceTier);
}

extension RunArtifactsCompat on RunArtifacts {
  AssistantJourney get canonicalJourney => journey;
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
