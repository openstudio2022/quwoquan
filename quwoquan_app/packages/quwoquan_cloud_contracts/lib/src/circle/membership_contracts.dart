import '../operation_request_payload.dart';

enum CircleMembershipRole { owner, admin, member }

enum CircleMembershipState { pending, active, left, removed }

final class JoinCircleMembershipCommand {
  JoinCircleMembershipCommand({required String circleId})
    : circleId = _required(circleId, 'circleId');

  final String circleId;
}

final class LeaveCircleMembershipCommand {
  LeaveCircleMembershipCommand({
    required String circleId,
    required this.expectedVersion,
  }) : circleId = _required(circleId, 'circleId') {
    _positive(expectedVersion, 'expectedVersion');
  }

  final String circleId;
  final int expectedVersion;
}

final class UpdateCircleMembershipRoleCommand {
  UpdateCircleMembershipRoleCommand({
    required String circleId,
    required String personaId,
    required this.role,
    required this.expectedVersion,
  }) : circleId = _required(circleId, 'circleId'),
       personaId = _required(personaId, 'personaId') {
    if (role == CircleMembershipRole.owner) {
      throw ArgumentError.value(
        role,
        'role',
        'owner transfer is not a role update',
      );
    }
    _positive(expectedVersion, 'expectedVersion');
  }

  final String circleId;
  final String personaId;
  final CircleMembershipRole role;
  final int expectedVersion;
}

final class CircleMembershipListQuery {
  CircleMembershipListQuery({
    required String circleId,
    this.cursor,
    this.limit = 20,
  }) : circleId = _required(circleId, 'circleId') {
    _limit(limit);
  }

  final String circleId;
  final String? cursor;
  final int limit;
}

final class MyCircleMembershipQuery {
  MyCircleMembershipQuery({required String circleId})
    : circleId = _required(circleId, 'circleId');

  final String circleId;
}

final class PersonaCircleListQuery {
  PersonaCircleListQuery({
    required String personaId,
    this.cursor,
    this.limit = 20,
  }) : personaId = _required(personaId, 'personaId') {
    _limit(limit);
  }

  final String personaId;
  final String? cursor;
  final int limit;
}

final class CircleMembershipCommandResult {
  const CircleMembershipCommandResult({
    required this.membershipId,
    required this.version,
    required this.state,
    required this.role,
    required this.idempotentReplay,
  });

  final String membershipId;
  final int version;
  final CircleMembershipState state;
  final CircleMembershipRole role;
  final bool idempotentReplay;
}

final class CircleMembershipSlice {
  const CircleMembershipSlice({
    required this.membershipId,
    required this.version,
    required this.circleId,
    required this.personaId,
    required this.role,
    required this.state,
    required this.joinedAt,
    required this.leftAt,
    required this.lastActiveAt,
    required this.contribution,
    required this.createdAt,
    required this.updatedAt,
  });

  final String membershipId;
  final int version;
  final String circleId;
  final String personaId;
  final CircleMembershipRole role;
  final CircleMembershipState state;
  final DateTime joinedAt;
  final DateTime? leftAt;
  final DateTime? lastActiveAt;
  final int contribution;
  final DateTime createdAt;
  final DateTime updatedAt;
}

final class CircleMembershipPageSlice {
  const CircleMembershipPageSlice({required this.items, this.nextCursor});

  final List<CircleMembershipSlice> items;
  final String? nextCursor;
}

/// PersonaCircleReader 的跨上下文只读投影，不是 Circle aggregate。
final class PersonaCircleSummary {
  const PersonaCircleSummary({
    required this.circleId,
    required this.name,
    required this.description,
    required this.coverUrl,
    required this.iconUrl,
    required this.ownerPersonaId,
    required this.ownerDisplayNameSnapshot,
    required this.category,
    required this.subCategory,
    required this.tags,
    required this.memberCount,
    required this.postCount,
    required this.weeklyActiveCount,
    required this.state,
    required this.visibility,
    required this.joinPolicy,
    required this.kind,
    required this.displaySubjectType,
    required this.followEnabled,
    required this.defaultPublicGroupId,
    required this.linkedHomepageId,
    required this.linkedHomepageType,
    required this.linkedHomepageTitle,
    required this.createdAt,
    required this.updatedAt,
  });

