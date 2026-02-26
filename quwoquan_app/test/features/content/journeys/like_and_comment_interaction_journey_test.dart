/// L1c Journey Tests: 点赞 & 评论互动旅程
///
/// 守护：
///   旅程 B1：点赞 → MockRepo.likePostCallCount +1 → countersStub 更新
///   旅程 B2：点赞时抛异常 → likeCount 不变（回滚语义由上层状态管理保证）
///   旅程 C1：发表评论 → MockRepo.createCommentCallCount +1 → commentsStub 增加
///   旅程 C2：评论失败 → 错误抛出，调用计数不变
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';

void main() {
  group('Like Interaction Journey', () {
    test('旅程 B1：连续点赞两个帖子 → likePostCallCount == 2', () async {
      final mock = MockContentRepository();

      await mock.likePost(postId: 'post_001');
      await mock.likePost(postId: 'post_002');

      expect(mock.likePostCallCount, equals(2));
      expect(mock.countersStubLikeCount, equals(2),
          reason: '每次 likePost 都应增加 countersStubLikeCount');
    });

    test('旅程 B2：取消点赞后重新点赞 → 计数正确', () async {
      final mock = MockContentRepository();

      await mock.likePost(postId: 'post_001');
      expect(mock.likePostCallCount, equals(1));

      // unlikePost 也使用 likePostCallCount 计数器（记录所有 like 相关交互）
      await mock.unlikePost(postId: 'post_001');
      expect(mock.likePostCallCount, equals(2));

      await mock.likePost(postId: 'post_001');
      expect(mock.likePostCallCount, equals(3));
    });

    test('旅程 B3：throwOnLike 注入 → likePost 抛出，状态管理层应感知到异常', () async {
      final mock = MockContentRepository()
        ..throwOnLike = Exception('CONTENT.USER.rate_limited');

      expect(
        () async => mock.likePost(postId: 'post_001'),
        throwsException,
      );
      // 关键：抛出前 callCount 已记录（方便追踪调用次数调试）
      expect(mock.likePostCallCount, equals(1));
    });

    test('旅程 B4：favoritePost → counters stub 更新', () async {
      final mock = MockContentRepository();

      await mock.favoritePost(postId: 'post_001');

      final counters = await mock.getCounters(postId: 'post_001');
      expect(counters['likeCount'], isNotNull);
    });
  });

  group('Comment Interaction Journey', () {
    test('旅程 C1：发表评论 → createCommentCallCount +1 + lastCommentText 正确', () async {
      final mock = MockContentRepository();

      final result = await mock.createComment(
        postId: 'post_001',
        content: '这张图真漂亮！',
      );

      expect(mock.createCommentCallCount, equals(1));
      expect(mock.lastCommentText, equals('这张图真漂亮！'));
      expect(mock.lastCommentPostId, equals('post_001'));
      expect(result['content'], equals('这张图真漂亮！'));
      expect(result['_id'], isNotNull);
    });

    test('旅程 C2：评论带 replyToCommentId → result 中包含该字段', () async {
      final mock = MockContentRepository();

      final result = await mock.createComment(
        postId: 'post_001',
        content: '回复你的评论',
        replyToCommentId: 'comment_parent_001',
      );

      expect(result['replyToCommentId'], equals('comment_parent_001'));
    });

    test('旅程 C3：连续发表 3 条评论 → listComments 返回 3 条', () async {
      final mock = MockContentRepository();

      await mock.createComment(postId: 'p1', content: '第一条');
      await mock.createComment(postId: 'p1', content: '第二条');
      await mock.createComment(postId: 'p1', content: '第三条');

      final comments = await mock.listComments(postId: 'p1');
      expect(comments.length, equals(3));
      expect(comments[2]['content'], equals('第三条'));
      expect(mock.countersStubCommentCount, equals(3));
    });

    test('旅程 C4：throwOnCreateComment → 抛出异常，commentsStub 不增加', () async {
      final mock = MockContentRepository()
        ..throwOnCreateComment = Exception('CONTENT.USER.rate_limited');

      final beforeCount = (await mock.listComments(postId: 'p1')).length;

      expect(
        () async => mock.createComment(postId: 'p1', content: 'fail'),
        throwsException,
      );

      final afterCount = (await mock.listComments(postId: 'p1')).length;
      expect(afterCount, equals(beforeCount),
          reason: '失败后 commentsStub 不应增加');
    });

    test('旅程 C5：deleteComment → commentsStub 减少', () async {
      final mock = MockContentRepository();
      final comment = await mock.createComment(postId: 'p1', content: '待删除');
      final commentId = comment['_id'] as String;

      await mock.deleteComment(postId: 'p1', commentId: commentId);

      final remaining = await mock.listComments(postId: 'p1');
      expect(remaining, isEmpty);
    });
  });

  group('Behavior Report Journey', () {
    test('旅程 D1：reportBehaviors 不抛异常（fire-and-forget）', () async {
      final mock = MockContentRepository();
      await expectLater(
        mock.reportBehaviors(events: [
          {'postId': 'p1', 'type': 'impression', 'feedPosition': 0},
          {'postId': 'p1', 'type': 'dwell', 'dwellMs': 12000},
        ]),
        completes,
      );
    });
  });
}
