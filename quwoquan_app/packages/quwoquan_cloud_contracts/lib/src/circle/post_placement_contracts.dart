import '../operation_request_payload.dart';

final class PlaceCirclePostCommand {
  PlaceCirclePostCommand({
    required String circleId,
    required String postId,
    String? groupId,
  }) : circleId = _required(circleId, 'circleId'),
       postId = _required(postId, 'postId'),
       groupId = _optional(groupId);

  final String circleId;
  final String postId;
  final String? groupId;
}

final class CirclePostPlacementCommandResult {
  const CirclePostPlacementCommandResult({
    required this.placementId,
    required this.version,
    required this.state,
    required this.idempotentReplay,
  });

  final String placementId;
  final int version;
  final String state;
  final bool idempotentReplay;
}

abstract interface class CirclePostPlacementCommandWriter {
  Future<CirclePostPlacementCommandResult> placePost(
    PlaceCirclePostCommand command,
  );
}

CloudOperationRequestPayload encodePlaceCirclePostCommand(
  PlaceCirclePostCommand command,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'circleId': command.circleId},
  body: <String, Object?>{
    'postId': command.postId,
    if (command.groupId != null) 'groupId': command.groupId,
  },
);

CirclePostPlacementCommandResult decodeCirclePostPlacementCommandResult(
  Object? value,
) {
  if (value is! Map) {
    throw const FormatException(
      'CirclePostPlacementCommandResult must be an object',
    );
  }
  final map = value.map((key, item) => MapEntry(key.toString(), item));
  final version = map['version'];
  final replayed = map['idempotentReplay'];
  if (version is! int || version <= 0) {
    throw const FormatException('version must be a positive integer');
  }
  if (replayed is! bool) {
    throw const FormatException('idempotentReplay must be a boolean');
  }
  return CirclePostPlacementCommandResult(
    placementId: _string(map, 'placementId'),
    version: version,
    state: _string(map, 'state'),
    idempotentReplay: replayed,
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
