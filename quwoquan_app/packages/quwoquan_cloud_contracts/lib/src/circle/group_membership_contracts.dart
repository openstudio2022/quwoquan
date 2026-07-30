import '../operation_request_payload.dart';
part '../generated/requests/circle/group_membership_contracts.requests.g.dart';

enum CircleGroupMembershipRole { owner, manager, member }

enum CircleGroupMembershipState { pending, active, rejected, left, removed }

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
