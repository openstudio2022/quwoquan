import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock.dart';
import 'package:test/test.dart';

void main() {
  test('alpha Comment Facet 与 production pure contract 同型', () async {
    final comments = AlphaContentCommentFacet(actorId: 'alpha-test-persona');

    final created = await comments.createComment(
      CreateContentCommentCommand(
        postId: 'alpha-contract-post',
        content: 'alpha typed comment',
        personaContextVersion: 1,
      ),
    );
    final page = await comments.listComments(postId: 'alpha-contract-post');

    expect(page.items.single.id, created.id);
    expect(page.items.single.content, 'alpha typed comment');
    expect(page.items.single.isAuthor, isTrue);

    final reaction = await comments.reactToComment(
      ReactToContentCommentCommand(
        commentId: created.id,
        reaction: ContentCommentReactionValue.like,
      ),
    );
    expect(reaction.reaction, ContentCommentReactionValue.like);
    expect(reaction.likeCount, 1);

    await expectLater(
      comments.deleteComment(
        DeleteContentCommentCommand(
          postId: 'alpha-contract-post',
          commentId: created.id,
          version: 99,
        ),
      ),
      throwsStateError,
    );
    final deleted = await comments.deleteComment(
      DeleteContentCommentCommand(
        postId: 'alpha-contract-post',
        commentId: created.id,
        version: created.version,
      ),
    );
    expect(deleted.status, ContentCommentStatus.deleted);
  });

  test('alpha Comment Facet 保留 canonical fixture 的根评论与回复分页语义', () async {
    final comments = AlphaContentCommentFacet();
    final page = await comments.listComments(
      postId: 'fixture_photo_001',
      limit: 100,
    );
    final byId = {for (final comment in page.items) comment.id: comment};

    // The fixture models six roots plus 176 replies. listComments reports
    // root pagination only; reply counts preserve the full 182-comment load.
    expect(page.total, 6);
    expect(byId['fixture_comment_thread_empty']?.replyCount, 0);
    expect(byId['fixture_comment_parent_001']?.replyCount, 1);
    expect(byId['fixture_comment_thread_five']?.replyCount, 5);
    expect(byId['fixture_comment_thread_ten']?.replyCount, 10);
    expect(byId['fixture_comment_thread_fifty']?.replyCount, 50);
    expect(byId['fixture_comment_thread_hundred']?.replyCount, 110);
    expect(
      page.items.fold<int>(0, (total, comment) => total + comment.replyCount),
      176,
    );
  });
}
