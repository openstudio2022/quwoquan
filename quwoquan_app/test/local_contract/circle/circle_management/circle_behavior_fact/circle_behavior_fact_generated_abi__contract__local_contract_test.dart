import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../support/circle/circle_management/circle/circle_operation_test_executor.dart';

void main() {
  test(
    'CircleBehaviorFact body cannot carry actor or session metadata',
    () async {
      final executor = CircleRecordingExecutor();
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