  final String circleId;
  final String name;
  final String description;
  final String coverUrl;
  final String iconUrl;
  final String ownerPersonaId;
  final String ownerDisplayNameSnapshot;
  final String category;
  final String subCategory;
  final List<String> tags;
  final int memberCount;
  final int postCount;
  final int weeklyActiveCount;
  final String state;
  final String visibility;
  final String joinPolicy;
  final String kind;
  final String displaySubjectType;
  final bool followEnabled;
  final String defaultPublicGroupId;
  final String linkedHomepageId;
  final String linkedHomepageType;
  final String linkedHomepageTitle;
  final DateTime createdAt;
  final DateTime updatedAt;
}

final class PersonaCirclePageSlice {
  const PersonaCirclePageSlice({required this.items, this.nextCursor});

  final List<PersonaCircleSummary> items;
  final String? nextCursor;
}

abstract interface class CircleMembershipCommandWriter {
  Future<CircleMembershipCommandResult> join(
    JoinCircleMembershipCommand command,
  );
  Future<CircleMembershipCommandResult> leave(
    LeaveCircleMembershipCommand command,
  );
  Future<CircleMembershipCommandResult> updateRole(
    UpdateCircleMembershipRoleCommand command,
  );
}

abstract interface class CircleMembershipQuery {
  Future<CircleMembershipSlice> getMyMembership(MyCircleMembershipQuery query);
  Future<CircleMembershipPageSlice> listMemberships(
    CircleMembershipListQuery query,
  );
  Future<PersonaCirclePageSlice> listPersonaCircles(
    PersonaCircleListQuery query,
  );
}

CloudOperationRequestPayload encodeMyCircleMembershipQuery(
  MyCircleMembershipQuery query,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'circleId': query.circleId},
);

CloudOperationRequestPayload encodeJoinCircleMembershipCommand(
  JoinCircleMembershipCommand command,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'circleId': command.circleId},
);

CloudOperationRequestPayload encodeLeaveCircleMembershipCommand(
  LeaveCircleMembershipCommand command,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'circleId': command.circleId},
  headers: <String, String>{'If-Match': '"${command.expectedVersion}"'},
);

CloudOperationRequestPayload encodeUpdateCircleMembershipRoleCommand(
  UpdateCircleMembershipRoleCommand command,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{
    'circleId': command.circleId,
    'personaId': command.personaId,
  },
  body: <String, Object?>{
    'role': command.role.name,
    'expectedVersion': command.expectedVersion,
  },
);

CloudOperationRequestPayload encodeCircleMembershipListQuery(
  CircleMembershipListQuery query,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'circleId': query.circleId},
  queryParameters: _pageQuery(query.cursor, query.limit),
);

CloudOperationRequestPayload encodePersonaCircleListQuery(
  PersonaCircleListQuery query,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'personaId': query.personaId},
  queryParameters: _pageQuery(query.cursor, query.limit),
);

CircleMembershipCommandResult decodeCircleMembershipCommandResult(
  Object? value,
) {
  final map = _object(value, 'CircleMembershipCommandResult');
  _only(map, const <String>{
    'membershipId',
    'version',
    'state',
    'role',
    'idempotentReplay',
  });
  return CircleMembershipCommandResult(
    membershipId: _string(map, 'membershipId'),
    version: _positiveInt(map, 'version'),
    state: _membershipState(map['state']),
    role: _membershipRole(map['role']),
    idempotentReplay: _bool(map, 'idempotentReplay'),
  );
}

