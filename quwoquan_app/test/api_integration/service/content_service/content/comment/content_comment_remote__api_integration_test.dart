// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/spec.md#gwt-007
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/spec.md#gwt-009
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/spec.md#gwt-012
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/spec.md#gwt-021
// readiness_case: comment_delete_comment_app_api
// readiness_case: comment_list_comments_by_author_app_api
// readiness_case: comment_list_comments_for_post_author_app_api
// readiness_case: comment_pin_comment_app_api
// readiness_case: comment_unpin_comment_app_api

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/content_api_contract_harness.dart';

void main() {
  late ContentApiContractHarness owner;
  late ContentApiContractHarness commenter;
  var ownerCreated = false;
  var commenterCreated = false;

  setUpAll(() async {
    owner = await ContentApiContractHarness.create();
    ownerCreated = true;
    commenter = await ContentApiContractHarness.create();
    commenterCreated = true;
  });

  tearDownAll(() async {
    if (commenterCreated) {
      await commenter.close();
    }
    if (ownerCreated) {
      await owner.close();
    }
  });

  test('production Comment Remote 完成创建重放、分页回读、置顶与删除闭环', () async {
    final sequence = DateTime.now().microsecondsSinceEpoch;
    final publication = await owner.publication.submitPostPublication(
      SubmitContentPostPublicationCommand(
        publishIntentId: 'comment-post-$sequence',
        localDraftId: 'comment-draft-$sequence',
        contentType: ContentType.micro,
        contentIdentity: ContentIdentity.moment,
        body: 'Comment API contract post $sequence',
        visibility: Visibility.public,
      ),
    );
    final postId = publication.postId;
    String? rootCommentId;
    String? replyCommentId;

    try {
      final rootCommand = CreateContentCommentCommand(
        postId: postId,
        content: 'root comment $sequence',
      );
      final root = await commenter.withIdempotencyKey(
        'comment-create-root-$sequence',
        () => commenter.comments.createComment(rootCommand),
      );
      final rootReplay = await commenter.withIdempotencyKey(
        'comment-create-root-$sequence',
        () => commenter.comments.createComment(rootCommand),
      );
      rootCommentId = root.id;
      expect(root.id, isNotEmpty);
      expect(root.status, CommentStatus.active);
      expect(root.replayed, isFalse);
      expect(rootReplay.id, root.id);
      expect(rootReplay.version, root.version);
      expect(rootReplay.status, root.status);
      expect(rootReplay.replayed, isTrue);

      final reply = await commenter.withIdempotencyKey(
        'comment-create-reply-$sequence',
        () => commenter.comments.createComment(
          CreateContentCommentCommand(
            postId: postId,
            content: 'reply comment $sequence',
            replyToCommentId: root.id,
          ),
        ),
      );
      replyCommentId = reply.id;
      expect(reply.id, isNotEmpty);
      expect(reply.status, CommentStatus.active);

      final postComments = await _pollUntil(
        () => owner.comments.listComments(
          postId: postId,
          limit: 20,
          sort: CommentSort.latest,
        ),
        (page) => page.items.any((item) => item.id == root.id),
        'root comment projection',
      );
      final projectedRoot = postComments.items.firstWhere(
        (item) => item.id == root.id,
      );
      expect(projectedRoot.postId, postId);
      expect(projectedRoot.content, rootCommand.content);
      expect(projectedRoot.status, CommentStatus.active);

      final replies = await _pollUntil(
        () => owner.comments.listReplies(
          postId: postId,
          commentId: root.id,
          limit: 20,
        ),
        (page) => page.items.any((item) => item.id == reply.id),
        'reply projection',
      );
      final projectedReply = replies.items.firstWhere(
        (item) => item.id == reply.id,
      );
      expect(projectedReply.postId, postId);
      expect(projectedReply.replyToCommentId, root.id);
      expect(projectedReply.replyToUserId, projectedRoot.authorId);
      expect(projectedReply.parentCommentId, root.id);

      final authored = await _pollUntil(
        () => commenter.comments.listByAuthor(limit: 20),
        (page) =>
            page.items.any((item) => item.id == root.id) &&
            page.items.any((item) => item.id == reply.id),
        'author comment projection',
      );
      final authoredRoot = authored.items.firstWhere(
        (item) => item.id == root.id,
      );
      final authoredReply = authored.items.firstWhere(
        (item) => item.id == reply.id,
      );
      expect(authoredRoot.postId, postId);
      expect(authoredRoot.parentCommentId, isNull);
      expect(authoredReply.postId, postId);
      expect(authoredReply.parentCommentId, root.id);

      final received = await _pollUntil(
        () => owner.comments.listReceived(limit: 20),
        (page) =>
            page.items.any((item) => item.id == root.id) &&
            page.items.any((item) => item.id == reply.id),
        'post author received projection',
      );
      final receivedRoot = received.items.firstWhere(
        (item) => item.id == root.id,
      );
      final receivedReply = received.items.firstWhere(
        (item) => item.id == reply.id,
      );
      expect(receivedRoot.postId, postId);
      expect(receivedRoot.parentCommentId, isNull);
      expect(receivedReply.postId, postId);
      expect(receivedReply.parentCommentId, root.id);

      final pin = await owner.withIdempotencyKey(
        'comment-pin-$sequence',
        () => owner.comments.pinComment(
          ChangeContentCommentPinCommand(postId: postId, commentId: root.id),
        ),
      );
      final pinReplay = await owner.withIdempotencyKey(
        'comment-pin-$sequence',
        () => owner.comments.pinComment(
          ChangeContentCommentPinCommand(postId: postId, commentId: root.id),
        ),
      );
      expect(pin.id, root.id);
      expect(pin.status, CommentStatus.active);
      expect(pin.replayed, isFalse);
      expect(pinReplay.id, pin.id);
      expect(pinReplay.version, pin.version);
      expect(pinReplay.replayed, isTrue);
      final unpin = await owner.withIdempotencyKey(
        'comment-unpin-$sequence',
        () => owner.comments.unpinComment(
          ChangeContentCommentPinCommand(postId: postId, commentId: root.id),
        ),
      );
      final unpinReplay = await owner.withIdempotencyKey(
        'comment-unpin-$sequence',
        () => owner.comments.unpinComment(
          ChangeContentCommentPinCommand(postId: postId, commentId: root.id),
        ),
      );
      expect(unpin.id, root.id);
      expect(unpin.version, greaterThan(pin.version));
      expect(unpin.replayed, isFalse);
      expect(unpinReplay.id, unpin.id);
      expect(unpinReplay.version, unpin.version);
      expect(unpinReplay.replayed, isTrue);

      final deletedReply = await commenter.withIdempotencyKey(
        'comment-delete-reply-$sequence',
        () => commenter.comments.deleteComment(
          DeleteContentCommentCommand(postId: postId, commentId: reply.id),
        ),
      );
      final deletedReplyReplay = await commenter.withIdempotencyKey(
        'comment-delete-reply-$sequence',
        () => commenter.comments.deleteComment(
          DeleteContentCommentCommand(postId: postId, commentId: reply.id),
        ),
      );
      expect(deletedReply.id, reply.id);
      expect(deletedReply.status, CommentStatus.deleted);
      expect(deletedReply.replayed, isFalse);
      expect(deletedReplyReplay.id, deletedReply.id);
      expect(deletedReplyReplay.version, deletedReply.version);
      expect(deletedReplyReplay.replayed, isTrue);
      replyCommentId = null;

      final deletedRoot = await commenter.withIdempotencyKey(
        'comment-delete-root-$sequence',
        () => commenter.comments.deleteComment(
          DeleteContentCommentCommand(postId: postId, commentId: root.id),
        ),
      );
      final deletedRootReplay = await commenter.withIdempotencyKey(
        'comment-delete-root-$sequence',
        () => commenter.comments.deleteComment(
          DeleteContentCommentCommand(postId: postId, commentId: root.id),
        ),
      );
      expect(deletedRoot.id, root.id);
      expect(deletedRoot.status, CommentStatus.deleted);
      expect(deletedRoot.replayed, isFalse);
      expect(deletedRootReplay.id, deletedRoot.id);
      expect(deletedRootReplay.version, deletedRoot.version);
      expect(deletedRootReplay.replayed, isTrue);
      rootCommentId = null;
    } finally {
      if (replyCommentId != null) {
        await commenter.withIdempotencyKey(
          'comment-clean-reply-$sequence',
          () => commenter.comments.deleteComment(
            DeleteContentCommentCommand(
              postId: postId,
              commentId: replyCommentId!,
            ),
          ),
        );
      }
      if (rootCommentId != null) {
        await commenter.withIdempotencyKey(
          'comment-clean-root-$sequence',
          () => commenter.comments.deleteComment(
            DeleteContentCommentCommand(
              postId: postId,
              commentId: rootCommentId!,
            ),
          ),
        );
      }
      await owner.postDeletion.deletePost(
        postId: postId,
        idempotencyKey: 'comment-clean-post-$sequence',
      );
    }
  });
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
