import 'circle_operation_contracts.g.dart';

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
