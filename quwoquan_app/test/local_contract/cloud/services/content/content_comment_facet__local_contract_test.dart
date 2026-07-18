import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';

import '../../../../support/cloud_services/test_content_comment_facet.dart';

void main() {
  group('ContentCommentFacet', () {
    test('列表只有 pinned-first + createdAt 单一顺序', () async {
      final facet = TestContentCommentFacet(
        items: <ContentCommentListItem>[
          testCommentItem(
            id: 'latest',
            createdAt: DateTime.utc(2026, 7, 14, 10),
          ),
          testCommentItem(
            id: 'pinned',
            isPinned: true,
            createdAt: DateTime.utc(2026, 7, 14, 8),
          ),
          testCommentItem(id: 'older', createdAt: DateTime.utc(2026, 7, 14, 9)),
        ],
      );

      final page = await facet.listComments(postId: 'post_1');

      expect(page.items.map((item) => item.id), <String>[
        'pinned',
        'latest',
        'older',
      ]);
    });

    test('创建、查询投影回读和服务端版本删除同源', () async {
      final facet = TestContentCommentFacet();
      final created = await facet.createComment(
        CreateContentCommentCommand(
          postId: 'post_1',
          content: '新建评论',
          authorDisplayNameSnapshot: '测试账号',
          personaContextVersion: 4,
        ),
      );

      final page = await facet.listComments(postId: 'post_1');
      expect(page.items.single.id, created.id);
      expect(page.items.single.content, '新建评论');
      expect(page.items.single.personaContextVersion, 4);

      final deleted = await facet.deleteComment(
        DeleteContentCommentCommand(postId: 'post_1', commentId: created.id),
      );
      expect(deleted.status, ContentCommentStatus.deleted);
      expect((await facet.listComments(postId: 'post_1')).items, isEmpty);
    });

    test('回复与反应均为强类型', () async {
      final root = testCommentItem(
        id: 'root',
        authorId: 'author',
        createdAt: DateTime.now().toUtc().subtract(const Duration(minutes: 1)),
      );
      final facet = TestContentCommentFacet(
        items: <ContentCommentListItem>[root],
      );
      final replyResult = await facet.createComment(
        CreateContentCommentCommand(
          postId: 'post_1',
          content: '二级回复',
          replyToCommentId: 'root',
        ),
      );
      final replies = await facet.listReplies(
        postId: 'post_1',
        commentId: 'root',
      );
      expect(replies.items.single.id, replyResult.id);
      expect(replies.items.single.parentCommentId, 'root');

      final reaction = await facet.reactToComment(
        ReactToContentCommentCommand(
          commentId: 'root',
          reaction: ContentCommentReactionValue.like,
        ),
      );
      expect(reaction.reaction, ContentCommentReactionValue.like);
      expect(reaction.likeCount, 1);
    });
  });
}
