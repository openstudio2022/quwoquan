import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class AlphaCircleMembershipFacet
    implements
        CircleMembershipCommandWriter,
        CircleMembershipModerationWriter,
        CircleMembershipQuery,
        PendingCircleMembershipQuery {
  final Map<String, CircleMembershipSlice> _memberships =
      <String, CircleMembershipSlice>{};

  @override
  Future<CircleMembershipCommandResult> join(
    JoinCircleMembershipCommand command,
  ) async {
    final existing = _memberships[command.circleId];
    if (existing != null && existing.state == CircleMembershipState.active) {
      return _result(existing, replayed: true);
    }
    final now = DateTime.utc(2026, 1, 1);
    final membership = CircleMembershipSlice(
      membershipId: 'alpha_membership_${command.circleId}',
      version: (existing?.version ?? 0) + 1,
      circleId: command.circleId,
      personaId: 'alpha_persona',
      role: CircleMemberRole.member,
      state: CircleMembershipState.active,
      joinedAt: now,
      leftAt: null,
      lastActiveAt: now,
      contribution: 0,
      createdAt: existing?.createdAt ?? now,
      updatedAt: now,
    );
    _memberships[command.circleId] = membership;
    return _result(membership, replayed: false);
  }

  @override
  Future<CircleMembershipCommandResult> leave(
    LeaveCircleMembershipCommand command,
  ) async {
    final current = _memberships[command.circleId];
    if (current == null) {
      throw StateError('alpha CircleMembership not found');
    }
    final left = CircleMembershipSlice(
      membershipId: current.membershipId,
      version: current.version + 1,
      circleId: current.circleId,
      personaId: current.personaId,
      role: current.role,
      state: CircleMembershipState.left,
      joinedAt: current.joinedAt,
      leftAt: DateTime.utc(2026, 1, 1),
      lastActiveAt: current.lastActiveAt,
      contribution: current.contribution,
      createdAt: current.createdAt,
      updatedAt: DateTime.utc(2026, 1, 1),
    );
    _memberships[command.circleId] = left;
    return _result(left, replayed: false);
  }

  @override
  Future<CircleMembershipCommandResult> updateRole(
    UpdateCircleMembershipRoleCommand command,
  ) async {
    final current = _memberships[command.circleId];
    if (current == null || current.personaId != command.personaId) {
      throw StateError('alpha CircleMembership not found');
    }
    final updated = CircleMembershipSlice(
      membershipId: current.membershipId,
      version: current.version + 1,
      circleId: current.circleId,
      personaId: current.personaId,
      role: command.role,
      state: current.state,
      joinedAt: current.joinedAt,
      leftAt: current.leftAt,
      lastActiveAt: current.lastActiveAt,
      contribution: current.contribution,
      createdAt: current.createdAt,
      updatedAt: DateTime.utc(2026, 1, 1),
    );
    _memberships[command.circleId] = updated;
    return _result(updated, replayed: false);
  }

  @override
  Future<CircleMembershipCommandResult> approve(
    DecideCircleMembershipCommand command,
  ) async {
    final current = _memberships[command.circleId];
    if (current == null || current.personaId != command.personaId) {
      throw StateError('alpha CircleMembership not found');
    }
    if (current.state == CircleMembershipState.active) {
      return _result(current, replayed: true);
    }
    if (current.state != CircleMembershipState.pending) {
      throw StateError('alpha CircleMembership is not pending');
    }
    final approved = _withState(current, CircleMembershipState.active);
    _memberships[command.circleId] = approved;
    return _result(approved, replayed: false);
  }

  @override
  Future<CircleMembershipCommandResult> reject(
    DecideCircleMembershipCommand command,
  ) async {
    final current = _memberships[command.circleId];
    if (current == null || current.personaId != command.personaId) {
      throw StateError('alpha CircleMembership not found');
    }
    if (current.state == CircleMembershipState.rejected) {
      return _result(current, replayed: true);
    }
    if (current.state != CircleMembershipState.pending) {
      throw StateError('alpha CircleMembership is not pending');
    }
    final rejected = _withState(current, CircleMembershipState.rejected);
    _memberships[command.circleId] = rejected;
    return _result(rejected, replayed: false);
  }

  @override
  Future<CircleMembershipPageSlice> listMemberships(
    CircleMembershipListQuery query,
  ) async => CircleMembershipPageSlice(
    items: _memberships.values
        .where((item) => item.circleId == query.circleId)
        .take(query.limit)
        .toList(growable: false),
  );

  @override
  Future<CircleMembershipPageSlice> listPendingMemberships(
    PendingCircleMembershipListQuery query,
  ) async => CircleMembershipPageSlice(
    items: _memberships.values
        .where(
          (item) =>
              item.circleId == query.circleId &&
              item.state == CircleMembershipState.pending,
        )
        .take(query.limit)
        .toList(growable: false),
  );

  @override
  Future<CircleMembershipSlice> getMyMembership(
    MyCircleMembershipQuery query,
  ) async {
    final membership = _memberships[query.circleId];
    if (membership == null) {
      throw StateError('alpha CircleMembership not found');
    }
    return membership;
  }

  @override
  Future<PersonaCirclePageSlice> listPersonaCircles(
    PersonaCircleListQuery query,
  ) async => const PersonaCirclePageSlice(items: <PersonaCircleSlice>[]);

  CircleMembershipCommandResult _result(
    CircleMembershipSlice membership, {
    required bool replayed,
  }) => CircleMembershipCommandResult(
    membershipId: membership.membershipId,
    version: membership.version,
    state: membership.state,
    role: membership.role,
    idempotentReplay: replayed,
  );

  CircleMembershipSlice _withState(
    CircleMembershipSlice current,
    CircleMembershipState state,
  ) {
    final now = DateTime.utc(2026, 1, 1);
    return CircleMembershipSlice(
      membershipId: current.membershipId,
      version: current.version + 1,
      circleId: current.circleId,
      personaId: current.personaId,
      role: current.role,
      state: state,
      joinedAt: current.joinedAt,
      leftAt: state == CircleMembershipState.left ? now : current.leftAt,
      lastActiveAt: current.lastActiveAt,
      contribution: current.contribution,
      createdAt: current.createdAt,
      updatedAt: now,
    );
  }
}
