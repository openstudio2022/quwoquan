import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter/services.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

enum DeviceCalendarAvailability { available, unavailable }

enum DeviceCalendarPermission {
  granted,
  requestable,
  denied,
  restricted,
  unavailable,
}

enum DeviceCalendarOperation { create, update, delete }

enum DeviceCalendarFailureReason {
  unavailable,
  permissionDenied,
  permissionRestricted,
  noWritableCalendar,
  eventNotFound,
  invalidRequest,
  invalidNativeResponse,
  idempotencyConflict,
  permitExpired,
  permitBindingMismatch,
  permitVerifierUnavailable,
  systemError,
}

extension on DeviceCalendarOperation {
  String get capability => 'calendar.event.$name';

  String get channelMethod => '${name}Event';
}

final class DeviceCalendarCapabilityProbe {
  const DeviceCalendarCapabilityProbe({
    required this.availability,
    required this.permission,
    required this.hasWritableCalendar,
    this.failure,
  });

  final DeviceCalendarAvailability availability;
  final DeviceCalendarPermission permission;
  final bool hasWritableCalendar;
  final RuntimeFailure? failure;

  bool get canMutate =>
      availability == DeviceCalendarAvailability.available &&
      permission == DeviceCalendarPermission.granted &&
      hasWritableCalendar;
}

final class DeviceCalendarLocalBinding {
  const DeviceCalendarLocalBinding({
    required this.installationId,
    required this.deviceId,
  });

  const DeviceCalendarLocalBinding.unavailable()
    : installationId = '',
      deviceId = '';

  final String installationId;
  final String deviceId;

  bool get isComplete =>
      installationId.trim().isNotEmpty && deviceId.trim().isNotEmpty;
}

final class DeviceCalendarPermitVerification {
  const DeviceCalendarPermitVerification({
    required this.permitId,
    required this.installationId,
    required this.deviceId,
    required this.capability,
    required this.inputDigest,
    required this.idempotencyKey,
    required this.verifiedAt,
  });

  final String permitId;
  final String installationId;
  final String deviceId;
  final String capability;
  final String inputDigest;
  final String idempotencyKey;
  final DateTime verifiedAt;
}

/// Claims returned only after the opaque permit has been authenticated.
///
/// The bridge compares every returned claim with locally derived expectations.
/// A verifier cannot grant a mutation by returning a bare boolean.
final class DeviceCalendarVerifiedPermit {
  const DeviceCalendarVerifiedPermit({
    required this.installationId,
    required this.deviceId,
    required this.capability,
    required this.inputDigest,
    required this.idempotencyKey,
    required this.expiresAt,
  });

  final String installationId;
  final String deviceId;
  final String capability;
  final String inputDigest;
  final String idempotencyKey;
  final DateTime expiresAt;
}

abstract interface class DeviceCalendarPermitVerifier {
  Future<DeviceCalendarVerifiedPermit> verify(
    DeviceCalendarPermitVerification verification,
  );
}

/// Production verifier until assistant auth exposes its generated verifier.
///
/// Deliberately does not parse, trust, or forward the opaque permit. Replacing
/// this implementation requires generated authentication verification, not an
/// environment switch or an app-local secret.
final class FailClosedDeviceCalendarPermitVerifier
    implements DeviceCalendarPermitVerifier {
  const FailClosedDeviceCalendarPermitVerifier();

  @override
  Future<DeviceCalendarVerifiedPermit> verify(
    DeviceCalendarPermitVerification verification,
  ) {
    throw DeviceCalendarException.forReason(
      DeviceCalendarFailureReason.permitVerifierUnavailable,
    );
  }
}

sealed class DeviceCalendarPermitBoundRequest {
  const DeviceCalendarPermitBoundRequest({
    required this.permitId,
    required this.idempotencyKey,
  });

  final String permitId;
  final String idempotencyKey;

  Map<String, Object?> canonicalInput(DeviceCalendarOperation operation);

  Map<String, Object?> channelArguments(DeviceCalendarOperation operation) {
    final canonical = canonicalInput(operation);
    return <String, Object?>{
      ...canonical,
      'inputDigest': deviceCalendarInputDigest(canonical),
    };
  }

