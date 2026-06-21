/// T1 契约：MockContentRepository.getCommentCountsDelta 半开区间 (since, watermark]
/// 语义、软删计数、currentTotal 权威口径，以及 listComments.totalCount 排除软删的回归。
///
/// 对齐云侧语义（service.yaml GetCommentCountsDelta）：
/// - createdSinceCount = createdAt ∈ (since, watermark]（不论其后是否删除）
/// - deletedSinceCount = status=deleted 且 deletedAt ∈ (since, watermark]
/// - currentTotal = 权威「当前非删」总数
/// - watermark = 本次查询时刻，作为下次 since，保证相邻 delta 不重不漏
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';

CommentDto _comment({
  required String id,
  required DateTime createdAt,
  String postId = 'delta-post',
  String status = 'visible',
  DateTime? deletedAt,
}) {
  return CommentDto(
    id: id,
    postId: postId,
    authorId: 'author_$id',
    content: 'content_$id',
    status: status,
    createdAt: createdAt,
    deletedAt: deletedAt,
  );
}

void main() {
  group('getCommentCountsDelta — 半开区间 (since, watermark] 语义', () {
    test('首同步 since=null：无下界，统计全部 createdAt<=watermark', () async {
      final repo = MockContentRepository()
        ..commentsStub = [
          _comment(id: 'c1', createdAt: DateTime.utc(2026, 6, 1)),
          _comment(id: 'c2', createdAt: DateTime.utc(2026, 6, 2)),
        ];

      final delta = await repo.getCommentCountsDelta(
        postId: 'delta-post',
        since: null,
      );

      expect(delta.createdSinceCount, 2);
      expect(delta.deletedSinceCount, 0);
      expect(delta.currentTotal, 2);
      expect(delta.since, isNull);
    });

    test('下界 since 严格排他：since==createdAt 不计入，since-1ms 计入', () async {
      final repo = MockContentRepository()
        ..commentsStub = [
          _comment(id: 'c1', createdAt: DateTime.utc(2026, 6, 10)),
        ];

      final exclusive = await repo.getCommentCountsDelta(
        postId: 'delta-post',
        since: DateTime.utc(2026, 6, 10),
      );
      expect(exclusive.createdSinceCount, 0, reason: '下界排他：point > since');

      final inclusive = await repo.getCommentCountsDelta(
        postId: 'delta-post',
        since: DateTime.utc(2026, 6, 10).subtract(const Duration(milliseconds: 1)),
      );
      expect(inclusive.createdSinceCount, 1);
    });

    test('上界 watermark 含闭：晚于 watermark（未来）的评论不计入', () async {
      final repo = MockContentRepository()
        ..commentsStub = [
          _comment(
            id: 'future',
            createdAt: DateTime.now().add(const Duration(days: 1)),
          ),
        ];

      final delta = await repo.getCommentCountsDelta(
        postId: 'delta-post',
        since: null,
      );
      expect(delta.createdSinceCount, 0, reason: '上界：point <= watermark');
      expect(delta.currentTotal, 1, reason: '未来评论仍是当前非删总数');
    });

    test('相邻两次 since=上次 watermark：新增精确不重复计数', () async {
      final repo = MockContentRepository()
        ..commentsStub = [
          _comment(id: 'c_old', createdAt: DateTime.utc(2026, 6, 1)),
        ];

      final first = await repo.getCommentCountsDelta(
        postId: 'delta-post',
        since: null,
      );
      expect(first.createdSinceCount, 1);
      final watermark1 = first.watermark;

      await Future<void>.delayed(const Duration(milliseconds: 5));
      repo.commentsStub = [
        ...repo.commentsStub,
        _comment(id: 'c_new', createdAt: DateTime.now()),
      ];
      await Future<void>.delayed(const Duration(milliseconds: 5));

      final second = await repo.getCommentCountsDelta(
        postId: 'delta-post',
        since: watermark1,
      );
      expect(
        second.createdSinceCount,
        1,
        reason: '只统计 c_new；c_old<=watermark1 不被相邻窗口重复计入',
      );
      expect(second.currentTotal, 2);
    });
  });

  group('getCommentCountsDelta — 软删与 currentTotal 口径', () {
    test('deletedSinceCount 半开：deletedAt 区间内才计入', () async {
      final repo = MockContentRepository()
        ..commentsStub = [
          _comment(
            id: 'd1',
            createdAt: DateTime.utc(2026, 6, 1),
            status: 'deleted',
            deletedAt: DateTime.utc(2026, 6, 10),
          ),
        ];

      final exclusive = await repo.getCommentCountsDelta(
        postId: 'delta-post',
        since: DateTime.utc(2026, 6, 10),
      );
      expect(exclusive.deletedSinceCount, 0);

      final inclusive = await repo.getCommentCountsDelta(
        postId: 'delta-post',
        since: DateTime.utc(2026, 6, 10).subtract(const Duration(milliseconds: 1)),
      );
      expect(inclusive.deletedSinceCount, 1);
      expect(inclusive.createdSinceCount, 0, reason: 'createdAt 06-01<=since 不计新增');
      expect(inclusive.currentTotal, 0, reason: '软删不计入权威总数');
    });

    test('createdSinceCount 计入区间内新增——即使其后被删除', () async {
      final repo = MockContentRepository()
        ..commentsStub = [
          _comment(
            id: 'cd',
            createdAt: DateTime.utc(2026, 6, 10),
            status: 'deleted',
            deletedAt: DateTime.utc(2026, 6, 11),
          ),
        ];

      final delta = await repo.getCommentCountsDelta(
        postId: 'delta-post',
        since: DateTime.utc(2026, 6, 9),
      );
      expect(delta.createdSinceCount, 1, reason: '新增计数不受其后删除影响');
      expect(delta.deletedSinceCount, 1);
      expect(delta.currentTotal, 0);
    });

    test('deleteComment 软删墓碑：counts 与列表同步反映', () async {
      final repo = MockContentRepository()
        ..commentsStub = [
          _comment(id: 'k1', createdAt: DateTime.utc(2026, 6, 1)),
          _comment(id: 'k2', createdAt: DateTime.utc(2026, 6, 2)),
        ];

      await repo.deleteComment(postId: 'delta-post', commentId: 'k2');

      final page = await repo.listComments(postId: 'delta-post');
      expect(page.totalCount, 1);
      expect(page.items.single.id, 'k1');

      final delta = await repo.getCommentCountsDelta(
        postId: 'delta-post',
        since: DateTime.utc(2026, 6, 1),
      );
      expect(delta.createdSinceCount, 1, reason: 'k2 06-02>since；k1 06-01==since 排他');
      expect(delta.deletedSinceCount, 1, reason: 'k2 deletedAt≈now 落在区间内');
      expect(delta.currentTotal, 1);
    });
  });

  group('listComments.totalCount 排除软删（回归）与 currentTotal 一致', () {
    test('listComments 不展示软删项且 totalCount==currentTotal', () async {
      final repo = MockContentRepository()
        ..commentsStub = [
          _comment(id: 'v1', createdAt: DateTime.utc(2026, 6, 1)),
          _comment(id: 'v2', createdAt: DateTime.utc(2026, 6, 2)),
          _comment(
            id: 'gone',
            createdAt: DateTime.utc(2026, 6, 3),
            status: 'deleted',
            deletedAt: DateTime.utc(2026, 6, 4),
          ),
        ];

      final page = await repo.listComments(postId: 'delta-post');
      expect(page.totalCount, 2);
      expect(page.items.length, 2);
      expect(page.items.any((c) => c.id == 'gone'), isFalse);

      final delta = await repo.getCommentCountsDelta(
        postId: 'delta-post',
        since: null,
      );
      expect(delta.currentTotal, 2);
      expect(page.totalCount, delta.currentTotal, reason: 'listComments 与 delta 计数恒一致');
    });
  });
}
