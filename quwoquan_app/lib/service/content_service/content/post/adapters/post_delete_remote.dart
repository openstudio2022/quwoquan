import 'package:quwoquan_app/runtime/transport/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_delete.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ContentPostDeleteInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId,
      String idempotencyKey,
    );

/// Content Post 删除命令的唯一 Remote owner。
final class RemoteContentPostDeleteCommandWriter
    implements ContentPostDeleteCommandWriter {
  const RemoteContentPostDeleteCommandWriter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final ContentPostDeleteInvocationContextFactory invocationContext;

  @override
  Future<PostDeletionReceipt> deletePost({
    required String postId,
    required String idempotencyKey,
  }) {
    final normalizedPostId = postId.trim();
    final normalizedIdempotencyKey = idempotencyKey.trim();
    if (normalizedPostId.isEmpty || normalizedIdempotencyKey.isEmpty) {
      throw ArgumentError(
        'DeletePost requires postId and caller-owned idempotencyKey',
      );
    }
    return client.contentPostDeletePost(
      DeletePostCommand(postId: normalizedPostId),
      context: invocationContext(
        ContentRequestPageIds.deletePost,
        normalizedIdempotencyKey,
      ),
    );
  }
}
