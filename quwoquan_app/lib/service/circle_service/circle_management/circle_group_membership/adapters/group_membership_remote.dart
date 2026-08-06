import 'package:quwoquan_app/service/circle_service/circle_management/circle_group_membership/application/public/circle_group_membership_ports.dart';
import 'package:quwoquan_app/runtime/transport/generated/circle/circle_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef CircleGroupMembershipInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      required bool command,
    });

final class RemoteCircleGroupMembershipFacet
    implements CircleGroupMembershipCommands, CircleGroupMembershipQueries {
  const RemoteCircleGroupMembershipFacet({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final CircleGroupMembershipInvocationContextFactory invocationContext;

  @override
  Future<CircleGroupMembershipCommandResult> apply(
    ApplyCircleGroupMembershipCommand command,
  ) => client.circleCircleGroupMembershipApplyJoinCircleGroup(
    command,
    context: invocationContext(
      CircleRequestPageIds.applyJoinCircleGroup,
      command: true,
    ),
  );

  @override
  Future<CircleGroupMembershipCommandResult> leave(
    LeaveCircleGroupMembershipCommand command,
  ) => client.circleCircleGroupMembershipLeaveCircleGroup(
    command,
    context: invocationContext(
      CircleRequestPageIds.leaveCircleGroup,
      command: true,
    ),
  );

  @override
  Future<CircleGroupMembershipCommandResult> approve(
    DecideCircleGroupMembershipCommand command,
  ) => client.circleCircleGroupMembershipApproveCircleGroupMember(
    command,
    context: invocationContext(
      CircleRequestPageIds.approveCircleGroupMember,
      command: true,
    ),
  );

  @override
  Future<CircleGroupMembershipCommandResult> reject(
    DecideCircleGroupMembershipCommand command,
  ) => client.circleCircleGroupMembershipRejectCircleGroupMember(
    command,
    context: invocationContext(
      CircleRequestPageIds.rejectCircleGroupMember,
      command: true,
    ),
  );

  @override
  Future<CircleGroupMembershipCommandResult> remove(
    RemoveCircleGroupMembershipCommand command,
  ) => client.circleCircleGroupMembershipRemoveCircleGroupMember(
    command,
    context: invocationContext(
      CircleRequestPageIds.removeCircleGroupMember,
      command: true,
    ),
  );

  @override
  Future<CircleGroupMembershipCommandResult> updateRole(
    UpdateCircleGroupMembershipRoleCommand command,
  ) => client.circleCircleGroupMembershipUpdateCircleGroupMemberRole(
    command,
    context: invocationContext(
      CircleRequestPageIds.updateCircleGroupMemberRole,
      command: true,
    ),
  );

  @override
  Future<CircleGroupMembershipSlice> getMy(
    MyCircleGroupMembershipQuery query,
  ) => client.circleCircleGroupMembershipGetMyCircleGroupMembership(
    query,
    context: invocationContext(
      CircleRequestPageIds.getMyCircleGroupMembership,
      command: false,
    ),
  );

  @override
  Future<CircleGroupMembershipPageSlice> list(
    CircleGroupMembershipListQuery query,
  ) => client.circleCircleGroupMembershipListCircleGroupMemberships(
    query,
    context: invocationContext(
      CircleRequestPageIds.listCircleGroupMemberships,
      command: false,
    ),
  );
}
