export 'package:quwoquan_app/assistant/generated/contracts/slot_schema.g.dart';

import 'package:quwoquan_app/assistant/generated/contracts/slot_schema.g.dart';

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