CircleMembershipPageSlice decodeCircleMembershipPageSlice(Object? value) {
  final map = _object(value, 'CircleMembershipPageSlice');
  _only(map, const <String>{'items', 'cursor'});
  return CircleMembershipPageSlice(
    items: _list(
      map,
      'items',
    ).map(_decodeCircleMembershipSlice).toList(growable: false),
    nextCursor: _optionalString(map['cursor']),
  );
}

CircleMembershipSlice decodeCircleMembershipSlice(Object? value) =>
    _decodeCircleMembershipSlice(value);

PersonaCirclePageSlice decodePersonaCirclePageSlice(Object? value) {
  final map = _object(value, 'PersonaCirclePageSlice');
  _only(map, const <String>{'items', 'cursor'});
  return PersonaCirclePageSlice(
    items: _list(
      map,
      'items',
    ).map(_decodePersonaCircleSummary).toList(growable: false),
    nextCursor: _optionalString(map['cursor']),
  );
}

CircleMembershipSlice _decodeCircleMembershipSlice(Object? value) {
  final map = _object(value, 'CircleMembershipSlice');
  _only(map, const <String>{
    'membershipId',
    'version',
    'circleId',
    'personaId',
    'role',
    'state',
    'joinedAt',
    'leftAt',
    'lastActiveAt',
    'contribution',
    'createdAt',
    'updatedAt',
  });
  return CircleMembershipSlice(
    membershipId: _string(map, 'membershipId'),
    version: _positiveInt(map, 'version'),
    circleId: _string(map, 'circleId'),
    personaId: _string(map, 'personaId'),
    role: _membershipRole(map['role']),
    state: _membershipState(map['state']),
    joinedAt: _date(map, 'joinedAt'),
    leftAt: _optionalDate(map['leftAt']),
    lastActiveAt: _optionalDate(map['lastActiveAt']),
    contribution: _nonNegativeInt(map, 'contribution'),
    createdAt: _date(map, 'createdAt'),
    updatedAt: _date(map, 'updatedAt'),
  );
}

PersonaCircleSummary _decodePersonaCircleSummary(Object? value) {
  final map = _object(value, 'PersonaCircleSummary');
  _only(map, const <String>{
    'circleId',
    'name',
    'description',
    'coverUrl',
    'iconUrl',
    'ownerPersonaId',
    'ownerDisplayNameSnapshot',
    'category',
    'subCategory',
    'tags',
    'memberCount',
    'postCount',
    'weeklyActiveCount',
    'state',
    'visibility',
    'joinPolicy',
    'kind',
    'displaySubjectType',
    'followEnabled',
    'defaultPublicGroupId',
    'linkedHomepageId',
    'linkedHomepageType',
    'linkedHomepageTitle',
    'createdAt',
    'updatedAt',
  });
  return PersonaCircleSummary(
    circleId: _string(map, 'circleId'),
    name: _string(map, 'name'),
    description: _stringValue(map['description'], 'description'),
    coverUrl: _stringValue(map['coverUrl'], 'coverUrl'),
    iconUrl: _stringValue(map['iconUrl'], 'iconUrl'),
    ownerPersonaId: _string(map, 'ownerPersonaId'),
    ownerDisplayNameSnapshot: _stringValue(
      map['ownerDisplayNameSnapshot'],
      'ownerDisplayNameSnapshot',
    ),
    category: _stringValue(map['category'], 'category'),
    subCategory: _stringValue(map['subCategory'], 'subCategory'),
    tags: _list(
      map,
      'tags',
    ).map((item) => _stringValue(item, 'tag')).toList(growable: false),
    memberCount: _nonNegativeInt(map, 'memberCount'),
    postCount: _nonNegativeInt(map, 'postCount'),
    weeklyActiveCount: _nonNegativeInt(map, 'weeklyActiveCount'),
    state: _string(map, 'state'),
    visibility: _string(map, 'visibility'),
    joinPolicy: _string(map, 'joinPolicy'),
    kind: _string(map, 'kind'),
    displaySubjectType: _string(map, 'displaySubjectType'),
    followEnabled: _bool(map, 'followEnabled'),
    defaultPublicGroupId: _stringValue(
      map['defaultPublicGroupId'],
      'defaultPublicGroupId',
    ),
    linkedHomepageId: _stringValue(map['linkedHomepageId'], 'linkedHomepageId'),
    linkedHomepageType: _stringValue(
      map['linkedHomepageType'],
      'linkedHomepageType',
    ),
    linkedHomepageTitle: _stringValue(
      map['linkedHomepageTitle'],
      'linkedHomepageTitle',
    ),
    createdAt: _date(map, 'createdAt'),
    updatedAt: _date(map, 'updatedAt'),
  );
}

