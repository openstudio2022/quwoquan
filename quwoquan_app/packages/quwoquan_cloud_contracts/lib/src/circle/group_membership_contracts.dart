import '../operation_request_payload.dart';

enum CircleGroupMembershipRole { owner, manager, member }

enum CircleGroupMembershipState { pending, active, rejected, left, removed }

final class ApplyCircleGroupMembershipCommand {
  ApplyCircleGroupMembershipCommand({
    required String circleId,
    required String groupId,
  }) : circleId = _required(circleId, 'circleId'),
       groupId = _required(groupId, 'groupId');
  final String circleId;
  final String groupId;
}

final class MyCircleGroupMembershipQuery {
  MyCircleGroupMembershipQuery({
    required String circleId,
    required String groupId,
  }) : circleId = _required(circleId, 'circleId'),
       groupId = _required(groupId, 'groupId');
  final String circleId;
  final String groupId;
}

final class CircleGroupMembershipListQuery {
  CircleGroupMembershipListQuery({
    required String circleId,
    required String groupId,
    this.state,
    this.cursor,
    this.limit = 20,
  }) : circleId = _required(circleId, 'circleId'),
       groupId = _required(groupId, 'groupId') {
    _limit(limit);
  }
  final String circleId;
  final String groupId;
  final CircleGroupMembershipState? state;
  final String? cursor;
  final int limit;
}

final class LeaveCircleGroupMembershipCommand {
  LeaveCircleGroupMembershipCommand({
    required String circleId,
    required String groupId,
  }) : circleId = _required(circleId, 'circleId'),
       groupId = _required(groupId, 'groupId');
  final String circleId;
  final String groupId;
}

final class DecideCircleGroupMembershipCommand {
  DecideCircleGroupMembershipCommand({
    required String circleId,
    required String groupId,
    required String personaId,
  }) : circleId = _required(circleId, 'circleId'),
       groupId = _required(groupId, 'groupId'),
       personaId = _required(personaId, 'personaId');
  final String circleId;
  final String groupId;
  final String personaId;
}

final class RemoveCircleGroupMembershipCommand {
  RemoveCircleGroupMembershipCommand({
    required String circleId,
    required String groupId,
    required String personaId,
  }) : circleId = _required(circleId, 'circleId'),
       groupId = _required(groupId, 'groupId'),
       personaId = _required(personaId, 'personaId');
  final String circleId;
  final String groupId;
  final String personaId;
}

final class UpdateCircleGroupMembershipRoleCommand {
  UpdateCircleGroupMembershipRoleCommand({
    required String circleId,
    required String groupId,
    required String personaId,
    required this.role,
  }) : circleId = _required(circleId, 'circleId'),
       groupId = _required(groupId, 'groupId'),
       personaId = _required(personaId, 'personaId') {
    if (role == CircleGroupMembershipRole.owner) {
      throw ArgumentError.value(
        role,
        'role',
        'owner transfer is not a role update',
      );
    }
  }
  final String circleId;
  final String groupId;
  final String personaId;
  final CircleGroupMembershipRole role;
}

final class CircleGroupMembershipCommandResult {
  const CircleGroupMembershipCommandResult({
    required this.membershipId,
    required this.version,
    required this.role,
    required this.state,
    required this.idempotentReplay,
  });
  final String membershipId;
  final int version;
  final CircleGroupMembershipRole role;
  final CircleGroupMembershipState state;
  final bool idempotentReplay;
}

final class CircleGroupMembershipSlice {
  const CircleGroupMembershipSlice({
    required this.membershipId,
    required this.version,
    required this.groupId,
    required this.circleId,
    required this.personaId,
    required this.role,
    required this.state,
    required this.joinedAt,
    required this.leftAt,
    required this.decidedAt,
    required this.createdAt,
    required this.updatedAt,
  });
  final String membershipId;
  final int version;
  final String groupId;
  final String circleId;
  final String personaId;
  final CircleGroupMembershipRole role;
  final CircleGroupMembershipState state;
  final DateTime? joinedAt;
  final DateTime? leftAt;
  final DateTime? decidedAt;
  final DateTime createdAt;
  final DateTime updatedAt;
}