  void validateFor(DeviceCalendarOperation operation) {
    if (permitId.trim().isEmpty ||
        idempotencyKey.trim().isEmpty ||
        idempotencyKey.trim().length > 128) {
      throw DeviceCalendarException.forReason(
        DeviceCalendarFailureReason.invalidRequest,
        operation: operation,
      );
    }
  }
}

final class DeviceCalendarCreateRequest
    extends DeviceCalendarPermitBoundRequest {
  DeviceCalendarCreateRequest({
    required super.permitId,
    required super.idempotencyKey,
    this.calendarId,
    required this.title,
    required this.start,
    required this.end,
    required this.timezone,
    this.location = '',
    this.notes = '',
  });

  final String? calendarId;
  final String title;
  final DateTime start;
  final DateTime end;
  final String timezone;
  final String location;
  final String notes;

  @override
  Map<String, Object?> canonicalInput(DeviceCalendarOperation operation) =>
      _eventCanonicalInput(
        operation: operation,
        idempotencyKey: idempotencyKey,
        calendarId: calendarId,
        deviceEventId: null,
        title: title,
        start: start,
        end: end,
        timezone: timezone,
        location: location,
        notes: notes,
      );

  @override
  void validateFor(DeviceCalendarOperation operation) {
    super.validateFor(operation);
    _validateEventFields(
      operation: operation,
      calendarId: calendarId,
      title: title,
      start: start,
      end: end,
      timezone: timezone,
      location: location,
      notes: notes,
    );
  }
}

final class DeviceCalendarUpdateRequest
    extends DeviceCalendarPermitBoundRequest {
  DeviceCalendarUpdateRequest({
    required super.permitId,
    required super.idempotencyKey,
    required this.deviceEventId,
    this.calendarId,
    required this.title,
    required this.start,
    required this.end,
    required this.timezone,
    this.location = '',
    this.notes = '',
  });

  final String deviceEventId;
  final String? calendarId;
  final String title;
  final DateTime start;
  final DateTime end;
  final String timezone;
  final String location;
  final String notes;

  @override
  Map<String, Object?> canonicalInput(DeviceCalendarOperation operation) =>
      _eventCanonicalInput(
        operation: operation,
        idempotencyKey: idempotencyKey,
        calendarId: calendarId,
        deviceEventId: deviceEventId,
        title: title,
        start: start,
        end: end,
        timezone: timezone,
        location: location,
        notes: notes,
      );

  @override
  void validateFor(DeviceCalendarOperation operation) {
    super.validateFor(operation);
    if (deviceEventId.trim().isEmpty || deviceEventId.trim().length > 512) {
      throw DeviceCalendarException.forReason(
        DeviceCalendarFailureReason.invalidRequest,
        operation: operation,
      );
    }
    _validateEventFields(
      operation: operation,
      calendarId: calendarId,
      title: title,
      start: start,
      end: end,
      timezone: timezone,
      location: location,
      notes: notes,
    );
  }
}

final class DeviceCalendarDeleteRequest
    extends DeviceCalendarPermitBoundRequest {
  DeviceCalendarDeleteRequest({
    required super.permitId,
    required super.idempotencyKey,
    required this.deviceEventId,
  });

  final String deviceEventId;

  @override
  Map<String, Object?> canonicalInput(DeviceCalendarOperation operation) =>
      <String, Object?>{
        'operation': operation.name,
        'idempotencyKey': idempotencyKey.trim(),
        'deviceEventId': deviceEventId.trim(),
      };

  @override
  void validateFor(DeviceCalendarOperation operation) {
    super.validateFor(operation);
    if (deviceEventId.trim().isEmpty || deviceEventId.trim().length > 512) {
      throw DeviceCalendarException.forReason(
        DeviceCalendarFailureReason.invalidRequest,
        operation: operation,
      );
    }
  }
}

final class DeviceCalendarReceipt {
  const DeviceCalendarReceipt({
    required this.operation,
    required this.deviceEventId,
    required this.receiptDigest,
    required this.replayed,
  });

  final DeviceCalendarOperation operation;
  final String deviceEventId;
  final String receiptDigest;
  final bool replayed;
}

abstract interface class DeviceCalendarBridge {
  Future<DeviceCalendarCapabilityProbe> probe();

  Future<DeviceCalendarReceipt> create(DeviceCalendarCreateRequest request);

