import 'package:quwoquan_app/service/circle_service/circle_management/circle_membership/application/public/circle_membership_ports.dart';
import 'package:quwoquan_app/runtime/transport/generated/circle/circle_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef CircleMembershipInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      required bool command,
    });

final class RemoteCircleMembershipFacet
    implements
        CircleMembershipCommands,
        CircleMembershipModeration,
        CircleMembershipQueries,
        PendingCircleMemberships {
  const RemoteCircleMembershipFacet({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final CircleMembershipInvocationContextFactory invocationContext;

  @override
  Future<CircleMembershipCommandResult> join(
    JoinCircleMembershipCommand command,
  ) => client.circleCircleMembershipJoinCircle(
    command,
    context: invocationContext(CircleRequestPageIds.joinCircle, command: true),
  );

  @override
  Future<CircleMembershipCommandResult> leave(
    LeaveCircleMembershipCommand command,
  ) => client.circleCircleMembershipLeaveCircle(
    command,
    context: invocationContext(CircleRequestPageIds.leaveCircle, command: true),
  );

  @override
  Future<CircleMembershipCommandResult> updateRole(
    UpdateCircleMembershipRoleCommand command,
  ) => client.circleCircleMembershipUpdateCircleMembershipRole(
    command,
    context: invocationContext(
      CircleRequestPageIds.updateCircleMembershipRole,
      command: true,
    ),
  );

  @override
  Future<CircleMembershipCommandResult> approve(
    DecideCircleMembershipCommand command,
  ) => client.circleCircleMembershipApproveCircleMember(
    command,
    context: invocationContext(
      CircleRequestPageIds.approveCircleMember,
      command: true,
    ),
  );

  @override
  Future<CircleMembershipCommandResult> reject(
    DecideCircleMembershipCommand command,
  ) => client.circleCircleMembershipRejectCircleMember(
    command,
    context: invocationContext(
      CircleRequestPageIds.rejectCircleMember,
      command: true,
    ),
  );

  @override
  Future<CircleMembershipPageSlice> listMemberships(
    CircleMembershipListQuery query,
  ) => client.circleCircleMembershipListCircleMemberships(
    query,
    context: invocationContext(
      CircleRequestPageIds.listCircleMemberships,
      command: false,
    ),
  );

  @override
  Future<CircleMembershipPageSlice> listPendingMemberships(
    PendingCircleMembershipListQuery query,
  ) => client.circleCircleMembershipListPendingCircleMemberships(
    query,
    context: invocationContext(
      CircleRequestPageIds.listPendingCircleMemberships,
      command: false,
    ),
  );

  @override
  Future<CircleMembershipSlice> getMyMembership(
    MyCircleMembershipQuery query,
  ) => client.circleCircleMembershipGetMyCircleMembership(
    query,
    context: invocationContext(
      CircleRequestPageIds.getMyCircleMembership,
      command: false,
    ),
  );

  @override
  Future<PersonaCirclePageSlice> listPersonaCircles(
    PersonaCircleListQuery query,
  ) => client.circleCircleMembershipListPersonaCircles(
    query,
    context: invocationContext(
      CircleRequestPageIds.listPersonaCircles,
      command: false,
    ),
  );
}
