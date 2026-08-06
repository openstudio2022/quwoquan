import 'package:quwoquan_app/service/content_service/content/content_reaction/application/public/content_post_reaction_ports.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// alpha runner 专用 Post ContentReaction fixture Facet。
final class InMemoryContentPostReactionFacet
    implements ContentPostReactionPort {
  final Map<String, bool> _liked = <String, bool>{};

  @override
  Future<ContentReactionStateSlice> getReactionState(
    GetContentPostReactionStateQuery query,
  ) async {
    final liked = _liked[query.postId] ?? false;
    return ContentReactionStateSlice(
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
    final before = _liked[postId] ?? false;
    _liked[postId] = liked;
    return ContentReactionCommandResult(
      reactionId: 'fixture_post_reaction_$postId',
      postId: postId,
      version: before == liked ? 1 : 2,
      liked: liked,
      changed: before != liked,
      replayed: false,
    );
  }
}
