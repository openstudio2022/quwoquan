import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/transport/generated/circle/circle_request_page_ids.g.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_behavior_fact/adapters/behavior_fact_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/circle_service/circle_management/circle/circle_operation_test_executor.dart';

void main() {
  test(
    'Remote appender binds the canonical operation and page context',
    () async {
      final executor = CircleRecordingExecutor(
        response: const <String, Object?>{
          'factId': 'cbf_remote_append',
          'idempotentReplay': false,
        },
      );
      final requestedPageIds = <String>[];
      final remote = RemoteCircleBehaviorFactWriter(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: (clientPageId) {
          requestedPageIds.add(clientPageId);
          return CloudOperationInvocationContext(
            surfaceId: 'circleDetail',
            clientPageId: clientPageId,
            actor: const CloudOperationActorContext(personaId: 'persona-1'),
            idempotencyKey: 'behavior-remote-1',
          );
        },
      );

      await remote.append(
        AppendCircleBehaviorFactCommand(
          circleId: 'circle-1',
          eventType: BehaviorEventType.impression,
        ),
      );

      expect(requestedPageIds, <String>[
        CircleRequestPageIds.reportCircleBehavior,
      ]);
      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.circleCircleBehaviorFactReportCircleBehavior,
      );
      expect(executor.context?.idempotencyKey, 'behavior-remote-1');
      expect(executor.body, <String, Object?>{
        'circleId': 'circle-1',
        'eventType': 'impression',
      });
    },
  );

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
