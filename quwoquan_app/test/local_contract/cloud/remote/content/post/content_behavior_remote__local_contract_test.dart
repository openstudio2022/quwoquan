import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/remote/content/post/content_behavior_remote.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
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
              contentId: 'post-1',
              eventType: 'effective_play',
              timestamp: '2026-07-29T00:00:00Z',
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
      expect(executor.body, <String, Object?>{
        'events': <Object?>[
          <String, Object?>{
            'contentId': 'post-1',
            'eventType': 'effective_play',
            'timestamp': '2026-07-29T00:00:00Z',
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
    return responseDecoder(null);
  }
}
