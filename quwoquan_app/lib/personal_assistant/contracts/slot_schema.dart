export 'package:quwoquan_app/personal_assistant/runtime/generated/contracts/slot_schema.g.dart';

import 'package:quwoquan_app/personal_assistant/runtime/generated/contracts/slot_schema.g.dart';

class SlotSchema extends SlotSchemaDto {
  const SlotSchema({
    super.requiredSlots = const <String>[],
    super.optionalSlots = const <String>[],
    super.carryOver = false,
    super.stateId = '',
    super.nextStateId = '',
  });

  Map<String, dynamic> toSchemaMap() => toJson();
}
