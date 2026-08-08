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

/// 审批页使用的 production command 能力。
///
/// [clientRequestId] 由 UI 在一次用户意图开始时生成；同一次显式重试必须复用，
/// Remote adapter 只能透传，不得另造幂等身份。
abstract interface class ClientRequestBoundCircleMembershipModeration
    implements CircleMembershipModeration {
  Future<CircleMembershipCommandResult> approveWithClientRequestId(
    DecideCircleMembershipCommand command, {
    required String clientRequestId,
  });

  Future<CircleMembershipCommandResult> rejectWithClientRequestId(
    DecideCircleMembershipCommand command, {
    required String clientRequestId,
  });
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
