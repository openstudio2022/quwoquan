import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_group_membership/application/public/circle_group_membership_ports.dart';
import 'package:quwoquan_app/runtime/di/circle_dependencies.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/circle_service/circle_management/circle/circle_operation_test_executor.dart';

void main() {
  test(
    'composition exposes the canonical group-membership command port',
    () async {
      final executor = CircleRecordingExecutor(
        response: circleGroupMembershipCommandResultFixture(),
      );
      final commands =
          CircleProductionComposition.generatedAdapter<
            CircleGroupMembershipCommands
          >(
            CircleProductionAdapter.groupMembership,
            client: GeneratedCloudOperationClient(executor),
            invocationContext: _context,
          );

      final result = await commands.apply(
        ApplyCircleGroupMembershipCommand(
          circleId: 'circle-1',
          groupId: 'group-1',
        ),
      );

      expect(result.membershipId, 'group-membership-1');
      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.circleCircleGroupMembershipApplyJoinCircleGroup,
      );
      expect(executor.pathParameters, <String, String>{
        'circleId': 'circle-1',
        'groupId': 'group-1',
      });
      expect(executor.context?.idempotencyKey, 'group-membership-contract');
    },
  );

  test(
    'composition exposes the canonical group-membership query port',
    () async {
      final executor = CircleRecordingExecutor(
        response: circleGroupMembershipSliceFixture(),
      );
      final queries =
          CircleProductionComposition.generatedAdapter<
            CircleGroupMembershipQueries
          >(
            CircleProductionAdapter.groupMembership,
            client: GeneratedCloudOperationClient(executor),
            invocationContext: _context,
          );

      final membership = await queries.getMy(
        MyCircleGroupMembershipQuery(circleId: 'circle-1', groupId: 'group-1'),
      );

      expect(membership.personaId, 'persona-2');
      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds
            .circleCircleGroupMembershipGetMyCircleGroupMembership,
      );
      expect(executor.context?.idempotencyKey, isNull);
    },
  );
}

CloudOperationInvocationContext _context(
  String clientPageId, {
  required bool command,
}) => CloudOperationInvocationContext(
  surfaceId: 'circleDetail',
  clientPageId: clientPageId,
  actor: const CloudOperationActorContext(personaId: 'persona-1'),
  idempotencyKey: command ? 'group-membership-contract' : null,
);
