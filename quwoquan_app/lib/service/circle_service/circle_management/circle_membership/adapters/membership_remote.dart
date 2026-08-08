import 'package:quwoquan_app/service/circle_service/circle_management/circle_membership/application/public/circle_membership_ports.dart';
import 'package:quwoquan_app/runtime/transport/generated/circle/circle_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef CircleMembershipInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      required bool command,
    });

typedef CircleMembershipClientRequestInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      required bool command,
      String? idempotencyKey,
    });

final class RemoteCircleMembershipFacet
    implements
        CircleMembershipCommands,
        CircleMembershipModeration,
        ClientRequestBoundCircleMembershipModeration,
        CircleMembershipQueries,
        PendingCircleMemberships {
  const RemoteCircleMembershipFacet({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final Object invocationContext;

  CloudOperationInvocationContext _context(
    String clientPageId, {
    required bool command,
    String? clientRequestId,
  }) {
    final normalizedClientRequestId = clientRequestId?.trim();
    if (clientRequestId != null) {
      if (normalizedClientRequestId == null ||
          normalizedClientRequestId.isEmpty) {
        throw ArgumentError.value(
          clientRequestId,
          'clientRequestId',
          'must not be blank',
        );
      }
      final factory = invocationContext;
      if (factory is! CircleMembershipClientRequestInvocationContextFactory) {
        throw StateError(
          'Circle membership moderation requires caller-bound clientRequestId',
        );
      }
      return factory(
        clientPageId,
        command: command,
        idempotencyKey: normalizedClientRequestId,
      );
    }
    final factory = invocationContext;
    if (factory is CircleMembershipInvocationContextFactory) {
      return factory(clientPageId, command: command);
    }
    if (factory is CircleMembershipClientRequestInvocationContextFactory) {
      return factory(clientPageId, command: command);
    }
    throw StateError('Invalid circle membership invocation context factory');
  }

  @override
  Future<CircleMembershipCommandResult> join(
    JoinCircleMembershipCommand command,
  ) => client.circleCircleMembershipJoinCircle(
    command,
    context: _context(CircleRequestPageIds.joinCircle, command: true),
  );

  @override
  Future<CircleMembershipCommandResult> leave(
    LeaveCircleMembershipCommand command,
  ) => client.circleCircleMembershipLeaveCircle(
    command,
    context: _context(CircleRequestPageIds.leaveCircle, command: true),
  );

  @override
  Future<CircleMembershipCommandResult> updateRole(
    UpdateCircleMembershipRoleCommand command,
  ) => client.circleCircleMembershipUpdateCircleMembershipRole(
    command,
    context: _context(
      CircleRequestPageIds.updateCircleMembershipRole,
      command: true,
    ),
  );

  @override
  Future<CircleMembershipCommandResult> approve(
    DecideCircleMembershipCommand command,
  ) => Future<CircleMembershipCommandResult>.error(
    StateError('approve requires a caller-bound clientRequestId'),
  );

  @override
  Future<CircleMembershipCommandResult> approveWithClientRequestId(
    DecideCircleMembershipCommand command, {
    required String clientRequestId,
  }) => client.circleCircleMembershipApproveCircleMember(
    command,
    context: _context(
      CircleRequestPageIds.approveCircleMember,
      command: true,
      clientRequestId: clientRequestId,
    ),
  );

  @override
  Future<CircleMembershipCommandResult> reject(
    DecideCircleMembershipCommand command,
  ) => Future<CircleMembershipCommandResult>.error(
    StateError('reject requires a caller-bound clientRequestId'),
  );

  @override
  Future<CircleMembershipCommandResult> rejectWithClientRequestId(
    DecideCircleMembershipCommand command, {
    required String clientRequestId,
  }) => client.circleCircleMembershipRejectCircleMember(
    command,
    context: _context(
      CircleRequestPageIds.rejectCircleMember,
      command: true,
      clientRequestId: clientRequestId,
    ),
  );

  @override
  Future<CircleMembershipPageSlice> listMemberships(
    CircleMembershipListQuery query,
  ) => client.circleCircleMembershipListCircleMemberships(
    query,
    context: _context(
      CircleRequestPageIds.listCircleMemberships,
      command: false,
    ),
  );

  @override
  Future<CircleMembershipPageSlice> listPendingMemberships(
    PendingCircleMembershipListQuery query,
  ) => client.circleCircleMembershipListPendingCircleMemberships(
    query,
    context: _context(
      CircleRequestPageIds.listPendingCircleMemberships,
      command: false,
    ),
  );

  @override
  Future<CircleMembershipSlice> getMyMembership(
    MyCircleMembershipQuery query,
  ) => client.circleCircleMembershipGetMyCircleMembership(
    query,
    context: _context(
      CircleRequestPageIds.getMyCircleMembership,
      command: false,
    ),
  );

  @override
  Future<PersonaCirclePageSlice> listPersonaCircles(
    PersonaCircleListQuery query,
  ) => client.circleCircleMembershipListPersonaCircles(
    query,
    context: _context(CircleRequestPageIds.listPersonaCircles, command: false),
  );
}
