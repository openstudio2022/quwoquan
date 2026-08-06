import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

abstract interface class CircleMembershipCommands {
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

abstract interface class CircleMembershipModeration {
  Future<CircleMembershipCommandResult> approve(
    DecideCircleMembershipCommand command,
  );

  Future<CircleMembershipCommandResult> reject(
    DecideCircleMembershipCommand command,
  );
}

/// 用户主页与关系统计只需要的最窄圈子成员查询面。
abstract interface class PersonaCircleMembershipQuery {
  Future<PersonaCirclePageSlice> listPersonaCircles(
    PersonaCircleListQuery query,
  );
}

abstract interface class CircleMembershipQueries
    implements PersonaCircleMembershipQuery {
  Future<CircleMembershipSlice> getMyMembership(MyCircleMembershipQuery query);

  Future<CircleMembershipPageSlice> listMemberships(
    CircleMembershipListQuery query,
  );
}

abstract interface class PendingCircleMemberships {
  Future<CircleMembershipPageSlice> listPendingMemberships(
    PendingCircleMembershipListQuery query,
  );
}
