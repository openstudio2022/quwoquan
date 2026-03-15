// Runtime-only protocol boundary:
// This wrapper only adapts the current keyed slotFillPlan payload shape to the
// generated metadata contract. Shared protocol fields must live in assistant
// metadata/codegen rather than expanding this file.

export 'package:quwoquan_app/assistant/internal_legacy/contracts/runtime_enums.dart';
export 'package:quwoquan_app/assistant/generated/contracts/planner_contracts.g.dart';

import 'package:quwoquan_app/assistant/internal_legacy/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/generated/contracts/planner_contracts.g.dart';

class SlotFillPlan extends SlotFillPlanDto {
  const SlotFillPlan({super.entries = const <String, SlotFillEntry>{}});

  bool get isEmpty => entries.isEmpty;
  bool get isNotEmpty => entries.isNotEmpty;

  bool get hasAskUser =>
      entries.values.any((entry) => entry.action == SlotFillAction.askUser);

  Map<String, dynamic> toFilledSlots() {
    final result = <String, dynamic>{};
    for (final entry in entries.values) {
      final value = entry.value;
      if (value == null) {
        continue;
      }
      if (value is String && value.trim().isEmpty) {
        continue;
      }
      result[entry.slotId] = value;
    }
    return result;
  }

  factory SlotFillPlan.fromJson(Map<String, dynamic>? json) {
    if (json == null || json.isEmpty) {
      return const SlotFillPlan();
    }
    final entries = <String, SlotFillEntry>{};
    for (final rawEntry in json.entries) {
      final slotId = rawEntry.key.trim();
      if (slotId.isEmpty) {
        continue;
      }
      final value = rawEntry.value;
      if (value is Map) {
        entries[slotId] = _slotFillEntryFromRaw(
          slotId,
          value.cast<String, dynamic>(),
        );
        continue;
      }
      entries[slotId] = SlotFillEntry(
        slotId: slotId,
        value: value,
        source: SlotSource.userQueryLlm,
        action: SlotFillAction.autoFilled,
        confidence: 0.8,
      );
    }
    return SlotFillPlan(entries: entries);
  }
}

SlotFillEntry _slotFillEntryFromRaw(
  String slotId,
  Map<String, dynamic> json,
) {
  return SlotFillEntry(
    slotId: slotId,
    value: json['value'],
    source: parseSlotSource(
      ((json['source'] ?? json['detectedFrom']) as String?)?.trim() ?? '',
    ),
    action: parseSlotFillAction(
      ((json['action'] ?? json['fillStrategy']) as String?)?.trim() ?? '',
    ),
    confidence: (json['confidence'] as num?)?.toDouble() ?? 0.0,
  );
}
