import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class ContentReactionMutationEvidence {
  const ContentReactionMutationEvidence({
    required this.idempotencyKey,
    required this.mutationBasis,
    required this.expectedVersion,
  });
  final String idempotencyKey;
  final String mutationBasis;
  final int expectedVersion;
}

abstract interface class ContentPostReactionReader {
  Future<ContentReactionStateSlice> getReactionState(
    GetContentPostReactionStateQuery query,
  );
}

abstract interface class ContentPostReactionWriter {
  Future<ContentReactionCommandResult> likePost(LikeContentPostCommand command);
  Future<ContentReactionCommandResult> unlikePost(
    UnlikeContentPostCommand command,
  );
}

abstract interface class ContentPostReactionDurableWriter {
  Future<ContentReactionCommandResult> likePostWithEvidence(
    String postId, {
    required ContentReactionMutationEvidence evidence,
  });
  Future<ContentReactionCommandResult> unlikePostWithEvidence(
    String postId, {
    required ContentReactionMutationEvidence evidence,
  });
  Future<ContentReactionCommandRecoverySlice> recoverPost(
    String postId, {
    required String operation,
    required String idempotencyKey,
  });
  Future<ContentReactionCommandRecoverySlice> finalizeExpiredPost(
    String postId, {
    required String operation,
    required ContentReactionMutationEvidence evidence,
  });
}

abstract interface class ContentPostReactionPort
    implements ContentPostReactionReader, ContentPostReactionWriter {}