final class CircleGroupMembershipPageSlice {
  const CircleGroupMembershipPageSlice({required this.items, this.nextCursor});
  final List<CircleGroupMembershipSlice> items;
  final String? nextCursor;
}

abstract interface class CircleGroupMembershipCommandWriter {
  Future<CircleGroupMembershipCommandResult> apply(
    ApplyCircleGroupMembershipCommand command,
  );
  Future<CircleGroupMembershipCommandResult> leave(
    LeaveCircleGroupMembershipCommand command,
  );
  Future<CircleGroupMembershipCommandResult> approve(
    DecideCircleGroupMembershipCommand command,
  );
  Future<CircleGroupMembershipCommandResult> reject(
    DecideCircleGroupMembershipCommand command,
  );
  Future<CircleGroupMembershipCommandResult> remove(
    RemoveCircleGroupMembershipCommand command,
  );
  Future<CircleGroupMembershipCommandResult> updateRole(
    UpdateCircleGroupMembershipRoleCommand command,
  );
}

abstract interface class CircleGroupMembershipQueryReader {
  Future<CircleGroupMembershipSlice> getMy(MyCircleGroupMembershipQuery query);
  Future<CircleGroupMembershipPageSlice> list(
    CircleGroupMembershipListQuery query,
  );
}

CloudOperationRequestPayload encodeApplyCircleGroupMembershipCommand(
  ApplyCircleGroupMembershipCommand command,
) => _path(command.circleId, command.groupId);

CloudOperationRequestPayload encodeMyCircleGroupMembershipQuery(
  MyCircleGroupMembershipQuery query,
) => _path(query.circleId, query.groupId);

CloudOperationRequestPayload encodeCircleGroupMembershipListQuery(
  CircleGroupMembershipListQuery query,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{
    'circleId': query.circleId,
    'groupId': query.groupId,
  },
  queryParameters: <String, String>{
    if (query.state != null) 'state': query.state!.name,
    if (query.cursor != null) 'cursor': query.cursor!,
    'limit': query.limit.toString(),
  },
);

CloudOperationRequestPayload encodeLeaveCircleGroupMembershipCommand(
  LeaveCircleGroupMembershipCommand command,
) => _path(command.circleId, command.groupId);

CloudOperationRequestPayload encodeApproveCircleGroupMembershipCommand(
  DecideCircleGroupMembershipCommand command,
) => _targetPath(command.circleId, command.groupId, command.personaId);

CloudOperationRequestPayload encodeRejectCircleGroupMembershipCommand(
  DecideCircleGroupMembershipCommand command,
) => _targetPath(command.circleId, command.groupId, command.personaId);

CloudOperationRequestPayload encodeRemoveCircleGroupMembershipCommand(
  RemoveCircleGroupMembershipCommand command,
) => _targetPath(command.circleId, command.groupId, command.personaId);

CloudOperationRequestPayload encodeUpdateCircleGroupMembershipRoleCommand(
  UpdateCircleGroupMembershipRoleCommand command,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{
    'circleId': command.circleId,
    'groupId': command.groupId,
    'personaId': command.personaId,
  },
  body: <String, Object?>{'role': command.role.name},
);

CircleGroupMembershipCommandResult decodeCircleGroupMembershipCommandResult(
  Object? value,
) {
  final map = _object(value, 'CircleGroupMembershipCommandResult');
  _only(map, const <String>{
    'membershipId',
    'version',
    'role',
    'state',
    'idempotentReplay',
  });
  return CircleGroupMembershipCommandResult(
    membershipId: _string(map, 'membershipId'),
    version: _positiveInt(map, 'version'),
    role: _role(map['role']),
    state: _state(map['state']),
    idempotentReplay: _bool(map, 'idempotentReplay'),
  );
}

CircleGroupMembershipSlice decodeCircleGroupMembershipSlice(Object? value) =>
    _slice(value);

CircleGroupMembershipPageSlice decodeCircleGroupMembershipPageSlice(
  Object? value,
) {
  final map = _object(value, 'CircleGroupMembershipPageSlice');
  _only(map, const <String>{'items', 'cursor'});
  final items = map['items'];
  if (items is! List<Object?>)
    throw const FormatException('items must be a list');
  return CircleGroupMembershipPageSlice(
    items: items.map(_slice).toList(growable: false),
    nextCursor: _optionalString(map['cursor']),
  );
}

