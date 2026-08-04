import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/circle/circle_management/circle_post_placement/adapters/post_placement_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../support/circle/circle_management/circle/circle_operation_test_executor.dart';

void main() {
  test(
    'CirclePostPlacement retries reuse a stable business idempotency key',
    () async {
      final executor = CircleRecordingExecutor(
        response: <String, Object?>{
          'placementId': 'placement-1',
          'version': 1,
          'state': 'active',
          'idempotentReplay': false,
        },
      );
      final contexts = <CloudOperationInvocationContext>[];
      final remote = RemoteCirclePostPlacementCommandWriter(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: (clientPageId, idempotencyKey) {
          final context = CloudOperationInvocationContext(
            surfaceId: 'createWorkspace',
            clientPageId: clientPageId,
            actor: const CloudOperationActorContext(personaId: 'persona-1'),
            idempotencyKey: idempotencyKey,
          );
          contexts.add(context);
          return context;
        },
      );
      final command = PlaceCirclePostCommand(
        circleId: 'circle-1',
        groupId: 'group-1',
        postId: 'post-1',
      );

      await remote.placePost(command);
      await remote.placePost(command);

      expect(contexts, hasLength(2));
      expect(contexts.first.idempotencyKey, contexts.last.idempotencyKey);
      expect(
        contexts.first.idempotencyKey,
        'circle-placement:circle-1:group-1:post-1',
      );
      expect(executor.body, <String, Object?>{
        'postId': 'post-1',
        'groupId': 'group-1',
      });
    },
  );

}
