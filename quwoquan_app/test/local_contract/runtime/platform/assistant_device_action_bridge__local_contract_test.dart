// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/tool-fabric-runtime/spec.md#gwt-003
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/platform/assistant_device_action_bridge.dart';

void main() {
  const bridge = MethodChannelAssistantDeviceActionBridge();
  final request = AssistantCalendarReminderRequest(
    idempotencyKey: 'tool-calendar-1',
    title: '西湖集合',
    startsAt: DateTime.parse('2026-08-02T09:00:00+08:00'),
    durationMinutes: 60,
    reminderMinutes: 10,
    notes: '断桥集合',
  );

  test('legacy reminder request 缺 opaque permit 时 fail-closed', () async {
    final result = await bridge.createCalendarReminder(request);

    expect(result.status, AssistantDeviceActionStatus.unavailable);
    expect(result.deviceObjectId, isEmpty);
  });
}
