import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/circle_service/circle_management/circle/circle_operation_test_executor.dart';

void main() {
  test(
    'CircleGroup create uses generated typed ABI without actor fields',
    () async {
      final executor = CircleRecordingExecutor(
        response: circleGroupCommandResultFixture(),
      );
      final client = GeneratedCloudOperationClient(executor);

      final result = await client.circleCircleGroupCreateCircleGroup(
        CreateCircleGroupCommand(
          circleId: 'circle-1',
          groupType: CircleGroupType.selfBuilt,
          name: '远行同好',
          visibility: CircleGroupVisibility.private,
          joinPolicy: CircleGroupJoinPolicy.applyOnly,
          storageEnabled: true,
          noticeEnabled: false,
        ),
        context: const CloudOperationInvocationContext(
          surfaceId: 'circleDetail',
          clientPageId: 'circle.group.create',
          actor: CloudOperationActorContext(personaId: 'persona-1'),
          idempotencyKey: 'group-create-1',
        ),
      );

      expect(result.groupId, 'group-1');
      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.circleCircleGroupCreateCircleGroup,
      );
      expect(executor.body, isNot(contains('personaId')));
      expect(executor.body, isNot(contains('circleId')));
      expect(executor.pathParameters, <String, String>{'circleId': 'circle-1'});
    },
  );

  test('CircleGroup only uses If-Match for multi-writer snapshot updates', () {
    final update = encodeCircleCircleGroupUpdateCircleGroupGeneratedRequest(
      UpdateCircleGroupCommand(
        circleId: 'circle-1',
        groupId: 'group-1',
        expectedVersion: 7,
        name: '更新名称',
      ),
    );
    expect(update.headers, <String, String>{'If-Match': '"7"'});
    expect(update.body, <String, Object?>{'name': '更新名称'});

    final archive = encodeCircleCircleGroupArchiveCircleGroupGeneratedRequest(
      ArchiveCircleGroupCommand(circleId: 'circle-1', groupId: 'group-1'),
    );
    expect(archive.headers, isEmpty);
    expect(archive.body, isNull);
  });

  test('CircleGroup Reader rejects aggregate storage and audit aliases', () {
    expect(
      decodeCircleGroupSlice(circleGroupSliceFixture()).groupId,
      'group-1',
    );
    expect(
      // 拒绝 _id alias：未知/存储键不得进入 Reader 解码
      () => decodeCircleGroupSlice(
        circleGroupSliceFixture()..['_id'] = 'group-1',
      ),
      throwsFormatException,
    );
    expect(
      () => decodeCircleGroupSlice(
        circleGroupSliceFixture()..['createdByPersonaId'] = 'persona-1',
      ),
      throwsFormatException,
    );
  });
}
