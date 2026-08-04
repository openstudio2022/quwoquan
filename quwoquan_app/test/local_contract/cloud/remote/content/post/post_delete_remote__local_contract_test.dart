// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/spec.md#sit-002

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/remote/content/post/post_delete_remote.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('DeletePost 仅走 generated owner 并透传 caller-owned 幂等身份', () async {
    final executor = _DeletePostExecutor();
    final writer = RemoteContentPostDeleteCommandWriter(
      client: GeneratedCloudOperationClient(executor),
      invocationContext: (clientPageId, idempotencyKey) =>
          CloudOperationInvocationContext(
            surfaceId: AppUiSurfaces.workBrowser.id,
            routeId: AppUiSurfaces.workBrowser.routeId,
            clientPageId: clientPageId,
            idempotencyKey: idempotencyKey,
            actor: const CloudOperationActorContext(personaId: 'persona-1'),
          ),
    );

    final receipt = await writer.deletePost(
      postId: ' post-1 ',
      idempotencyKey: ' delete-intent-1 ',
    );

    expect(
      executor.operation?.canonicalOperationId,
      AppCloudOperationIds.contentPostDeletePost,
    );
    expect(executor.context?.surfaceId, AppUiSurfaces.workBrowser.id);
    expect(executor.context?.clientPageId, ContentRequestPageIds.deletePost);
    expect(executor.context?.idempotencyKey, 'delete-intent-1');
    expect(executor.pathParameters, <String, String>{'postId': 'post-1'});
    expect(executor.body, isNull);
    expect(receipt.postId, 'post-1');
    expect(receipt.status, PostStatus.deleted);
    expect(receipt.replayed, isFalse);
  });

  test('DeletePost 在进入 generated executor 前拒绝空 identity', () async {
    final executor = _DeletePostExecutor();
    final writer = RemoteContentPostDeleteCommandWriter(
      client: GeneratedCloudOperationClient(executor),
      invocationContext: (_, _) => const CloudOperationInvocationContext(
        surfaceId: 'workBrowser',
        clientPageId: 'content.post.delete',
        actor: CloudOperationActorContext(personaId: 'persona-1'),
      ),
    );

    expect(
      () => writer.deletePost(postId: '', idempotencyKey: 'delete-intent-1'),
      throwsArgumentError,
    );
    expect(
      () => writer.deletePost(postId: 'post-1', idempotencyKey: ''),
      throwsArgumentError,
    );
    expect(executor.operation, isNull);
  });
}

final class _DeletePostExecutor implements CloudOperationExecutor {
  CloudOperationContract? operation;
  CloudOperationInvocationContext? context;
  Map<String, String>? pathParameters;
  Object? body;

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    final request = requestEncoder();
    this.operation = operation;
    this.context = context;
    pathParameters = request.pathParameters;
    body = request.body;
    return responseDecoder(<String, Object?>{
      'postId': 'post-1',
      'status': 'deleted',
      'replayed': false,
    });
  }
}
