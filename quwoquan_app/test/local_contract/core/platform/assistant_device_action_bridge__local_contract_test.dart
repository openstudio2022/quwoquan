// spec_ref: specs/feature-tree/assistant-run-learning/assistant-runtime-foundation/spec.md#sit-001
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/platform/assistant_device_action_bridge.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const channel = MethodChannel('quwoquan/assistant/device_action');
  const bridge = MethodChannelAssistantDeviceActionBridge();
  final request = AssistantCalendarReminderRequest(
    idempotencyKey: 'tool-calendar-1',
    title: '西湖集合',
    startsAt: DateTime.parse('2026-08-02T09:00:00+08:00'),
    durationMinutes: 60,
    reminderMinutes: 10,
    notes: '断桥集合',
  );

  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, null);
  });

  test('成功回执必须包含非空设备对象 ID', () async {
    MethodCall? captured;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          captured = call;
          return <String, Object>{
            'status': 'created',
            'deviceObjectId': '  event-42  ',
          };
        });

    final result = await bridge.createCalendarReminder(request);

    expect(result.status, AssistantDeviceActionStatus.created);
    expect(result.deviceObjectId, 'event-42');
    expect(captured?.method, 'createCalendarReminder');
    expect(captured?.arguments, <String, Object>{
      'idempotencyKey': 'tool-calendar-1',
      'title': '西湖集合',
      'startsAtEpochMs': request.startsAt.millisecondsSinceEpoch,
      'durationMinutes': 60,
      'reminderMinutes': 10,
      'notes': '断桥集合',
    });
  });

  test('created 缺设备对象 ID 时 fail-closed 为 failed', () async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (_) async {
          return <String, Object>{'status': 'created', 'deviceObjectId': '  '};
        });

    final result = await bridge.createCalendarReminder(request);

    expect(result.status, AssistantDeviceActionStatus.failed);
    expect(result.deviceObjectId, isEmpty);
  });

  test('失败回执不传播设备对象 ID 且畸形字段不抛出', () async {
    final responses = <Map<String, Object>>[
      <String, Object>{'status': 'denied', 'deviceObjectId': 'must-not-leak'},
      <String, Object>{'status': 7, 'deviceObjectId': <String>[]},
    ];
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (_) async => responses.removeAt(0));

    final denied = await bridge.createCalendarReminder(request);
    final malformed = await bridge.createCalendarReminder(request);

    expect(denied.status, AssistantDeviceActionStatus.denied);
    expect(denied.deviceObjectId, isEmpty);
    expect(malformed.status, AssistantDeviceActionStatus.failed);
    expect(malformed.deviceObjectId, isEmpty);
  });
}