  Future<DeviceCalendarReceipt> update(DeviceCalendarUpdateRequest request);

  Future<DeviceCalendarReceipt> delete(DeviceCalendarDeleteRequest request);
}

final class UnsupportedDeviceCalendarBridge implements DeviceCalendarBridge {
  const UnsupportedDeviceCalendarBridge();

  @override
  Future<DeviceCalendarCapabilityProbe> probe() async {
    return DeviceCalendarCapabilityProbe(
      availability: DeviceCalendarAvailability.unavailable,
      permission: DeviceCalendarPermission.unavailable,
      hasWritableCalendar: false,
      failure: DeviceCalendarException.failureFor(
        DeviceCalendarFailureReason.unavailable,
      ),
    );
  }

  @override
  Future<DeviceCalendarReceipt> create(DeviceCalendarCreateRequest request) =>
      _unavailable(DeviceCalendarOperation.create);

  @override
  Future<DeviceCalendarReceipt> update(DeviceCalendarUpdateRequest request) =>
      _unavailable(DeviceCalendarOperation.update);

  @override
  Future<DeviceCalendarReceipt> delete(DeviceCalendarDeleteRequest request) =>
      _unavailable(DeviceCalendarOperation.delete);

  Future<DeviceCalendarReceipt> _unavailable(
    DeviceCalendarOperation operation,
  ) {
    return Future<DeviceCalendarReceipt>.error(
      DeviceCalendarException.forReason(
        DeviceCalendarFailureReason.unavailable,
        operation: operation,
      ),
    );
  }
}

typedef DeviceCalendarClock = DateTime Function();

final class MethodChannelDeviceCalendarBridge implements DeviceCalendarBridge {
  MethodChannelDeviceCalendarBridge({
    required this.permitVerifier,
    required this.localBinding,
    this.channel = const MethodChannel('quwoquan/assistant/device_action'),
    this.clock = _systemUtcNow,
  });

  final DeviceCalendarPermitVerifier permitVerifier;
  final DeviceCalendarLocalBinding localBinding;
  final MethodChannel channel;
  final DeviceCalendarClock clock;

  final Map<String, String> _acceptedDigests = <String, String>{};
  final Map<String, DeviceCalendarReceipt> _completed =
      <String, DeviceCalendarReceipt>{};
  final Map<String, Future<DeviceCalendarReceipt>> _inFlight =
      <String, Future<DeviceCalendarReceipt>>{};

  @override
  Future<DeviceCalendarCapabilityProbe> probe() async {
    try {
      final raw = await channel.invokeMapMethod<String, dynamic>('probe');
      if (raw == null) {
        return _failedProbe(DeviceCalendarFailureReason.invalidNativeResponse);
      }
      final availability = switch (_string(raw['availability'])) {
        'available' => DeviceCalendarAvailability.available,
        _ => DeviceCalendarAvailability.unavailable,
      };
      final permission = switch (_string(raw['permission'])) {
        'granted' => DeviceCalendarPermission.granted,
        'requestable' => DeviceCalendarPermission.requestable,
        'denied' => DeviceCalendarPermission.denied,
        'restricted' => DeviceCalendarPermission.restricted,
        _ => DeviceCalendarPermission.unavailable,
      };
      final hasWritableCalendar = raw['hasWritableCalendar'] == true;
      final reason = _probeFailureReason(
        availability: availability,
        permission: permission,
        hasWritableCalendar: hasWritableCalendar,
      );
      return DeviceCalendarCapabilityProbe(
        availability: availability,
        permission: permission,
        hasWritableCalendar: hasWritableCalendar,
        failure: reason == null
            ? null
            : DeviceCalendarException.failureFor(reason),
      );
    } on MissingPluginException {
      return _failedProbe(DeviceCalendarFailureReason.unavailable);
    } on PlatformException {
      return _failedProbe(DeviceCalendarFailureReason.systemError);
    } on Object {
      return _failedProbe(DeviceCalendarFailureReason.invalidNativeResponse);
    }
  }

  @override
  Future<DeviceCalendarReceipt> create(DeviceCalendarCreateRequest request) =>
      _mutate(DeviceCalendarOperation.create, request);

  @override
  Future<DeviceCalendarReceipt> update(DeviceCalendarUpdateRequest request) =>
      _mutate(DeviceCalendarOperation.update, request);

