import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/content_service/content/comment/in_memory_content_comment_facet.dart';

void main() {
  group('ContentCommentFacet', () {
    test('列表按 hot/latest 服务端同构顺序且始终 pinned-first', () async {
      final facet = InMemoryContentCommentFacet(
        items: <CommentListItem>[
          testCommentItem(
            id: 'latest',
            createdAt: DateTime.utc(2026, 7, 14, 10),
          ),
          testCommentItem(
            id: 'pinned',
            isPinned: true,
            pinnedAt: DateTime.utc(2026, 7, 14, 8),
            createdAt: DateTime.utc(2026, 7, 14, 8),
          ),
          testCommentItem(id: 'older', createdAt: DateTime.utc(2026, 7, 14, 9)),
          testCommentItem(
            id: 'popular',
            createdAt: DateTime.utc(2026, 7, 14, 7),
            likeCount: 20,
          ),
        ],
      );

      final hot = await facet.listComments(postId: 'post_1');
      final latest = await facet.listComments(
        postId: 'post_1',
        sort: CommentSort.latest,
      );

      expect(hot.items.map((item) => item.id), <String>[
        'pinned',
        'popular',
        'latest',
        'older',
      ]);
      expect(latest.items.map((item) => item.id), <String>[
        'pinned',
        'latest',
        'older',
        'popular',
      ]);
    });

    test('创建、查询投影回读和服务端版本删除同源', () async {
      final facet = InMemoryContentCommentFacet();
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
      expect(deleted.status, CommentStatus.deleted);
      expect((await facet.listComments(postId: 'post_1')).items, isEmpty);
    });

    test('回复与反应均为强类型', () async {
      final root = testCommentItem(
        id: 'root',
        authorId: 'author',
        createdAt: DateTime.now().toUtc().subtract(const Duration(minutes: 1)),
      );
      final earlierReply = testCommentItem(
        id: 'reply-earlier',
        postId: 'post_1',
        parentCommentId: 'root',
        createdAt: DateTime.utc(2026, 7, 14, 7),
      );
      final facet = InMemoryContentCommentFacet(
        items: <CommentListItem>[root, earlierReply],
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
      expect(replies.items.map((item) => item.id), <String>[
        'reply-earlier',
        replyResult.id,
      ]);
      expect(replies.items.last.parentCommentId, 'root');

      final reaction = await facet.reactToComment(
        ReactToContentCommentCommand(
          commentId: 'root',
          reaction: CommentReactionType.like,
        ),
      );
      expect(reaction.reaction, CommentReactionType.like);
      expect(reaction.likeCount, 1);
    });
  });
}