CircleGroupMembershipSlice _slice(Object? value) {
  final map = _object(value, 'CircleGroupMembershipSlice');
  _only(map, const <String>{
    'membershipId',
    'version',
    'groupId',
    'circleId',
    'personaId',
    'role',
    'state',
    'joinedAt',
    'leftAt',
    'decidedAt',
    'createdAt',
    'updatedAt',
  });
  return CircleGroupMembershipSlice(
    membershipId: _string(map, 'membershipId'),
    version: _positiveInt(map, 'version'),
    groupId: _string(map, 'groupId'),
    circleId: _string(map, 'circleId'),
    personaId: _string(map, 'personaId'),
    role: _role(map['role']),
    state: _state(map['state']),
    joinedAt: _optionalDate(map['joinedAt']),
    leftAt: _optionalDate(map['leftAt']),
    decidedAt: _optionalDate(map['decidedAt']),
    createdAt: _date(map, 'createdAt'),
    updatedAt: _date(map, 'updatedAt'),
  );
}

CloudOperationRequestPayload _path(String circleId, String groupId) =>
    CloudOperationRequestPayload(
      pathParameters: <String, String>{
        'circleId': circleId,
        'groupId': groupId,
      },
    );

CloudOperationRequestPayload _targetPath(
  String circleId,
  String groupId,
  String personaId,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{
    'circleId': circleId,
    'groupId': groupId,
    'personaId': personaId,
  },
);

CircleGroupMembershipRole _role(Object? value) => switch (value) {
  'owner' => CircleGroupMembershipRole.owner,
  'manager' => CircleGroupMembershipRole.manager,
  'member' => CircleGroupMembershipRole.member,
  _ => throw FormatException('invalid CircleGroupMembershipRole: $value'),
};

CircleGroupMembershipState _state(Object? value) => switch (value) {
  'pending' => CircleGroupMembershipState.pending,
  'active' => CircleGroupMembershipState.active,
  'rejected' => CircleGroupMembershipState.rejected,
  'left' => CircleGroupMembershipState.left,
  'removed' => CircleGroupMembershipState.removed,
  _ => throw FormatException('invalid CircleGroupMembershipState: $value'),
};

Map<String, Object?> _object(Object? value, String label) {
  if (value is! Map) throw FormatException('$label must be an object');
  return value.map((key, value) {
    if (key is! String) throw FormatException('$label key must be string');
    return MapEntry(key, value);
  });
}

void _only(Map<String, Object?> map, Set<String> allowed) {
  final unknown = map.keys.where((key) => !allowed.contains(key)).toList();
  if (unknown.isNotEmpty) throw FormatException('unknown fields: $unknown');
}

String _required(String value, String name) {
  final normalized = value.trim();
  if (normalized.isEmpty) throw ArgumentError.value(value, name, 'required');
  return normalized;
}

String _string(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! String || value.trim().isEmpty)
    throw FormatException('$key must be non-empty');
  return value;
}

String? _optionalString(Object? value) {
  if (value == null || value == '') return null;
  if (value is! String) throw const FormatException('optional string invalid');
  return value;
}

int _positiveInt(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! int || value <= 0)
    throw FormatException('$key must be positive');
  return value;
}

bool _bool(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! bool) throw FormatException('$key must be bool');
  return value;
}

DateTime _date(Map<String, Object?> map, String key) {
  final value = DateTime.tryParse(_string(map, key));
  if (value == null) throw FormatException('$key must be RFC3339');
  return value.toUtc();
}

DateTime? _optionalDate(Object? value) {
  if (value == null || value == '') return null;
  if (value is! String)
    throw const FormatException('optional timestamp invalid');
  final parsed = DateTime.tryParse(value);
  if (parsed == null)
    throw const FormatException('optional timestamp must be RFC3339');
  return parsed.toUtc();
}

void _limit(int value) {
  if (value < 1 || value > 100)
    throw ArgumentError.value(value, 'limit', 'must be in 1..100');
}