  @override
  Future<DeviceCalendarReceipt> delete(DeviceCalendarDeleteRequest request) =>
      _mutate(DeviceCalendarOperation.delete, request);

  Future<DeviceCalendarReceipt> _mutate(
    DeviceCalendarOperation operation,
    DeviceCalendarPermitBoundRequest request,
  ) async {
    request.validateFor(operation);
    final channelArguments = request.channelArguments(operation);
    final inputDigest = channelArguments['inputDigest']! as String;
    await _verifyPermit(
      operation: operation,
      request: request,
      inputDigest: inputDigest,
    );

    final replayKey = request.idempotencyKey.trim();
    final acceptedDigest = _acceptedDigests[replayKey];
    if (acceptedDigest != null && acceptedDigest != inputDigest) {
      throw DeviceCalendarException.forReason(
        DeviceCalendarFailureReason.idempotencyConflict,
        operation: operation,
      );
    }
    _acceptedDigests[replayKey] = inputDigest;

    final completed = _completed[replayKey];
    if (completed != null) {
      return DeviceCalendarReceipt(
        operation: completed.operation,
        deviceEventId: completed.deviceEventId,
        receiptDigest: completed.receiptDigest,
        replayed: true,
      );
    }
    final inFlight = _inFlight[replayKey];
    if (inFlight != null) {
      final receipt = await inFlight;
      return DeviceCalendarReceipt(
        operation: receipt.operation,
        deviceEventId: receipt.deviceEventId,
        receiptDigest: receipt.receiptDigest,
        replayed: true,
      );
    }

    final future = _invokeMutation(
      operation: operation,
      channelArguments: channelArguments,
    );
    _inFlight[replayKey] = future;
    try {
      final receipt = await future;
      _completed[replayKey] = receipt;
      return receipt;
    } finally {
      _inFlight.remove(replayKey);
    }
  }

  Future<void> _verifyPermit({
    required DeviceCalendarOperation operation,
    required DeviceCalendarPermitBoundRequest request,
    required String inputDigest,
  }) async {
    if (!localBinding.isComplete) {
      throw DeviceCalendarException.forReason(
        DeviceCalendarFailureReason.permitVerifierUnavailable,
        operation: operation,
      );
    }
    final now = clock().toUtc();
    final verification = DeviceCalendarPermitVerification(
      permitId: request.permitId,
      installationId: localBinding.installationId.trim(),
      deviceId: localBinding.deviceId.trim(),
      capability: operation.capability,
      inputDigest: inputDigest,
      idempotencyKey: request.idempotencyKey.trim(),
      verifiedAt: now,
    );
    final DeviceCalendarVerifiedPermit permit;
    try {
      permit = await permitVerifier.verify(verification);
    } on DeviceCalendarException {
      rethrow;
    } on Object {
      throw DeviceCalendarException.forReason(
        DeviceCalendarFailureReason.permitVerifierUnavailable,
        operation: operation,
      );
    }
    if (!permit.expiresAt.toUtc().isAfter(now)) {
      throw DeviceCalendarException.forReason(
        DeviceCalendarFailureReason.permitExpired,
        operation: operation,
      );
    }
    if (permit.installationId.trim() != verification.installationId ||
        permit.deviceId.trim() != verification.deviceId ||
        permit.capability.trim() != verification.capability ||
        permit.inputDigest.trim() != verification.inputDigest ||
        permit.idempotencyKey.trim() != verification.idempotencyKey) {
      throw DeviceCalendarException.forReason(
        DeviceCalendarFailureReason.permitBindingMismatch,
        operation: operation,
      );
    }
  }

