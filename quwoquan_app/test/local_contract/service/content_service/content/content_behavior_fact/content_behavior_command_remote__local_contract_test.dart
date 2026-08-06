import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/adapters/content_behavior_command_remote.dart';
import 'package:quwoquan_app/runtime/transport/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'behavior report delegates to the ContentBehaviorFact operation',
    () async {
      final executor = _RecordingExecutor();
      final writer = RemoteContentBehaviorCommandAdapter(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: (clientPageId) => CloudOperationInvocationContext(
          surfaceId: 'workBrowser',
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(personaId: 'persona-1'),
        ),
      );

      await writer.reportBehaviors(
        ReportContentBehaviorsCommand(
          events: <ContentBehaviorEventWire>[
            ContentBehaviorEventWire(
              clientEventId: 'event-1',
              occurredAt: DateTime.utc(2026, 8, 3),
              contentId: 'post-1',
              action: BehaviorEventType.click,
            ),
          ],
        ),
      );

      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.contentContentBehaviorFactReportBehaviors,
      );
      expect(executor.operation?.objectId, 'content.content_behavior_fact');
      expect(
        executor.context?.clientPageId,
        ContentRequestPageIds.reportBehaviors,
      );
      expect(
        executor.context?.idempotencyKey,
        matches(RegExp(r'^behavior-batch-[0-9a-f]{64}$')),
      );
      expect(executor.body, <String, Object?>{
        'events': <Object?>[
          <String, Object?>{
            'clientEventId': 'event-1',
            'occurredAt': '2026-08-03T00:00:00.000Z',
            'contentId': 'post-1',
            'action': 'click',
          },
        ],
      });
    },
  );
}

final class _RecordingExecutor implements CloudOperationExecutor {
  CloudOperationContract? operation;
  CloudOperationInvocationContext? context;
  Object? body;

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    this.operation = operation;
    this.context = context;
    body = requestEncoder().body;
    return responseDecoder(<String, Object?>{
      'acceptedCount': 1,
      'replayedCount': 0,
    });
  }
}
