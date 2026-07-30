import '../operation_request_payload.dart';
part '../generated/requests/circle/group_contracts.requests.g.dart';

enum CircleGroupType { publicGroup, selfBuilt, orgNode }

enum CircleGroupNodeType {
  generic,
  college,
  grade,
  classroom,
  department,
  team,
}

enum CircleGroupVisibility { public, private }

enum CircleGroupJoinPolicy { applyOnly, inviteOnly }

enum CircleGroupStatus { active, archived }

final class CircleGroupCommandResult {
  const CircleGroupCommandResult({
    required this.groupId,
    required this.version,
    required this.status,
    required this.idempotentReplay,
  });

  final String groupId;
  final int version;
  final CircleGroupStatus status;
  final bool idempotentReplay;
}

final class CircleGroupSlice {
  const CircleGroupSlice({
    required this.groupId,
    required this.version,
    required this.circleId,
    required this.parentGroupId,
    required this.groupType,
    required this.nodeType,
    required this.name,
    required this.description,
    required this.visibility,
    required this.joinPolicy,
    required this.conversationId,
    required this.storageEnabled,
    required this.noticeEnabled,
    required this.isDefaultPublicGroup,
    required this.status,
    required this.memberCount,
    required this.createdAt,
    required this.updatedAt,
  });

  final String groupId;
  final int version;
  final String circleId;
  final String? parentGroupId;
  final CircleGroupType groupType;
  final CircleGroupNodeType? nodeType;
  final String name;
  final String description;
  final CircleGroupVisibility visibility;
  final CircleGroupJoinPolicy joinPolicy;
  final String? conversationId;
  final bool storageEnabled;
  final bool noticeEnabled;
  final bool isDefaultPublicGroup;
  final CircleGroupStatus status;
  final int memberCount;
  final DateTime createdAt;
  final DateTime updatedAt;
}

final class CircleGroupPageSlice {
  const CircleGroupPageSlice({required this.items, this.nextCursor});

  final List<CircleGroupSlice> items;
  final String? nextCursor;
}

abstract interface class CircleGroupCommandWriter {
  Future<CircleGroupCommandResult> create(CreateCircleGroupCommand command);
  Future<CircleGroupCommandResult> update(UpdateCircleGroupCommand command);
  Future<CircleGroupCommandResult> archive(ArchiveCircleGroupCommand command);
}

abstract interface class CircleGroupQueryReader {
  Future<CircleGroupSlice> get(CircleGroupQuery query);
  Future<CircleGroupPageSlice> list(CircleGroupListQuery query);
  Future<CircleGroupPageSlice> search(CircleGroupSearchQuery query);
}

CircleGroupCommandResult decodeCircleGroupCommandResult(Object? value) {
  final map = _object(value, 'CircleGroupCommandResult');
  _only(map, const <String>{
    'groupId',
    'version',
    'status',
    'idempotentReplay',
  });
  return CircleGroupCommandResult(
    groupId: _string(map, 'groupId'),
    version: _positiveInt(map, 'version'),
    status: _status(map['status']),
    idempotentReplay: _bool(map, 'idempotentReplay'),
  );
}

CircleGroupSlice decodeCircleGroupSlice(Object? value) => _slice(value);

CircleGroupPageSlice decodeCircleGroupPageSlice(Object? value) {
  final map = _object(value, 'CircleGroupPageSlice');
  _only(map, const <String>{'items', 'cursor'});
  final items = map['items'];
  if (items is! List<Object?>) {
    throw const FormatException('CircleGroupPageSlice.items must be a list');
  }
  return CircleGroupPageSlice(
    items: items.map(_slice).toList(growable: false),
    nextCursor: _optionalString(map['cursor']),
  );
}

CircleGroupSlice _slice(Object? value) {
  final map = _object(value, 'CircleGroupSlice');
  _only(map, const <String>{
    'groupId',
    'version',
    'circleId',
    'parentGroupId',
    'groupType',
    'nodeType',
    'name',
    'description',
    'visibility',
    'joinPolicy',
    'conversationId',
    'storageEnabled',
    'noticeEnabled',
    'isDefaultPublicGroup',
    'status',
    'memberCount',
    'createdAt',
    'updatedAt',
  });
  return CircleGroupSlice(
    groupId: _string(map, 'groupId'),
    version: _positiveInt(map, 'version'),
    circleId: _string(map, 'circleId'),
    parentGroupId: _optionalString(map['parentGroupId']),
    groupType: _groupType(map['groupType']),
    nodeType: _optionalNodeType(map['nodeType']),
    name: _string(map, 'name'),
    description: _optionalString(map['description']) ?? '',
    visibility: _visibility(map['visibility']),
    joinPolicy: _joinPolicy(map['joinPolicy']),
    conversationId: _optionalString(map['conversationId']),
    storageEnabled: _bool(map, 'storageEnabled'),
    noticeEnabled: _bool(map, 'noticeEnabled'),
    isDefaultPublicGroup: _bool(map, 'isDefaultPublicGroup'),
    status: _status(map['status']),
    memberCount: _nonNegativeInt(map, 'memberCount'),
    createdAt: _date(map, 'createdAt'),
    updatedAt: _date(map, 'updatedAt'),
  );
}

CircleGroupType _groupType(Object? value) => switch (value) {
  'public_group' => CircleGroupType.publicGroup,
  'self_built' => CircleGroupType.selfBuilt,
  'org_node' => CircleGroupType.orgNode,
  _ => throw FormatException('invalid CircleGroupType: $value'),
};

CircleGroupNodeType? _optionalNodeType(Object? value) => switch (value) {
  null || '' => null,
  'generic' => CircleGroupNodeType.generic,
  'college' => CircleGroupNodeType.college,
  'grade' => CircleGroupNodeType.grade,
  'classroom' => CircleGroupNodeType.classroom,
  'department' => CircleGroupNodeType.department,
  'team' => CircleGroupNodeType.team,
  _ => throw FormatException('invalid CircleGroupNodeType: $value'),
};

CircleGroupVisibility _visibility(Object? value) => switch (value) {
  'public' => CircleGroupVisibility.public,
  'private' => CircleGroupVisibility.private,
  _ => throw FormatException('invalid CircleGroupVisibility: $value'),
};

CircleGroupJoinPolicy _joinPolicy(Object? value) => switch (value) {
  'apply_only' => CircleGroupJoinPolicy.applyOnly,
  'invite_only' => CircleGroupJoinPolicy.inviteOnly,
  _ => throw FormatException('invalid CircleGroupJoinPolicy: $value'),
};

CircleGroupStatus _status(Object? value) => switch (value) {
  'active' => CircleGroupStatus.active,
  'archived' => CircleGroupStatus.archived,
  _ => throw FormatException('invalid CircleGroupStatus: $value'),
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
  if (value is! String || value.trim().isEmpty) {
    throw FormatException('$key must be a non-empty string');
  }
  return value;
}

String? _optionalString(Object? value) {
  if (value == null || value == '') return null;
  if (value is! String) throw const FormatException('optional string invalid');
  return value;
}

bool _bool(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! bool) throw FormatException('$key must be bool');
  return value;
}

int _positiveInt(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! int || value <= 0)
    throw FormatException('$key must be positive');
  return value;
}

int _nonNegativeInt(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! int || value < 0) {
    throw FormatException('$key must be non-negative');
  }
  return value;
}

DateTime _date(Map<String, Object?> map, String key) {
  final raw = _string(map, key);
  final value = DateTime.tryParse(raw);
  if (value == null) throw FormatException('$key must be RFC3339');
  return value.toUtc();
}
