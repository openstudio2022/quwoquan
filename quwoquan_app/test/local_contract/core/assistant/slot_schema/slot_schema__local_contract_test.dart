// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/context-assembly-slot-filling/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/slot_schema.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('slot schema exposes only the canonical typed slot collection', () {
    const schema = SlotSchemaDto(
      slots: <AssistantSlotDefinitionWire>[
        AssistantSlotDefinitionWire(
          slotId: 'travel.destination',
          required: true,
          valueType: 'string',
          parserRefs: <String>['travel.destination.parse'],
          sourcePriority: <String>['conversation', 'page'],
          clarification: AssistantSlotClarificationWire(
            policy: 'ask_user',
            targetSlot: ContextTargetSlot.gpsOrCityLocation,
            prompt: '请确认这次出行的目的地',
            retryPolicy: ContextRetryPolicy.singleRetry,
            scopeExpansionPolicy: ContextScopeExpansionPolicy.none,
          ),
        ),
      ],
      carryOver: true,
      stateId: 'planning',
      nextStateId: 'researching',
    );

    final wire = schema.toJson();
    expect(wire.keys.toSet(), <String>{
      'slots',
      'carryOver',
      'stateId',
      'nextStateId',
    });
    expect(wire, isNot(contains('requiredSlots')));
    expect(wire, isNot(contains('optionalSlots')));

    final decoded = SlotSchemaDto.fromJson(wire);
    expect(decoded.slots.single.slotId, 'travel.destination');
    expect(decoded.slots.single.required, isTrue);
    expect(decoded.slots.single.clarification.policy, 'ask_user');
    expect(decoded.carryOver, isTrue);
    expect(decoded.stateId, 'planning');
    expect(decoded.nextStateId, 'researching');
  });

  test('slot schema rejects retired or unknown fields', () {
    expect(
      () => SlotSchemaDto.fromJson(<String, dynamic>{
        'requiredSlots': <String>['travel.destination'],
      }),
      throwsFormatException,
    );
  });
}
