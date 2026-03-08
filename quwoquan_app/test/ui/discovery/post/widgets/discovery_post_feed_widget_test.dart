import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/discovery/providers/discovery_feed_provider.dart';

// ─── helpers ──────────────────────────────────────────────────────────────────

ProviderContainer _container(ContentRepository repo) {
  return ProviderContainer(
    overrides: [contentRepositoryProvider.overrideWithValue(repo)],
  );
}

// ─── tests ────────────────────────────────────────────────────────────────────

void main() {
  group('DiscoveryFeedMapNotifier', () {
    test('initial state is empty map', () {
      final container = _container(MockContentRepository());
      addTearDown(container.dispose);
      final state = container.read(discoveryFeedMapProvider);
      expect(state, isEmpty);
    });

    test(
      'load(photo) populates feed items from MockContentRepository',
      () async {
        final container = _container(MockContentRepository());
        addTearDown(container.dispose);

        await container.read(discoveryFeedMapProvider.notifier).load('photo');

        final feedAsync = container.read(discoveryFeedMapProvider)['photo'];
        expect(feedAsync, isNotNull);
        final feed = feedAsync!.value;
        expect(feed, isNotNull);
        expect(feed!.items, isNotEmpty);
        expect(feed.items.first, isA<PhotoPostDto>());
      },
    );

    test('load(video) returns VideoPostDto items', () async {
      final container = _container(MockContentRepository());
      addTearDown(container.dispose);

      await container.read(discoveryFeedMapProvider.notifier).load('video');

      final feed = container.read(discoveryFeedMapProvider)['video']?.value;
      expect(feed, isNotNull);
      expect(feed!.items, isNotEmpty);
      expect(feed.items.first, isA<VideoPostDto>());
    });

    test('load error is captured in feed state without throwing', () async {
      final failRepo = _FailingContentRepository();
      final container = _container(failRepo);
      addTearDown(container.dispose);

      await container.read(discoveryFeedMapProvider.notifier).load('photo');

      final feed = container.read(discoveryFeedMapProvider)['photo']?.value;
      expect(feed, isNotNull);
      expect(feed!.error, isNotNull);
      expect(feed.error, contains('network_error'));
    });

    test('appendNextPage does nothing when nextCursor is null', () async {
      final container = _container(MockContentRepository());
      addTearDown(container.dispose);

      await container.read(discoveryFeedMapProvider.notifier).load('photo');
      final beforeCount =
          container
              .read(discoveryFeedMapProvider)['photo']
              ?.value
              ?.items
              .length ??
          0;

      await container
          .read(discoveryFeedMapProvider.notifier)
          .appendNextPage('photo');
      final afterCount =
          container
              .read(discoveryFeedMapProvider)['photo']
              ?.value
              ?.items
              .length ??
          0;

      // MockContentRepository returns nextCursor: null → no new items loaded
      expect(afterCount, equals(beforeCount));
    });
  });

  group('MockContentRepository', () {
    test('likePost increments likePostCallCount', () async {
      final mock = MockContentRepository();
      await mock.likePost(postId: 'p1');
      expect(mock.likePostCallCount, equals(1));
      await mock.likePost(postId: 'p2');
      expect(mock.likePostCallCount, equals(2));
    });

    test('likePost throws when throwOnLike is set', () async {
      final mock = MockContentRepository()
        ..throwOnLike = Exception('rate_limited');
      expect(() => mock.likePost(postId: 'p1'), throwsException);
    });

    test('createComment tracks call and returns comment map', () async {
      final mock = MockContentRepository();
      final result = await mock.createComment(postId: 'p1', content: '好图！');
      expect(mock.createCommentCallCount, equals(1));
      expect(mock.lastCommentText, equals('好图！'));
      expect(mock.lastCommentPostId, equals('p1'));
      expect(result['content'], equals('好图！'));
      expect(result['_id'], isNotNull);
    });

    test('createComment throws when throwOnCreateComment is set', () async {
      final mock = MockContentRepository()
        ..throwOnCreateComment = Exception('forbidden');
      expect(
        () => mock.createComment(postId: 'p1', content: 'test'),
        throwsException,
      );
    });

    test('getReactionState returns reactionStateStub', () async {
      final mock = MockContentRepository()
        ..reactionStateStub = {'liked': true, 'favorited': false};
      final state = await mock.getReactionState(postId: 'p1');
      expect(state['liked'], isTrue);
    });

    test('listComments reflects comments added via createComment', () async {
      final mock = MockContentRepository();
      await mock.createComment(postId: 'p1', content: 'first');
      await mock.createComment(postId: 'p1', content: 'second');
      final comments = await mock.listComments(postId: 'p1');
      expect(comments.items.length, equals(2));
      expect(comments.items[0].content, equals('first'));
      expect(comments.items[1].content, equals('second'));
    });
  });
}

// ─── test double ──────────────────────────────────────────────────────────────

class _FailingContentRepository extends MockContentRepository {
  @override
  Future<CursorPage<PostBaseDto>> listDiscoveryFeedPage({
    required String category,
    String? subCategory,
    int limit = 20,
    String? cursor,
    String sort = kFeedSortRecommend,
  }) async {
    throw Exception('network_error');
  }

  @override
  Future<List<PostBaseDto>> listDiscoveryFeed({
    required String category,
    String? subCategory,
    int limit = 20,
    String? cursor,
    String sort = kFeedSortRecommend,
  }) async => throw Exception('network_error');
}
