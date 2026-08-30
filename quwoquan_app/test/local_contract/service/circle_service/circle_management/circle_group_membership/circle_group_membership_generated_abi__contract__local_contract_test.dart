import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/circle_service/circle_management/circle/circle_operation_test_executor.dart';

void main() {
  test('CircleGroupMembership commands use generated typed ABI', () async {
    final executor = CircleRecordingExecutor(
      response: circleGroupMembershipCommandResultFixture(),
    );
    final client = GeneratedCloudOperationClient(executor);

    final result = await client
        .circleCircleGroupMembershipApproveCircleGroupMember(
          DecideCircleGroupMembershipCommand(
            circleId: 'circle-1',
            groupId: 'group-1',
            personaId: 'persona-2',
          ),
          context: const CloudOperationInvocationContext(
            surfaceId: 'circleDetail',
            clientPageId: 'circle.group.members.approve',
            actor: CloudOperationActorContext(personaId: 'persona-owner'),
            idempotencyKey: 'approve-1',
          ),
        );

    expect(result.state, CircleGroupMembershipState.active);
    expect(executor.pathParameters, <String, String>{
      'circleId': 'circle-1',
      'groupId': 'group-1',
      'personaId': 'persona-2',
    });
    expect(executor.headers, isEmpty);
    expect(executor.body, isNull);
    expect(
      executor.operation?.canonicalOperationId,
      AppCloudOperationIds.circleCircleGroupMembershipApproveCircleGroupMember,
    );
  });

  test('CircleGroupMembership Reader rejects userId and decision actor', () {
    expect(
      decodeCircleGroupMembershipSlice(circleGroupMembershipSliceFixture())
          .personaId,
      'persona-2',
    );
    expect(
      () => decodeCircleGroupMembershipSlice(
        circleGroupMembershipSliceFixture()
          ..remove('personaId')
          ..['userId'] = 'persona-2',
      ),
      throwsFormatException,
    );
    expect(
      () => decodeCircleGroupMembershipSlice(
        circleGroupMembershipSliceFixture()
          ..['decidedByPersonaId'] = 'persona-owner',
      ),
      throwsFormatException,
    );
  });
}
