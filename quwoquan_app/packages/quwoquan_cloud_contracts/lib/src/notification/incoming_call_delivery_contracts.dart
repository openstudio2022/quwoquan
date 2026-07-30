import '../operation_request_payload.dart';
part '../generated/requests/notification/incoming_call_delivery_contracts.requests.g.dart';

abstract interface class IncomingCallPresentationWriter {
  Future<AckIncomingCallPresentationResultDto> acknowledgePresentation(
    AckIncomingCallPresentationCommand command,
  );
}

final class AckIncomingCallPresentationResultDto {
  const AckIncomingCallPresentationResultDto({
    required this.deliveryKey,
    required this.deviceId,
    required this.status,
    required this.raced,
    required this.acknowledgedAt,
  });

  final String deliveryKey;
  final String deviceId;
  final String status;
  final bool raced;
  final DateTime acknowledgedAt;
}

AckIncomingCallPresentationResultDto decodeAckIncomingCallPresentationResult(
  Object? response,
) {
  if (response is! Map<Object?, Object?>) {
    throw const FormatException(
      'Incoming call presentation result must be a JSON object',
    );
  }
  return AckIncomingCallPresentationResultDto(
    deliveryKey: _requiredField(response, 'deliveryKey'),
    deviceId: _requiredField(response, 'deviceId'),
    status: _requiredField(response, 'status'),
    raced: _requiredBool(response, 'raced'),
    acknowledgedAt: _requiredTimestamp(response, 'acknowledgedAt'),
  );
}

String _requiredField(Map<Object?, Object?> value, String field) {
  final raw = value[field];
  if (raw is! String || raw.trim().isEmpty) {
    throw FormatException('$field must be a non-empty string');
  }
  return raw.trim();
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
