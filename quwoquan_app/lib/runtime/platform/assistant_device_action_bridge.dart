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

/// Pre-M3 adapter retained only so the assistant consumer fails closed while it
/// migrates to DeviceCalendarBridge with an opaque permit.
///
/// This request shape cannot prove installation/device/capability/input digest
/// binding, so it must never reach the native calendar channel.
class MethodChannelAssistantDeviceActionBridge
    implements AssistantDeviceActionBridge {
  const MethodChannelAssistantDeviceActionBridge();

  @override
  Future<AssistantDeviceActionResult> createCalendarReminder(
    AssistantCalendarReminderRequest request,
  ) async => const AssistantDeviceActionResult(
    status: AssistantDeviceActionStatus.unavailable,
  );
}
