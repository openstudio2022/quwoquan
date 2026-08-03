import 'circle_operation_contracts.g.dart';

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
