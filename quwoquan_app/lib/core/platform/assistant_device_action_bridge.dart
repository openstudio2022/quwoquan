import 'package:flutter/services.dart';

enum AssistantDeviceActionStatus { created, unavailable, denied, failed }

class AssistantCalendarReminderRequest {
  const AssistantCalendarReminderRequest({
    required this.idempotencyKey,
    required this.title,
    required this.startsAt,
    required this.durationMinutes,
    required this.reminderMinutes,
    required this.notes,
  });

  final String idempotencyKey;
  final String title;
  final DateTime startsAt;
  final int durationMinutes;
  final int reminderMinutes;
  final String notes;

  Map<String, Object> toChannelArguments() => <String, Object>{
    'idempotencyKey': idempotencyKey,
    'title': title,
    'startsAtEpochMs': startsAt.millisecondsSinceEpoch,
    'durationMinutes': durationMinutes,
    'reminderMinutes': reminderMinutes,
    'notes': notes,
  };
}

class AssistantDeviceActionResult {
  const AssistantDeviceActionResult({
    required this.status,
    this.deviceObjectId = '',
  });

  final AssistantDeviceActionStatus status;
  final String deviceObjectId;

  bool get created => status == AssistantDeviceActionStatus.created;
}

abstract interface class AssistantDeviceActionBridge {
  Future<AssistantDeviceActionResult> createCalendarReminder(
    AssistantCalendarReminderRequest request,
  );
}

class UnsupportedAssistantDeviceActionBridge
    implements AssistantDeviceActionBridge {
  const UnsupportedAssistantDeviceActionBridge();

  @override
  Future<AssistantDeviceActionResult> createCalendarReminder(
    AssistantCalendarReminderRequest request,
  ) async => const AssistantDeviceActionResult(
    status: AssistantDeviceActionStatus.unavailable,
  );
}

class MethodChannelAssistantDeviceActionBridge
    implements AssistantDeviceActionBridge {
  const MethodChannelAssistantDeviceActionBridge();

  static const MethodChannel _channel = MethodChannel(
    'quwoquan/assistant/device_action',
  );

  @override
  Future<AssistantDeviceActionResult> createCalendarReminder(
    AssistantCalendarReminderRequest request,
  ) async {
    try {
      final raw = await _channel.invokeMapMethod<String, dynamic>(
        'createCalendarReminder',
        request.toChannelArguments(),
      );
      final rawStatus = _trimmedString(raw?['status']);
      final deviceObjectId = _trimmedString(raw?['deviceObjectId']);
      final status = switch (rawStatus) {
        'created' when deviceObjectId.isNotEmpty =>
          AssistantDeviceActionStatus.created,
        'created' => AssistantDeviceActionStatus.failed,
        'denied' => AssistantDeviceActionStatus.denied,
        'unavailable' => AssistantDeviceActionStatus.unavailable,
        _ => AssistantDeviceActionStatus.failed,
      };
      return AssistantDeviceActionResult(
        status: status,
        deviceObjectId: status == AssistantDeviceActionStatus.created
            ? deviceObjectId
            : '',
      );
    } on MissingPluginException {
      return const AssistantDeviceActionResult(
        status: AssistantDeviceActionStatus.unavailable,
      );
    } on PlatformException {
      return const AssistantDeviceActionResult(
        status: AssistantDeviceActionStatus.failed,
      );
    }
  }

  static String _trimmedString(Object? value) {
    return value is String ? value.trim() : '';
  }
}
