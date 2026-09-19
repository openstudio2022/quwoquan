import 'package:quwoquan_app/runtime/transport/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/service/content_service/content/content_reaction/application/public/content_post_reaction_ports.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ContentPostReactionInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      required bool command,
    });

final class RemoteContentPostReactionFacet
    implements ContentPostReactionPort, ContentPostReactionDurableWriter {
  const RemoteContentPostReactionFacet({
    required this.client,
    required this.invocationContext,
  });
  final GeneratedCloudOperationClient client;
  final ContentPostReactionInvocationContextFactory invocationContext;
  @override
  Future<ContentReactionStateSlice> getReactionState(
    GetContentPostReactionStateQuery query,
  ) => client.contentContentReactionGetContentReactionState(
    query,
    context: invocationContext(
      ContentRequestPageIds.getContentReactionState,
      command: false,
    ),
  );
  @override
  Future<ContentReactionCommandResult> likePost(
    LikeContentPostCommand command,
  ) => client.contentContentReactionLikePost(
    command,
    context: invocationContext(ContentRequestPageIds.likePost, command: true),
  );
  @override
  Future<ContentReactionCommandResult> unlikePost(
    UnlikeContentPostCommand command,
  ) => client.contentContentReactionUnlikePost(
    command,
    context: invocationContext(ContentRequestPageIds.unlikePost, command: true),
  );
  @override
  Future<ContentReactionCommandResult> likePostWithEvidence(
    String postId, {
    required ContentReactionMutationEvidence evidence,
  }) => client.contentContentReactionLikePost(
    LikeContentPostCommand(
      postId: postId,
      mutationBasis: evidence.mutationBasis,
      expectedVersion: evidence.expectedVersion,
    ),
    context: _withIdempotency(
      invocationContext(ContentRequestPageIds.likePost, command: true),
      evidence.idempotencyKey,
    ),
  );
  @override
  Future<ContentReactionCommandResult> unlikePostWithEvidence(
    String postId, {
    required ContentReactionMutationEvidence evidence,
  }) => client.contentContentReactionUnlikePost(
    UnlikeContentPostCommand(
      postId: postId,
      mutationBasis: evidence.mutationBasis,
      expectedVersion: evidence.expectedVersion,
    ),
    context: _withIdempotency(
      invocationContext(ContentRequestPageIds.unlikePost, command: true),
      evidence.idempotencyKey,
    ),
  );
  @override
  Future<ContentReactionCommandRecoverySlice> recoverPost(
    String postId, {
    required String operation,
    required String idempotencyKey,
  }) => client.contentContentReactionRecoverContentReactionCommand(
    RecoverContentReactionCommandQuery(
      targetKind: ContentReactionTargetKind.post,
      targetId: postId,
      operation: operation,
    ),
    context: _withIdempotency(
      invocationContext(
        ContentRequestPageIds.recoverContentReactionCommand,
        command: false,
      ),
      idempotencyKey,
    ),
  );
  @override
  Future<ContentReactionCommandRecoverySlice> finalizeExpiredPost(
    String postId, {
    required String operation,
    required ContentReactionMutationEvidence evidence,
  }) => client.contentContentReactionFinalizeExpiredContentReactionCommand(
    FinalizeExpiredContentReactionCommand(
      targetKind: ContentReactionTargetKind.post,
      targetId: postId,
      operation: operation,
      mutationBasis: evidence.mutationBasis,
      expectedVersion: evidence.expectedVersion,
    ),
    context: _withIdempotency(
      invocationContext(
        ContentRequestPageIds.finalizeExpiredContentReactionCommand,
        command: true,
      ),
      evidence.idempotencyKey,
    ),
  );
  CloudOperationInvocationContext _withIdempotency(
    CloudOperationInvocationContext base,
    String key,
  ) => CloudOperationInvocationContext(
    surfaceId: base.surfaceId,
    clientPageId: base.clientPageId,
    routeId: base.routeId,
    actor: base.actor,
    referralSource: base.referralSource,
    feedRequestId: base.feedRequestId,
    shareId: base.shareId,
    modelId: base.modelId,
    experimentBucket: base.experimentBucket,
    idempotencyKey: key,
    deadlineAt: base.deadlineAt,
    cancellation: base.cancellation,
  );
}
