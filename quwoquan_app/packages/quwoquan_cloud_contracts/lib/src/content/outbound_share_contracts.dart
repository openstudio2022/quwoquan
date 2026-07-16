import '../operation_request_payload.dart';

/// A confirmed external delivery. Failed or cancelled share attempts cannot be
/// represented by this command and therefore cannot append a business fact.
final class CreateContentOutboundShareCommand {
  CreateContentOutboundShareCommand({
    required String postId,
    required String channel,
    required String destinationKind,
    String? destination,
    required String referralId,
    required String providerReceiptId,
    required DateTime clientConfirmedAt,
  }) : postId = _required(postId, 'postId'),
       channel = _required(channel, 'channel'),
       destinationKind = _required(destinationKind, 'destinationKind'),
       destination = _optional(destination),
       referralId = _required(referralId, 'referralId'),
       providerReceiptId = _required(providerReceiptId, 'providerReceiptId'),
       clientConfirmedAt = clientConfirmedAt.toUtc();

  final String postId;
  final String channel;
  final String destinationKind;
  final String? destination;
  final String referralId;
  final String providerReceiptId;
  final DateTime clientConfirmedAt;
}

final class ContentOutboundShareFactResult {
  const ContentOutboundShareFactResult({
    required this.eventId,
    required this.postId,
    required this.channel,
    required this.referralId,
    required this.occurredAt,
    required this.replayed,
  });

  final String eventId;
  final String postId;
  final String channel;
  final String referralId;
  final DateTime occurredAt;
  final bool replayed;
}

abstract interface class ContentOutboundShareAppendWriter {
  Future<ContentOutboundShareFactResult> appendOutboundShare(
    CreateContentOutboundShareCommand command,
  );
}

CloudOperationRequestPayload encodeCreateContentOutboundShareCommand(
  CreateContentOutboundShareCommand command,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'postId': command.postId},
  body: <String, Object?>{
    'channel': command.channel,
    'destinationKind': command.destinationKind,
    if (command.destination != null) 'destination': command.destination,
    'referralId': command.referralId,
    'deliverySucceeded': true,
    'providerReceiptId': command.providerReceiptId,
    'clientConfirmedAt': command.clientConfirmedAt.toIso8601String(),
  },
);

ContentOutboundShareFactResult decodeContentOutboundShareFactResult(
  Object? value,
) {
  if (value is! Map) {
    throw const FormatException(
      'ContentOutboundShareFactResult must be an object',
    );
  }
  final map = value.map((key, item) => MapEntry(key.toString(), item));
  final occurredAt = DateTime.tryParse(_string(map, 'occurredAt'));
  final replayed = map['replayed'];
  if (occurredAt == null)
    throw const FormatException('occurredAt must be RFC3339');
  if (replayed is! bool)
    throw const FormatException('replayed must be a boolean');
  return ContentOutboundShareFactResult(
    eventId: _string(map, 'eventId'),
    postId: _string(map, 'postId'),
    channel: _string(map, 'channel'),
    referralId: _string(map, 'referralId'),
    occurredAt: occurredAt.toUtc(),
    replayed: replayed,
  );
}

String _string(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! String || value.trim().isEmpty) {
    throw FormatException('$key must be a non-empty string');
  }
  return value.trim();
}

String _required(String value, String name) {
  final normalized = value.trim();
  if (normalized.isEmpty) throw ArgumentError.value(value, name, 'required');
  return normalized;
}

String? _optional(String? value) {
  final normalized = value?.trim() ?? '';
  return normalized.isEmpty ? null : normalized;
}
