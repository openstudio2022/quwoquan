import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/circle_service/circle_management/circle/circle_operation_test_executor.dart';

void main() {
  test(
    'CircleBehaviorFact body cannot carry actor or session metadata',
    () async {
      // ReportCircleBehavior 返回 typed AppendResult，decoder fail-closed：
      // executor 必须回放 canonical 回执 wire。
      final executor = CircleRecordingExecutor(
        response: const <String, Object?>{
          'factId': 'cbf_generated_abi',
          'idempotentReplay': false,
        },
      );
      final client = GeneratedCloudOperationClient(executor);

      await client.circleCircleBehaviorFactReportCircleBehavior(
        AppendCircleBehaviorFactCommand(
          circleId: 'circle-1',
          eventType: BehaviorEventType.effectivePlay,
        ),
        context: const CloudOperationInvocationContext(
          surfaceId: 'circleDetail',
          clientPageId: 'circle.behaviors.report',
          actor: CloudOperationActorContext(personaId: 'persona-1'),
          idempotencyKey: 'behavior-1',
        ),
      );

      expect(executor.body, <String, Object?>{
        'circleId': 'circle-1',
        'eventType': 'effective_play',
      });
      expect(executor.body, isNot(contains('personaId')));
      expect(executor.body, isNot(contains('sessionId')));
      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.circleCircleBehaviorFactReportCircleBehavior,
      );
    },
  );

}
