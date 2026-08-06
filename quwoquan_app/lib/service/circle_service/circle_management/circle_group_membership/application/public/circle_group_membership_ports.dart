import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 圈内小组成员关系的公开命令边界。
abstract interface class CircleGroupMembershipCommands {
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

/// 圈内小组成员关系的公开查询边界。
abstract interface class CircleGroupMembershipQueries {
  Future<CircleGroupMembershipSlice> getMy(MyCircleGroupMembershipQuery query);

  Future<CircleGroupMembershipPageSlice> list(
    CircleGroupMembershipListQuery query,
  );
}
