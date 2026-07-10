import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';

void main() {
  group('MockContentRepository 评论种子（contract fixture 同源）', () {
    test('展示流帖子返回两级评论：一级带 1 条回复预览 + 余量游标', () async {
      final repo = MockContentRepository();
      final page = await repo.listComments(
        postId: 'alpha_photo_landscape_single',
      );
      expect(page.items, isNotEmpty);

      final withReplies = page.items.where((c) => c.replyCount > 0).toList();
      expect(
        withReplies,
        isNotEmpty,
        reason: '展示流富线程必须含带二级回复的一级评论',
      );

      final parent = withReplies.firstWhere((c) => c.replyCount >= 5);
      expect(parent.replyPreview.length, 1, reason: '默认随列表回显 1 条回复预览');
      expect(parent.replyNextCursor, isNotNull, reason: '余量回复必须给出展开游标');
    });

    test('一级评论可分页展开二级回复，游标不重复预览项', () async {
      final repo = MockContentRepository();
      final page = await repo.listComments(
        postId: 'alpha_photo_landscape_single',
      );
      final parent = page.items.firstWhere((c) => c.replyCount >= 6);

      final firstExpand = await repo.listCommentReplies(
        postId: 'alpha_photo_landscape_single',
        commentId: parent.id,
        cursor: parent.replyNextCursor,
        limit: 5,
      );
      expect(firstExpand.items.length, 5, reason: '首次展开最多 5 条');
      expect(
        firstExpand.items.map((c) => c.id),
        isNot(contains(parent.replyPreview.single.id)),
        reason: '展开结果不得与预览项重复',
      );
    });

    test('发现流克隆帖归一到基础帖复用同一份评论种子', () async {
      final repo = MockContentRepository();
      final base = await repo.listComments(postId: 'd1');
      expect(base.items, isNotEmpty);

      final clone = await repo.listComments(postId: 'd1_photo_1');
      expect(
        clone.items.map((c) => c.id),
        equals(base.items.map((c) => c.id)),
        reason: '克隆帖 d1_photo_1 应复用 d1 的评论，避免评论区空白',
      );
    });

    test('无种子且无基础帖映射的帖子返回空评论页', () async {
      final repo = MockContentRepository();
      final page = await repo.listComments(postId: 'no_such_post_xyz');
      expect(page.items, isEmpty);
      expect(page.nextCursor, isNull);
    });
  });
}
