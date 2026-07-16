import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class TestContentPostReactionFacet implements ContentPostReactionFacet {
  final Map<String, bool> _liked = <String, bool>{};

  Object? throwOnCommand;
  int commandCallCount = 0;

  @override
  Future<ContentPostReactionStateSlice> getReactionState(
    GetContentPostReactionStateQuery query,
  ) async {
    final liked = _liked[query.postId] ?? false;
    return ContentPostReactionStateSlice(
      found: _liked.containsKey(query.postId),
      postId: query.postId,
      liked: liked,
      version: liked ? 1 : 0,
      updatedAt: liked ? DateTime.now().toUtc() : null,
    );
  }

  @override
  Future<ContentReactionCommandResult> likePost(
    LikeContentPostCommand command,
  ) => _change(command.postId, true);

  @override
  Future<ContentReactionCommandResult> unlikePost(
    UnlikeContentPostCommand command,
  ) => _change(command.postId, false);

  Future<ContentReactionCommandResult> _change(
    String postId,
    bool liked,
  ) async {
    commandCallCount++;
    final failure = throwOnCommand;
    if (failure != null) throw failure;
    final before = _liked[postId] ?? false;
    _liked[postId] = liked;
    return ContentReactionCommandResult(
      reactionId: 'test_post_reaction_$postId',
      postId: postId,
      version: before == liked ? 1 : 2,
      liked: liked,
      changed: before != liked,
      replayed: false,
    );
  }
}
