import '../operation_request_payload.dart';

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

final class CreateCircleGroupCommand {
  CreateCircleGroupCommand({
    required String circleId,
    this.parentGroupId,
    required this.groupType,
    this.nodeType,
    required String name,
    this.description = '',
    required this.visibility,
    required this.joinPolicy,
    required this.storageEnabled,
    required this.noticeEnabled,
  }) : circleId = _required(circleId, 'circleId'),
       name = _required(name, 'name') {
    if (name.runes.length > 80 || description.runes.length > 2000) {
      throw ArgumentError(
        'CircleGroup name/description exceeds contract limit',
      );
    }
    if (groupType == CircleGroupType.orgNode && nodeType == null) {
      throw ArgumentError('orgNode requires nodeType');
    }
    if (groupType != CircleGroupType.orgNode && nodeType != null) {
      throw ArgumentError('nodeType belongs only to orgNode');
    }
  }

  final String circleId;
  final String? parentGroupId;
  final CircleGroupType groupType;
  final CircleGroupNodeType? nodeType;
  final String name;
  final String description;
  final CircleGroupVisibility visibility;
  final CircleGroupJoinPolicy joinPolicy;
  final bool storageEnabled;
  final bool noticeEnabled;
}

final class UpdateCircleGroupCommand {
  UpdateCircleGroupCommand({
    required String circleId,
    required String groupId,
    required this.expectedVersion,
    this.parentGroupId,
    this.nodeType,
    this.name,
    this.description,
    this.visibility,
    this.joinPolicy,
    this.storageEnabled,
    this.noticeEnabled,
  }) : circleId = _required(circleId, 'circleId'),
       groupId = _required(groupId, 'groupId') {
    _positive(expectedVersion, 'expectedVersion');
    if (name != null && (name!.trim().isEmpty || name!.runes.length > 80)) {
      throw ArgumentError.value(name, 'name', 'must contain 1..80 runes');
    }
    if (description != null && description!.runes.length > 2000) {
      throw ArgumentError.value(description, 'description', 'too long');
    }
    if (parentGroupId == null &&
        nodeType == null &&
        name == null &&
        description == null &&
        visibility == null &&
        joinPolicy == null &&
        storageEnabled == null &&
        noticeEnabled == null) {
      throw ArgumentError('CircleGroup update must contain a field');
    }
  }

  final String circleId;
  final String groupId;
  final int expectedVersion;

  /// Empty string explicitly detaches the parent; null omits the field.
  final String? parentGroupId;
  final CircleGroupNodeType? nodeType;
  final String? name;
  final String? description;
  final CircleGroupVisibility? visibility;
  final CircleGroupJoinPolicy? joinPolicy;
  final bool? storageEnabled;
  final bool? noticeEnabled;
}

final class ArchiveCircleGroupCommand {
  ArchiveCircleGroupCommand({required String circleId, required String groupId})
    : circleId = _required(circleId, 'circleId'),
      groupId = _required(groupId, 'groupId');

  final String circleId;
  final String groupId;
}

final class CircleGroupQuery {
  CircleGroupQuery({required String circleId, required String groupId})
    : circleId = _required(circleId, 'circleId'),
      groupId = _required(groupId, 'groupId');

  final String circleId;
  final String groupId;
}

final class CircleGroupListQuery {
  CircleGroupListQuery({
    required String circleId,
    this.groupType,
    this.visibility,
    this.parentGroupId,
    this.nodeType,
    this.cursor,
    this.limit = 20,
  }) : circleId = _required(circleId, 'circleId') {
    _limit(limit);
  }

  final String circleId;
  final CircleGroupType? groupType;
  final CircleGroupVisibility? visibility;
  final String? parentGroupId;
  final CircleGroupNodeType? nodeType;
  final String? cursor;
  final int limit;
}

final class CircleGroupSearchQuery {
  CircleGroupSearchQuery({
    required String circleId,
    required String query,
    this.visibility,
    this.groupType,
    this.cursor,
    this.limit = 20,
  }) : circleId = _required(circleId, 'circleId'),
       query = _required(query, 'query') {
    _limit(limit);
  }

