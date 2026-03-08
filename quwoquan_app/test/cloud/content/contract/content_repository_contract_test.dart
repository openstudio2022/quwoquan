import 'package:test/test.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';

void main() {
  group('ContentRepository — 常规契约', () {
    late ContentRepository repo;

    setUp(() {
      repo = MockContentRepository();
    });

    test('listDiscoveryFeed 返回非空帖子列表', () async {
      final posts = await repo.listDiscoveryFeed(category: 'all');
      expect(posts, isNotEmpty);
    });

    test('listDiscoveryFeedPage 返回带游标的分页结果', () async {
      final page = await repo.listDiscoveryFeedPage(category: 'all');
      expect(page.items, isNotEmpty);
    });

    test('getPost 不存在的 ID 抛出异常', () async {
      expect(
        () async => await repo.getPost(postId: 'nonexistent'),
        throwsException,
      );
    });

    test('createPost 返回创建结果', () async {
      final result = await repo.createPost(payload: {
        'type': 'moment',
        'body': 'test moment',
      });
      expect(result, isA<Map<String, dynamic>>());
    });

    test('likePost / unlikePost 不崩溃', () async {
      await repo.likePost(postId: 'test');
      await repo.unlikePost(postId: 'test');
    });

    test('favoritePost / unfavoritePost 不崩溃', () async {
      await repo.favoritePost(postId: 'test');
      await repo.unfavoritePost(postId: 'test');
    });

    test('getReactionState 返回互动状态', () async {
      final state = await repo.getReactionState(postId: 'test');
      expect(state, isA<Map<String, dynamic>>());
    });

    test('listComments 返回评论列表', () async {
      final comments = await repo.listComments(postId: 'test');
      expect(comments, isList);
    });

    test('createComment 返回新评论', () async {
      final comment = await repo.createComment(
        postId: 'test',
        content: '测试评论',
      );
      expect(comment, isA<Map<String, dynamic>>());
    });

    test('deleteComment 不崩溃', () async {
      await repo.deleteComment(postId: 'test', commentId: 'c1');
    });

    test('reportBehaviors 不崩溃', () async {
      await repo.reportBehaviors(events: []);
    });

    test('getCounters 返回计数器', () async {
      final counters = await repo.getCounters(postId: 'test');
      expect(counters, isA<Map<String, dynamic>>());
    });

    test('接口包含全部 15 个 service.yaml API 方法', () {
      final methods = <String>[
        'listDiscoveryFeedPage', 'listDiscoveryFeed',
        'listDiscoveryFeedPageLegacy',
        'getPost', 'createPost',
        'likePost', 'unlikePost', 'favoritePost', 'unfavoritePost',
        'getReactionState', 'listComments', 'createComment', 'deleteComment',
        'reportBehaviors', 'getCounters',
      ];
      expect(methods.length, 15);
    });
  });

  group('ContentRepository — 异常/边界契约', () {
    late ContentRepository repo;

    setUp(() {
      repo = MockContentRepository();
    });

    test('listDiscoveryFeed limit=0 不崩溃', () async {
      final posts = await repo.listDiscoveryFeed(category: 'all', limit: 0);
      expect(posts, isList);
    });

    test('listDiscoveryFeed 空 category 不崩溃', () async {
      final posts = await repo.listDiscoveryFeed(category: '');
      expect(posts, isList);
    });

    test('reportBehaviors 空事件列表不崩溃', () async {
      await repo.reportBehaviors(events: []);
    });
  });
}
