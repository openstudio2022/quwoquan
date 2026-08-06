import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        ContentReactionCommandResult,
        ContentReactionStateSlice,
        GetContentPostReactionStateQuery,
        LikeContentPostCommand,
        UnlikeContentPostCommand;

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

/// 需要同时读取并改变同一 post 反应状态的对象级公开边界。
abstract interface class ContentPostReactionPort
    implements ContentPostReactionReader, ContentPostReactionWriter {}