Map<String, String> _pageQuery(String? cursor, int limit) => <String, String>{
  'limit': '$limit',
  if (_optionalString(cursor) case final cursor?) 'cursor': cursor,
};

Map<String, Object?> _object(Object? value, String name) {
  if (value is! Map) throw FormatException('$name must be an object');
  return value.map((key, item) => MapEntry(key.toString(), item));
}

List<Object?> _list(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! List) throw FormatException('$key must be a list');
  return List<Object?>.from(value);
}

void _only(Map<String, Object?> map, Set<String> keys) {
  final unknown = map.keys.where((key) => !keys.contains(key)).toList();
  if (unknown.isNotEmpty)
    throw FormatException('unknown fields: ${unknown.join(',')}');
}

String _string(Map<String, Object?> map, String key) =>
    _required(_stringValue(map[key], key), key);

String _stringValue(Object? value, String key) {
  if (value is! String) throw FormatException('$key must be a string');
  return value;
}

String? _optionalString(Object? value) {
  if (value == null) return null;
  if (value is! String)
    throw const FormatException('optional value must be a string');
  final normalized = value.trim();
  return normalized.isEmpty ? null : normalized;
}

int _positiveInt(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! int || value <= 0)
    throw FormatException('$key must be positive');
  return value;
}

int _nonNegativeInt(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! int || value < 0)
    throw FormatException('$key must be non-negative');
  return value;
}

bool _bool(Map<String, Object?> map, String key) {
  final value = map[key];
  if (value is! bool) throw FormatException('$key must be a boolean');
  return value;
}

DateTime _date(Map<String, Object?> map, String key) {
  final value = map[key];
  final parsed = value is String ? DateTime.tryParse(value) : null;
  if (parsed == null)
    throw FormatException('$key must be an RFC3339 timestamp');
  return parsed;
}

DateTime? _optionalDate(Object? value) {
  if (value == null) return null;
  if (value is! String)
    throw const FormatException('timestamp must be a string');
  final parsed = DateTime.tryParse(value);
  if (parsed == null || parsed.year <= 1) return null;
  return parsed;
}

CircleMembershipRole _membershipRole(Object? value) => switch (value) {
  'owner' => CircleMembershipRole.owner,
  'admin' => CircleMembershipRole.admin,
  'member' => CircleMembershipRole.member,
  _ => throw const FormatException('invalid CircleMembershipRole'),
};

CircleMembershipState _membershipState(Object? value) => switch (value) {
  'pending' => CircleMembershipState.pending,
  'active' => CircleMembershipState.active,
  'left' => CircleMembershipState.left,
  'removed' => CircleMembershipState.removed,
  _ => throw const FormatException('invalid CircleMembershipState'),
};

String _required(String value, String name) {
  final normalized = value.trim();
  if (normalized.isEmpty) throw ArgumentError.value(value, name, 'required');
  return normalized;
}

void _positive(int value, String name) {
  if (value <= 0) throw ArgumentError.value(value, name, 'must be positive');
}

void _limit(int value) {
  if (value < 1 || value > 100) {
    throw ArgumentError.value(value, 'limit', 'must be between 1 and 100');
  }
}
