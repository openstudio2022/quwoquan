import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/circle_service/circle_management/circle/circle_operation_test_executor.dart';

void main() {
  test(
    'CircleMembership commands use operation-specific generated ABI',
    () async {
      final executor = CircleRecordingExecutor(response: circleMembershipCommandResultFixture());
      final client = GeneratedCloudOperationClient(executor);
      const context = CloudOperationInvocationContext(
        surfaceId: 'circleDetail',
        clientPageId: 'circle.join',
        actor: CloudOperationActorContext(personaId: 'persona-1'),
        idempotencyKey: 'idem-1',
      );

      final result = await client.circleCircleMembershipJoinCircle(
        JoinCircleMembershipCommand(circleId: 'circle-1'),
        context: context,
      );

      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.circleCircleMembershipJoinCircle,
      );
      expect(executor.pathParameters, <String, String>{'circleId': 'circle-1'});
      expect(executor.body, isNull);
      expect(result.role, CircleMemberRole.member);
      expect(result.state, CircleMembershipState.active);
    },
  );

  test('LeaveCircle is a server-owned state transition without If-Match', () {
    final payload = encodeCircleCircleMembershipLeaveCircleGeneratedRequest(
      LeaveCircleMembershipCommand(circleId: 'circle-1'),
    );

    expect(payload.pathParameters, <String, String>{'circleId': 'circle-1'});
    expect(payload.headers, isEmpty);
    expect(payload.body, isNull);
  });

  test(
    'CircleMembership self query strictly decodes persona identity',
    () async {
      final executor = CircleRecordingExecutor(response: circleMembershipSliceFixture());
      final client = GeneratedCloudOperationClient(executor);

      final membership = await client
          .circleCircleMembershipGetMyCircleMembership(
            MyCircleMembershipQuery(circleId: 'circle-1'),
            context: const CloudOperationInvocationContext(
              surfaceId: 'circleDetail',
              clientPageId: 'circle.members.self',
              actor: CloudOperationActorContext(personaId: 'persona-1'),
            ),
          );

      expect(membership.personaId, 'persona-1');
      expect(membership.version, 7);
      expect(executor.body, isNull);
      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.circleCircleMembershipGetMyCircleMembership,
      );
    },
  );

  test('CircleMembership decoder rejects userId alias and unknown fields', () {
    final alias = circleMembershipSliceFixture()
      ..remove('personaId')
      ..['userId'] = 'persona-1';
    expect(() => decodeCircleMembershipSlice(alias), throwsFormatException);

    final unknown = circleMembershipSliceFixture()..['displayName'] = 'compat alias';
    expect(() => decodeCircleMembershipSlice(unknown), throwsFormatException);
  });

}
