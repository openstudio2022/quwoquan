import '../operation_request_payload.dart';
part '../generated/requests/user/device_registration_contracts.requests.g.dart';

enum DevicePushEndpointKind {
  apnsVoip('apns_voip'),
  fcm('fcm');

  const DevicePushEndpointKind(this.wireValue);

  final String wireValue;
}

abstract interface class DeviceRegistrationCommandWriter {
  Future<DevicePushEndpointCommandResultDto> upsertPushEndpoint(
    DevicePushEndpointUpsertCommand command,
  );

  Future<DevicePushEndpointCommandResultDto> removePushEndpoint(
    DevicePushEndpointRemoveCommand command,
  );
}

final class DevicePushEndpointCommandResultDto {
  const DevicePushEndpointCommandResultDto({
    required this.endpointRef,
    required this.deviceId,
    required this.endpointKind,
    required this.status,
    required this.version,
    required this.aggregateVersion,
    required this.idempotentReplay,
    required this.updatedAt,
  });

  final String endpointRef;
  final String deviceId;
  final DevicePushEndpointKind endpointKind;
  final String status;
  final int version;
  final int aggregateVersion;
  final bool idempotentReplay;
  final DateTime updatedAt;
}

DevicePushEndpointCommandResultDto decodeDevicePushEndpointCommandResult(
  Object? response,
) {
  if (response is! Map<Object?, Object?>) {
    throw const FormatException(
      'Device push endpoint result must be a JSON object',
    );
  }
  final endpointKind = _requiredField(response, 'endpointKind');
  return DevicePushEndpointCommandResultDto(
    endpointRef: _requiredField(response, 'endpointRef'),
    deviceId: _requiredField(response, 'deviceId'),
    endpointKind: switch (endpointKind) {
      'apns_voip' => DevicePushEndpointKind.apnsVoip,
      'fcm' => DevicePushEndpointKind.fcm,
      _ => throw FormatException(
        'Unsupported device push endpoint kind: $endpointKind',
      ),
    },
    status: _requiredField(response, 'status'),
    version: _requiredInt(response, 'version'),
    aggregateVersion: _requiredInt(response, 'aggregateVersion'),
    idempotentReplay: _requiredBool(response, 'idempotentReplay'),
    updatedAt: _requiredTimestamp(response, 'updatedAt'),
  );
}

String _requiredField(Map<Object?, Object?> value, String field) {
  final raw = value[field];
  if (raw is! String || raw.trim().isEmpty) {
    throw FormatException('$field must be a non-empty string');
  }
  return raw.trim();
}

int _requiredInt(Map<Object?, Object?> value, String field) {
  final raw = value[field];
  if (raw is! num) {
    throw FormatException('$field must be an integer');
  }
  return raw.toInt();
}

bool _requiredBool(Map<Object?, Object?> value, String field) {
  final raw = value[field];
  if (raw is! bool) {
    throw FormatException('$field must be a boolean');
  }
  return raw;
}

DateTime _requiredTimestamp(Map<Object?, Object?> value, String field) {
  final raw = value[field];
  final parsed = raw is String ? DateTime.tryParse(raw) : null;
  if (parsed == null) {
    throw FormatException('$field must be an RFC3339 timestamp');
  }
  return parsed.toUtc();
}
