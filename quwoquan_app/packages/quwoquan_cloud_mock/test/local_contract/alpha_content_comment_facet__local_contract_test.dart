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

    final deleted = await comments.deleteComment(
      DeleteContentCommentCommand(
        postId: 'alpha-contract-post',
        commentId: created.id,
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

  test('alpha Comment Facet 与 hot/latest 及回复升序契约同构', () async {
    final comments = AlphaContentCommentFacet(actorId: 'alpha-test-persona');
    final popular = await comments.createComment(
      CreateContentCommentCommand(
        postId: 'alpha-sort-post',
        content: '高互动旧评论',
        personaContextVersion: 1,
      ),
    );
    final latest = await comments.createComment(
      CreateContentCommentCommand(
        postId: 'alpha-sort-post',
        content: '低互动新评论',
        personaContextVersion: 1,
      ),
    );
    await comments.reactToComment(
      ReactToContentCommentCommand(
        commentId: popular.id,
        reaction: ContentCommentReactionValue.like,
      ),
    );

    final hot = await comments.listComments(postId: 'alpha-sort-post');
    final latestPage = await comments.listComments(
      postId: 'alpha-sort-post',
      sort: ContentCommentSort.latest,
    );
    expect(hot.items.map((item) => item.id), <String>[popular.id, latest.id]);
    expect(latestPage.items.map((item) => item.id), <String>[
      latest.id,
      popular.id,
    ]);

    final firstReply = await comments.createComment(
      CreateContentCommentCommand(
        postId: 'alpha-sort-post',
        content: '第一条回复',
        replyToCommentId: popular.id,
        personaContextVersion: 1,
      ),
    );
    final secondReply = await comments.createComment(
      CreateContentCommentCommand(
        postId: 'alpha-sort-post',
        content: '第二条回复',
        replyToCommentId: popular.id,
        personaContextVersion: 1,
      ),
    );
    final replies = await comments.listReplies(
      postId: 'alpha-sort-post',
      commentId: popular.id,
    );
    expect(replies.items.map((item) => item.id), <String>[
      firstReply.id,
      secondReply.id,
    ]);
  });
}
