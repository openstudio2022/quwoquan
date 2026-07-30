import '../operation_request_payload.dart';
import '../generated/circle_contract_enums.g.dart';
part '../generated/requests/circle/membership_contracts.requests.g.dart';

enum CircleMembershipRole { owner, admin, member }

enum CircleMembershipState { pending, active, rejected, left, removed }

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

  /// pending/rejected 申请尚未达成加入，joinedAt 为 null。
  final DateTime? joinedAt;
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
    required this.status,
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
  final CircleStatus status;
  final CircleVisibility visibility;
  final CircleJoinPolicy joinPolicy;
  final CircleKind kind;
  final CircleDisplaySubjectType displaySubjectType;
  final bool followEnabled;
  final String defaultPublicGroupId;
  final String linkedHomepageId;
  final HomepageType? linkedHomepageType;
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

abstract interface class CircleMembershipModerationWriter {
  Future<CircleMembershipCommandResult> approve(
    DecideCircleMembershipCommand command,
  );
  Future<CircleMembershipCommandResult> reject(
    DecideCircleMembershipCommand command,
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

abstract interface class PendingCircleMembershipQuery {
  Future<CircleMembershipPageSlice> listPendingMemberships(
    PendingCircleMembershipListQuery query,
  );
}

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
    joinedAt: _optionalDate(map['joinedAt']),
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
    'status',
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
    status: CircleStatus.fromWire(map['status']),
    visibility: CircleVisibility.fromWire(map['visibility']),
    joinPolicy: CircleJoinPolicy.fromWire(map['joinPolicy']),
    kind: CircleKind.fromWire(map['kind']),
    displaySubjectType: CircleDisplaySubjectType.fromWire(
      map['displaySubjectType'],
    ),
    followEnabled: _bool(map, 'followEnabled'),
    defaultPublicGroupId: _stringValue(
      map['defaultPublicGroupId'],
      'defaultPublicGroupId',
    ),
    linkedHomepageId: _stringValue(map['linkedHomepageId'], 'linkedHomepageId'),
    linkedHomepageType: map['linkedHomepageType'] == null
        ? null
        : HomepageType.fromWire(map['linkedHomepageType']),
    linkedHomepageTitle: _stringValue(
      map['linkedHomepageTitle'],
      'linkedHomepageTitle',
    ),
    createdAt: _date(map, 'createdAt'),
    updatedAt: _date(map, 'updatedAt'),
  );
}

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
  'rejected' => CircleMembershipState.rejected,
  'left' => CircleMembershipState.left,
  'removed' => CircleMembershipState.removed,
  _ => throw const FormatException('invalid CircleMembershipState'),
};

String _required(String value, String name) {
  final normalized = value.trim();
  if (normalized.isEmpty) throw ArgumentError.value(value, name, 'required');
  return normalized;
}