  Future<DeviceCalendarReceipt> _invokeMutation({
    required DeviceCalendarOperation operation,
    required Map<String, Object?> channelArguments,
  }) async {
    final Map<String, dynamic>? raw;
    try {
      raw = await channel.invokeMapMethod<String, dynamic>(
        operation.channelMethod,
        channelArguments,
      );
    } on MissingPluginException {
      throw DeviceCalendarException.forReason(
        DeviceCalendarFailureReason.unavailable,
        operation: operation,
      );
    } on PlatformException catch (error) {
      throw DeviceCalendarException.forReason(
        _failureReasonFromWire(error.code),
        operation: operation,
      );
    } on Object {
      throw DeviceCalendarException.forReason(
        DeviceCalendarFailureReason.systemError,
        operation: operation,
      );
    }
    final status = _string(raw?['status']);
    if (status != 'succeeded') {
      throw DeviceCalendarException.forReason(
        _failureReasonFromWire(status),
        operation: operation,
      );
    }
    final deviceEventId = _string(raw?['deviceEventId']);
    final receiptDigest = _string(raw?['receiptDigest']);
    if (deviceEventId.isEmpty || !_canonicalDigest.hasMatch(receiptDigest)) {
      throw DeviceCalendarException.forReason(
        DeviceCalendarFailureReason.invalidNativeResponse,
        operation: operation,
      );
    }
    return DeviceCalendarReceipt(
      operation: operation,
      deviceEventId: deviceEventId,
      receiptDigest: receiptDigest,
      replayed: raw?['replayed'] == true,
    );
  }
}

final class DeviceCalendarException implements Exception {
  const DeviceCalendarException({
    required this.reason,
    required this.runtimeFailure,
  });

  factory DeviceCalendarException.forReason(
    DeviceCalendarFailureReason reason, {
    DeviceCalendarOperation? operation,
  }) {
    return DeviceCalendarException(
      reason: reason,
      runtimeFailure: failureFor(reason, operation: operation),
    );
  }

  final DeviceCalendarFailureReason reason;
  final RuntimeFailure runtimeFailure;

  static RuntimeFailure failureFor(
    DeviceCalendarFailureReason reason, {
    DeviceCalendarOperation? operation,
  }) {
    final permission =
        reason == DeviceCalendarFailureReason.permissionDenied ||
        reason == DeviceCalendarFailureReason.permissionRestricted;
    final permit =
        reason == DeviceCalendarFailureReason.permitExpired ||
        reason == DeviceCalendarFailureReason.permitBindingMismatch ||
        reason == DeviceCalendarFailureReason.permitVerifierUnavailable;
    final unavailable =
        reason == DeviceCalendarFailureReason.unavailable ||
        reason == DeviceCalendarFailureReason.noWritableCalendar ||
        reason == DeviceCalendarFailureReason.permitVerifierUnavailable;
    final code = switch (reason) {
      DeviceCalendarFailureReason.permissionDenied ||
      DeviceCalendarFailureReason.permissionRestricted =>
        RuntimeFailureCodes.appUserPermissionRequired,
      DeviceCalendarFailureReason.eventNotFound =>
        RuntimeFailureCodes.appUserNotFound,
      DeviceCalendarFailureReason.invalidRequest ||
      DeviceCalendarFailureReason.invalidNativeResponse ||
      DeviceCalendarFailureReason.idempotencyConflict =>
        RuntimeFailureCodes.appContractInvalidResponse,
      DeviceCalendarFailureReason.permitExpired ||
      DeviceCalendarFailureReason.permitBindingMismatch =>
        RuntimeFailureCodes.appUserForbidden,
      _ => RuntimeFailureCodes.appSystemUnknownError,
    };
    return RuntimeFailure(
      code: code,
      semanticReason: 'device_calendar_${reason.name}',
      origin: permission
          ? RuntimeFailureOrigin.user
          : unavailable
          ? RuntimeFailureOrigin.environment
          : RuntimeFailureOrigin.localClient,
      kind: permission
          ? RuntimeFailureKind.permission
          : permit
          ? RuntimeFailureKind.auth
          : reason == DeviceCalendarFailureReason.eventNotFound
          ? RuntimeFailureKind.notFound
          : unavailable
          ? RuntimeFailureKind.unavailable
          : reason == DeviceCalendarFailureReason.invalidRequest ||
                reason == DeviceCalendarFailureReason.invalidNativeResponse ||
                reason == DeviceCalendarFailureReason.idempotencyConflict
          ? RuntimeFailureKind.contract
          : RuntimeFailureKind.internal,
      nature: permission
          ? RuntimeFailureNature.requiresPermission
          : reason == DeviceCalendarFailureReason.systemError
          ? RuntimeFailureNature.transient
          : RuntimeFailureNature.permanent,
      location: const RuntimeFailureLocation(
        businessObject: 'runtime.device_calendar',
        functionModule: 'device_calendar_bridge',
      ),
      context: operation == null
          ? const RuntimeFailureContext()
          : RuntimeFailureContext(
              attributes: <RuntimeContextAttribute>[
                RuntimeContextAttribute(
                  key: 'operation',
                  value: operation.name,
                ),
              ],
            ),
    );
  }

