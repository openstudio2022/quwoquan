import 'content_operation_contracts.g.dart';

abstract interface class ContentPostReactionQuery {
  Future<ContentReactionStateSlice> getReactionState(
    GetContentPostReactionStateQuery query,
  );
}

abstract interface class ContentPostReactionCommandWriter {
  Future<ContentReactionCommandResult> likePost(LikeContentPostCommand command);

  Future<ContentReactionCommandResult> unlikePost(
    UnlikeContentPostCommand command,
  );
}

abstract interface class ContentPostReactionFacet
    implements ContentPostReactionQuery, ContentPostReactionCommandWriter {}
