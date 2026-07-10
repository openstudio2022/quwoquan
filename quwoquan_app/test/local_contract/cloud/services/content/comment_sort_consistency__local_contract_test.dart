import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';

void main() {
  group('MockContentRepository 评论排序契约（与云侧 sortCommentsByMode 同源）', () {
    const postId = 'fixture_photo_001';

    Future<List<String>> idsForSort(MockContentRepository repo, String sort) async {
      final page = await repo.listComments(postId: postId, sort: sort, limit: 100);
      return page.items.map((c) => c.id).toList(growable: false);
    }

    test('综合/最新/最多赞返回同一评论集合与同一总数（换序不换集）', () async {
      final repo = MockContentRepository();
      final recommended = await idsForSort(repo, 'recommended');
      final latest = await idsForSort(repo, 'latest');
      final mostLiked = await idsForSort(repo, 'most_liked');

      expect(recommended, isNotEmpty);
      expect(latest.length, recommended.length);
      expect(mostLiked.length, recommended.length);
      expect(latest.toSet(), recommended.toSet(),
          reason: '最新与综合必须是同一评论集合');
      expect(mostLiked.toSet(), recommended.toSet(),
          reason: '最多赞与综合必须是同一评论集合');
    });

    test('置顶评论在所有排序下都排第一', () async {
      final repo = MockContentRepository();
      for (final sort in const ['recommended', 'latest', 'most_liked']) {
        final page = await repo.listComments(postId: postId, sort: sort, limit: 100);
        final pinnedIndex = page.items.indexWhere((c) => c.isPinned);
        if (pinnedIndex >= 0) {
          expect(pinnedIndex, 0,
              reason: '置顶评论在 $sort 排序下必须排第一');
          expect(page.items.first.isPinned, isTrue);
        }
      }
    });

    test('最多赞排序首条（非置顶段）按点赞量降序', () async {
      final repo = MockContentRepository();
      final page = await repo.listComments(postId: postId, sort: 'most_liked', limit: 100);
      final nonPinned = page.items.where((c) => !c.isPinned).toList();
      for (var i = 1; i < nonPinned.length; i++) {
        expect(
          nonPinned[i - 1].likeCount >= nonPinned[i].likeCount,
          isTrue,
          reason: '最多赞排序非置顶段必须点赞量单调不增',
        );
      }
    });

    test('综合排序多次拉取顺序确定（无漂移）', () async {
      final repo = MockContentRepository();
      final first = await idsForSort(repo, 'recommended');
      for (var i = 0; i < 10; i++) {
        final again = await idsForSort(repo, 'recommended');
        expect(again, first, reason: '综合排序顺序必须可重复，不得漂移');
      }
    });
  });
}