  @override
  String toString() => 'DeviceCalendarException(${reason.name})';
}

Map<String, Object?> _eventCanonicalInput({
  required DeviceCalendarOperation operation,
  required String idempotencyKey,
  required String? calendarId,
  required String? deviceEventId,
  required String title,
  required DateTime start,
  required DateTime end,
  required String timezone,
  required String location,
  required String notes,
}) {
  return <String, Object?>{
    'operation': operation.name,
    'idempotencyKey': idempotencyKey.trim(),
    'calendarId': calendarId?.trim() ?? '',
    if (deviceEventId != null) 'deviceEventId': deviceEventId.trim(),
    'title': title.trim(),
    'startEpochMs': start.toUtc().millisecondsSinceEpoch,
    'endEpochMs': end.toUtc().millisecondsSinceEpoch,
    'timezone': timezone.trim(),
    'location': location.trim(),
    'notes': notes.trim(),
  };
}

void _validateEventFields({
  required DeviceCalendarOperation operation,
  required String? calendarId,
  required String title,
  required DateTime start,
  required DateTime end,
  required String timezone,
  required String location,
  required String notes,
}) {
  if (title.trim().isEmpty ||
      title.trim().length > 200 ||
      !end.toUtc().isAfter(start.toUtc()) ||
      timezone.trim().isEmpty ||
      timezone.trim().length > 100 ||
      (calendarId?.trim().length ?? 0) > 512 ||
      location.trim().length > 500 ||
      notes.trim().length > 2000) {
    throw DeviceCalendarException.forReason(
      DeviceCalendarFailureReason.invalidRequest,
      operation: operation,
    );
  }
}

String deviceCalendarInputDigest(Map<String, Object?> canonicalInput) {
  final encoded = jsonEncode(canonicalInput);
  return 'sha256:${sha256.convert(utf8.encode(encoded))}';
}

DeviceCalendarFailureReason? _probeFailureReason({
  required DeviceCalendarAvailability availability,
  required DeviceCalendarPermission permission,
  required bool hasWritableCalendar,
}) {
  if (availability == DeviceCalendarAvailability.unavailable) {
    return DeviceCalendarFailureReason.unavailable;
  }
  return switch (permission) {
    DeviceCalendarPermission.denied =>
      DeviceCalendarFailureReason.permissionDenied,
    DeviceCalendarPermission.restricted =>
      DeviceCalendarFailureReason.permissionRestricted,
    DeviceCalendarPermission.granted when !hasWritableCalendar =>
      DeviceCalendarFailureReason.noWritableCalendar,
    _ => null,
  };
}

DeviceCalendarCapabilityProbe _failedProbe(DeviceCalendarFailureReason reason) {
  return DeviceCalendarCapabilityProbe(
    availability: DeviceCalendarAvailability.unavailable,
    permission: DeviceCalendarPermission.unavailable,
    hasWritableCalendar: false,
    failure: DeviceCalendarException.failureFor(reason),
  );
}

DeviceCalendarFailureReason _failureReasonFromWire(String raw) {
  return switch (raw.trim()) {
    'permission_denied' => DeviceCalendarFailureReason.permissionDenied,
    'permission_restricted' => DeviceCalendarFailureReason.permissionRestricted,
    'no_calendar' => DeviceCalendarFailureReason.noWritableCalendar,
    'event_not_found' => DeviceCalendarFailureReason.eventNotFound,
    'invalid_request' => DeviceCalendarFailureReason.invalidRequest,
    'idempotency_conflict' => DeviceCalendarFailureReason.idempotencyConflict,
    'unavailable' ||
    'missing_plugin' => DeviceCalendarFailureReason.unavailable,
    'system_error' => DeviceCalendarFailureReason.systemError,
    _ => DeviceCalendarFailureReason.invalidNativeResponse,
  };
}

String _string(Object? value) => value is String ? value.trim() : '';

DateTime _systemUtcNow() => DateTime.now().toUtc();

final RegExp _canonicalDigest = RegExp(r'^sha256:[0-9a-f]{64}$');
