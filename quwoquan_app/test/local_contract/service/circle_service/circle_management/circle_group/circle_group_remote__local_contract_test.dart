import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_group/application/public/circle_group_ports.dart';
import 'package:quwoquan_app/runtime/di/circle_dependencies.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/circle_service/circle_management/circle/circle_operation_test_executor.dart';

void main() {
  test('composition exposes the canonical CircleGroup command port', () async {
    final executor = CircleRecordingExecutor(
      response: circleGroupCommandResultFixture(),
    );
    final commands =
        CircleProductionComposition.generatedAdapter<CircleGroupCommands>(
          CircleProductionAdapter.group,
          client: GeneratedCloudOperationClient(executor),
          invocationContext: _context,
        );

    final result = await commands.create(
      CreateCircleGroupCommand(
        circleId: 'circle-1',
        groupType: CircleGroupType.selfBuilt,
        name: '远行同好',
        visibility: CircleGroupVisibility.private,
        joinPolicy: CircleGroupJoinPolicy.applyOnly,
        storageEnabled: true,
        noticeEnabled: false,
      ),
    );

    expect(result.groupId, 'group-1');
    expect(
      executor.operation?.canonicalOperationId,
      AppCloudOperationIds.circleCircleGroupCreateCircleGroup,
    );
    expect(executor.context?.idempotencyKey, 'circle-group-contract');
  });

  test('composition exposes the canonical CircleGroup query port', () async {
    final executor = CircleRecordingExecutor(
      response: circleGroupSliceFixture(),
    );
    final queries =
        CircleProductionComposition.generatedAdapter<CircleGroupQueries>(
          CircleProductionAdapter.group,
          client: GeneratedCloudOperationClient(executor),
          invocationContext: _context,
        );

    final group = await queries.get(
      CircleGroupQuery(circleId: 'circle-1', groupId: 'group-1'),
    );

    expect(group.groupId, 'group-1');
    expect(
      executor.operation?.canonicalOperationId,
      AppCloudOperationIds.circleCircleGroupGetCircleGroup,
    );
    expect(executor.context?.idempotencyKey, isNull);
  });
}

CloudOperationInvocationContext _context(
  String clientPageId, {
  required bool command,
}) => CloudOperationInvocationContext(
  surfaceId: 'circleDetail',
  clientPageId: clientPageId,
  actor: const CloudOperationActorContext(personaId: 'persona-1'),
  idempotencyKey: command ? 'circle-group-contract' : null,
);