  final String circleId;
  final String query;
  final CircleGroupVisibility? visibility;
  final CircleGroupType? groupType;
  final String? cursor;
  final int limit;
}

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

CloudOperationRequestPayload encodeCreateCircleGroupCommand(
  CreateCircleGroupCommand command,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'circleId': command.circleId},
  body: <String, Object?>{
    if (command.parentGroupId != null) 'parentGroupId': command.parentGroupId,
    'groupType': _groupTypeWire(command.groupType),
    if (command.nodeType != null) 'nodeType': command.nodeType!.name,
    'name': command.name,
    'description': command.description,
    'visibility': command.visibility.name,
    'joinPolicy': _joinPolicyWire(command.joinPolicy),
    'storageEnabled': command.storageEnabled,
    'noticeEnabled': command.noticeEnabled,
  },
);

CloudOperationRequestPayload encodeUpdateCircleGroupCommand(
  UpdateCircleGroupCommand command,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{
    'circleId': command.circleId,
    'groupId': command.groupId,
  },
  headers: <String, String>{'If-Match': '"${command.expectedVersion}"'},
  body: <String, Object?>{
    if (command.parentGroupId != null) 'parentGroupId': command.parentGroupId,
    if (command.nodeType != null) 'nodeType': command.nodeType!.name,
    if (command.name != null) 'name': command.name,
    if (command.description != null) 'description': command.description,
    if (command.visibility != null) 'visibility': command.visibility!.name,
    if (command.joinPolicy != null)
      'joinPolicy': _joinPolicyWire(command.joinPolicy!),
    if (command.storageEnabled != null)
      'storageEnabled': command.storageEnabled,
    if (command.noticeEnabled != null) 'noticeEnabled': command.noticeEnabled,
  },
);

CloudOperationRequestPayload encodeArchiveCircleGroupCommand(
  ArchiveCircleGroupCommand command,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{
    'circleId': command.circleId,
    'groupId': command.groupId,
  },
);

CloudOperationRequestPayload encodeCircleGroupQuery(CircleGroupQuery query) =>
    CloudOperationRequestPayload(
      pathParameters: <String, String>{
        'circleId': query.circleId,
        'groupId': query.groupId,
      },
    );

CloudOperationRequestPayload encodeCircleGroupListQuery(
  CircleGroupListQuery query,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'circleId': query.circleId},
  queryParameters: <String, String>{
    if (query.groupType != null) 'groupType': _groupTypeWire(query.groupType!),
    if (query.visibility != null) 'visibility': query.visibility!.name,
    if (query.parentGroupId != null) 'parentGroupId': query.parentGroupId!,
    if (query.nodeType != null) 'nodeType': query.nodeType!.name,
    if (query.cursor != null) 'cursor': query.cursor!,
    'limit': query.limit.toString(),
  },
);

CloudOperationRequestPayload encodeCircleGroupSearchQuery(
  CircleGroupSearchQuery query,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'circleId': query.circleId},
  queryParameters: <String, String>{
    'query': query.query,
    if (query.visibility != null) 'visibility': query.visibility!.name,
    if (query.groupType != null) 'groupType': _groupTypeWire(query.groupType!),
    if (query.cursor != null) 'cursor': query.cursor!,
    'limit': query.limit.toString(),
  },
);

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

String _groupTypeWire(CircleGroupType value) => switch (value) {
  CircleGroupType.publicGroup => 'public_group',
  CircleGroupType.selfBuilt => 'self_built',
  CircleGroupType.orgNode => 'org_node',
};

String _joinPolicyWire(CircleGroupJoinPolicy value) => switch (value) {
  CircleGroupJoinPolicy.applyOnly => 'apply_only',
  CircleGroupJoinPolicy.inviteOnly => 'invite_only',
};

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

String _required(String value, String name) {
  final normalized = value.trim();
  if (normalized.isEmpty) throw ArgumentError.value(value, name, 'required');
  return normalized;
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

void _positive(int value, String name) {
  if (value <= 0) throw ArgumentError.value(value, name, 'must be positive');
}

void _limit(int value) {
  if (value < 1 || value > 100) {
    throw ArgumentError.value(value, 'limit', 'must be in 1..100');
  }
}
