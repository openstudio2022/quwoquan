import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Alpha runner 专用的强类型 CircleGroupMembership fixture。
final class AlphaCircleGroupMembershipFacet
    implements
        CircleGroupMembershipCommandWriter,
        CircleGroupMembershipQueryReader {
  final Map<String, CircleGroupMembershipSlice> _memberships =
      <String, CircleGroupMembershipSlice>{};

  @override
  Future<CircleGroupMembershipCommandResult> apply(
    ApplyCircleGroupMembershipCommand command,
  ) async {
    final key = _key(command.circleId, command.groupId, _personaId);
    final existing = _memberships[key];
    if (existing != null &&
        (existing.state == CircleGroupMembershipState.pending ||
            existing.state == CircleGroupMembershipState.active)) {
      return _result(existing, replayed: true);
    }
    final membership = CircleGroupMembershipSlice(
      membershipId: 'alpha_group_membership_${command.groupId}_$_personaId',
      version: (existing?.version ?? 0) + 1,
      groupId: command.groupId,
      circleId: command.circleId,
      personaId: _personaId,
      role: CircleGroupMembershipRole.member,
      state: CircleGroupMembershipState.pending,
      joinedAt: null,
      leftAt: null,
      decidedAt: null,
      createdAt: existing?.createdAt ?? _now,
      updatedAt: _now,
    );
    _memberships[key] = membership;
    return _result(membership, replayed: false);
  }

  @override
  Future<CircleGroupMembershipCommandResult> leave(
    LeaveCircleGroupMembershipCommand command,
  ) async => _transition(
    circleId: command.circleId,
    groupId: command.groupId,
    personaId: _personaId,
    expectedVersion: command.expectedVersion,
    state: CircleGroupMembershipState.left,
  );

  @override
  Future<CircleGroupMembershipCommandResult> approve(
    DecideCircleGroupMembershipCommand command,
  ) async => _transition(
    circleId: command.circleId,
    groupId: command.groupId,
    personaId: command.personaId,
    expectedVersion: command.expectedVersion,
    state: CircleGroupMembershipState.active,
  );

  @override
  Future<CircleGroupMembershipCommandResult> reject(
    DecideCircleGroupMembershipCommand command,
  ) async => _transition(
    circleId: command.circleId,
    groupId: command.groupId,
    personaId: command.personaId,
    expectedVersion: command.expectedVersion,
    state: CircleGroupMembershipState.rejected,
  );

  @override
  Future<CircleGroupMembershipCommandResult> remove(
    RemoveCircleGroupMembershipCommand command,
  ) async => _transition(
    circleId: command.circleId,
    groupId: command.groupId,
    personaId: command.personaId,
    expectedVersion: command.expectedVersion,
    state: CircleGroupMembershipState.removed,
  );

  @override
  Future<CircleGroupMembershipCommandResult> updateRole(
    UpdateCircleGroupMembershipRoleCommand command,
  ) async {
    final key = _key(command.circleId, command.groupId, command.personaId);
    final current = _required(key, command.expectedVersion);
    if (current.state != CircleGroupMembershipState.active) {
      throw StateError('alpha CircleGroupMembership is not active');
    }
    final updated = _copy(
      current,
      version: current.version + 1,
      role: command.role,
      state: current.state,
    );
    _memberships[key] = updated;
    return _result(updated, replayed: false);
  }

  @override
  Future<CircleGroupMembershipSlice> getMy(
    MyCircleGroupMembershipQuery query,
  ) async => _required(_key(query.circleId, query.groupId, _personaId));

  @override
  Future<CircleGroupMembershipPageSlice> list(
    CircleGroupMembershipListQuery query,
  ) async => CircleGroupMembershipPageSlice(
    items: _memberships.values
        .where(
          (membership) =>
              membership.circleId == query.circleId &&
              membership.groupId == query.groupId,
        )
        .where(
          (membership) =>
              query.state == null || membership.state == query.state,
        )
        .take(query.limit)
        .toList(growable: false),
  );

  Future<CircleGroupMembershipCommandResult> _transition({
    required String circleId,
    required String groupId,
    required String personaId,
    required int expectedVersion,
    required CircleGroupMembershipState state,
  }) async {
    final key = _key(circleId, groupId, personaId);
    final current = _required(key, expectedVersion);
    final updated = _copy(
      current,
      version: current.version + 1,
      role: current.role,
      state: state,
    );
    _memberships[key] = updated;
    return _result(updated, replayed: false);
  }

  CircleGroupMembershipSlice _required(String key, [int? expectedVersion]) {
    final membership = _memberships[key];
    if (membership == null) {
      throw StateError('alpha CircleGroupMembership not found');
    }
    if (expectedVersion != null && membership.version != expectedVersion) {
      throw StateError('alpha CircleGroupMembership version conflict');
    }
    return membership;
  }

  CircleGroupMembershipSlice _copy(
    CircleGroupMembershipSlice membership, {
    required int version,
    required CircleGroupMembershipRole role,
    required CircleGroupMembershipState state,
  }) => CircleGroupMembershipSlice(
    membershipId: membership.membershipId,
    version: version,
    groupId: membership.groupId,
    circleId: membership.circleId,
    personaId: membership.personaId,
    role: role,
    state: state,
    joinedAt: state == CircleGroupMembershipState.active
        ? membership.joinedAt ?? _now
        : membership.joinedAt,
    leftAt: state == CircleGroupMembershipState.left ? _now : null,
    decidedAt:
        state == CircleGroupMembershipState.active ||
            state == CircleGroupMembershipState.rejected
        ? _now
        : membership.decidedAt,
    createdAt: membership.createdAt,
    updatedAt: _now,
  );

  CircleGroupMembershipCommandResult _result(
    CircleGroupMembershipSlice membership, {
    required bool replayed,
  }) => CircleGroupMembershipCommandResult(
    membershipId: membership.membershipId,
    version: membership.version,
    role: membership.role,
    state: membership.state,
    idempotentReplay: replayed,
  );

  String _key(String circleId, String groupId, String personaId) =>
      '$circleId::$groupId::$personaId';

  static const String _personaId = 'alpha_persona';
  DateTime get _now => DateTime.utc(2026, 7, 14);
}
