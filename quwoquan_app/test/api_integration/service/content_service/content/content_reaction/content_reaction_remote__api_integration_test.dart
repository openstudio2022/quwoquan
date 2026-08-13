// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/spec.md#gwt-006
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/spec.md#gwt-006.t1
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/spec.md#gwt-006.t2
// readiness_case: content_reaction_get_content_reaction_state_app_api
// readiness_case: content_reaction_like_post_app_api
// readiness_case: content_reaction_react_to_comment_app_api
// readiness_case: content_reaction_unlike_post_app_api

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/content_api_contract_harness.dart';

void main() {
  late ContentApiContractHarness owner;
  late ContentApiContractHarness reactor;
  var ownerCreated = false;
  var reactorCreated = false;

  setUpAll(() async {
    owner = await ContentApiContractHarness.create();
    ownerCreated = true;
    reactor = await ContentApiContractHarness.create();
    reactorCreated = true;
  });

  tearDownAll(() async {
    if (reactorCreated) {
      await reactor.close();
    }
    if (ownerCreated) {
      await owner.close();
    }
  });

  test(
    'production ContentReaction Remote 完成 Post like 与 Comment 三态闭环',
    () async {
      final sequence = DateTime.now().microsecondsSinceEpoch;
      final publication = await owner.publication.submitPostPublication(
        SubmitContentPostPublicationCommand(
          publishIntentId: 'reaction-post-$sequence',
          localDraftId: 'reaction-draft-$sequence',
          contentType: ContentType.micro,
          contentIdentity: ContentIdentity.moment,
          body: 'Reaction API contract post $sequence',
          visibility: Visibility.public,
        ),
      );
      final postId = publication.postId;
      String? commentId;

      try {
        final initial = await reactor.reactions.getReactionState(
          GetContentPostReactionStateQuery(postId: postId),
        );
        expect(initial.postId, postId);
        expect(initial.liked, isFalse);

        final likeCommand = LikeContentPostCommand(postId: postId);
        final liked = await reactor.withIdempotencyKey(
          'reaction-like-$sequence',
          () => reactor.reactions.likePost(likeCommand),
        );
        final likeReplay = await reactor.withIdempotencyKey(
          'reaction-like-$sequence',
          () => reactor.reactions.likePost(likeCommand),
        );
        expect(liked.postId, postId);
        expect(liked.liked, isTrue);
        expect(liked.replayed, isFalse);
        expect(likeReplay.reactionId, liked.reactionId);
        expect(likeReplay.version, liked.version);
        expect(likeReplay.liked, isTrue);
        expect(likeReplay.replayed, isTrue);

        final likedState = await _pollUntil(
          () => reactor.reactions.getReactionState(
            GetContentPostReactionStateQuery(postId: postId),
          ),
          (state) => state.liked,
          'liked projection',
        );
        expect(likedState.postId, postId);
        expect(likedState.found, isTrue);

        final unlikeCommand = UnlikeContentPostCommand(postId: postId);
        final unliked = await reactor.withIdempotencyKey(
          'reaction-unlike-$sequence',
          () => reactor.reactions.unlikePost(unlikeCommand),
        );
        final unlikeReplay = await reactor.withIdempotencyKey(
          'reaction-unlike-$sequence',
          () => reactor.reactions.unlikePost(unlikeCommand),
        );
        expect(unliked.postId, postId);
        expect(unliked.liked, isFalse);
        expect(unliked.replayed, isFalse);
        expect(unlikeReplay.reactionId, unliked.reactionId);
        expect(unlikeReplay.version, unliked.version);
        expect(unlikeReplay.replayed, isTrue);
        await _pollUntil(
          () => reactor.reactions.getReactionState(
            GetContentPostReactionStateQuery(postId: postId),
          ),
          (state) => !state.liked,
          'unliked projection',
        );

        final createdComment = await owner.withIdempotencyKey(
          'reaction-comment-$sequence',
          () => owner.comments.createComment(
            CreateContentCommentCommand(
              postId: postId,
              content: 'reaction target $sequence',
            ),
          ),
        );
        commentId = createdComment.id;

        for (final reaction in const <CommentReactionType>[
          CommentReactionType.like,
          CommentReactionType.dislike,
          CommentReactionType.none,
        ]) {
          final result = await reactor.withIdempotencyKey(
            'comment-reaction-${reaction.wireName}-$sequence',
            () => reactor.comments.reactToComment(
              ReactToContentCommentCommand(
                commentId: createdComment.id,
                reaction: reaction,
              ),
            ),
          );
          expect(result.reactionId, isNotEmpty);
          expect(result.reaction, reaction);
          expect(result.replayed, isFalse);
          expect(result.likeCount, greaterThanOrEqualTo(0));
          expect(result.dislikeCount, greaterThanOrEqualTo(0));

          final projected = await _pollUntil(
            () => reactor.comments.listComments(
              postId: postId,
              limit: 20,
              sort: CommentSort.latest,
            ),
            (page) => page.items.any(
              (item) =>
                  item.id == createdComment.id &&
                  item.viewerReaction == reaction &&
                  item.likeCount == result.likeCount &&
                  item.dislikeCount == result.dislikeCount,
            ),
            'comment ${reaction.wireName} projection',
          );
          final projectedComment = projected.items.firstWhere(
            (item) => item.id == createdComment.id,
          );
          expect(projectedComment.viewerReaction, reaction);
          expect(projectedComment.likeCount, result.likeCount);
          expect(projectedComment.dislikeCount, result.dislikeCount);
        }

        final deletedComment = await owner.withIdempotencyKey(
          'reaction-comment-delete-$sequence',
          () => owner.comments.deleteComment(
            DeleteContentCommentCommand(
              postId: postId,
              commentId: createdComment.id,
            ),
          ),
        );
        expect(deletedComment.status, CommentStatus.deleted);
        commentId = null;
      } finally {
        if (commentId != null) {
          await owner.withIdempotencyKey(
            'reaction-comment-clean-$sequence',
            () => owner.comments.deleteComment(
              DeleteContentCommentCommand(
                postId: postId,
                commentId: commentId!,
              ),
            ),
          );
        }
        await owner.postDeletion.deletePost(
          postId: postId,
          idempotencyKey: 'reaction-post-clean-$sequence',
        );
      }
    },
  );
}

Future<T> _pollUntil<T>(
  Future<T> Function() read,
  bool Function(T value) done,
  String label,
) async {
  final deadline = DateTime.now().add(const Duration(seconds: 12));
  while (true) {
    final value = await read();
    if (done(value)) {
      return value;
    }
    if (DateTime.now().isAfter(deadline)) {
      throw StateError('Timed out waiting for $label');
    }
    await Future<void>.delayed(const Duration(milliseconds: 250));
  }
}
