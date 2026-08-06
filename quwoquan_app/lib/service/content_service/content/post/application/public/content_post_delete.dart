import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

String contentPostDeleteIdempotencyKey(String postId) {
  final normalized = postId.trim();
  if (normalized.isEmpty) {
    throw ArgumentError.value(postId, 'postId', 'must not be empty');
  }
  return 'content.post.delete:$normalized';
}

/// Post aggregate delete command seam. Wire encoding stays in the adapter.
abstract interface class ContentPostDeleteCommandWriter {
  Future<PostDeletionReceipt> deletePost({
    required String postId,
    required String idempotencyKey,
  });
}
