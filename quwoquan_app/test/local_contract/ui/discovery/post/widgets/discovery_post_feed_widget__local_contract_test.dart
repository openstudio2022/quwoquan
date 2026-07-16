import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/discovery/providers/discovery_feed_provider.dart';
import '../../../../../support/cloud_services/content_facet_overrides.dart';
import '../../../../../support/cloud_services/test_content_post_reaction_facet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

// ─── helpers ──────────────────────────────────────────────────────────────────

ProviderContainer _container(MockContentRepository repo) {
  return ProviderContainer(
    overrides: [
      ...mockContentFacetOverrides(repo),
      postInteractionStateProvider.overrideWith(
        _NoopPostInteractionStateNotifier.new,
      ),
    ],
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
      expect(feed.error, '操作失败，请稍后重试');
      expect(feed.blockingError, isNotNull);
      expect(feed.staleDataError, isNull);
      expect(feed.appendError, isNull);
    });

    test('appendNextPage 会在存在 nextCursor 时追加下一页并清空 cursor', () async {
      final container = _container(MockContentRepository());
      addTearDown(container.dispose);

      await container.read(discoveryFeedMapProvider.notifier).load('photo');
      final beforeFeed = container
          .read(discoveryFeedMapProvider)['photo']
          ?.value;
      final beforeCount = beforeFeed?.items.length ?? 0;
      expect(beforeFeed?.hasMore, isTrue);

      await container
          .read(discoveryFeedMapProvider.notifier)
          .appendNextPage('photo');
      final afterFeed = container
          .read(discoveryFeedMapProvider)['photo']
          ?.value;
      final afterCount = afterFeed?.items.length ?? 0;

      expect(afterCount, greaterThan(beforeCount));
      expect(afterFeed?.hasMore, isFalse);
      expect(afterFeed?.error, isNull);
    });

    test(
      'load with cached items keeps staleDataError and preserves items',
      () async {
        final container = _container(MockContentRepository());
        addTearDown(container.dispose);

        await container.read(discoveryFeedMapProvider.notifier).load('photo');
        final seeded = container
            .read(discoveryFeedMapProvider)['photo']!
            .value!;
        expect(seeded.items, isNotEmpty);

        final notifier = container.read(discoveryFeedMapProvider.notifier);
        notifier.state = <String, AsyncValue<DiscoveryFeedState>>{
          'photo': AsyncData(
            seeded.copyWith(
              nextCursor: 'cursor_1',
              blockingError: null,
              staleDataError: null,
              appendError: null,
            ),
          ),
        };

        container.updateOverrides([
          ...mockContentFacetOverrides(_FailingContentRepository()),
          postInteractionStateProvider.overrideWith(
            _NoopPostInteractionStateNotifier.new,
          ),
        ]);
        addTearDown(container.pump);
        await container.pump();

        await notifier.load('photo', force: true);
        final after = container.read(discoveryFeedMapProvider)['photo']!.value!;
        expect(after.items, isNotEmpty);
        expect(after.staleDataError, isNotNull);
        expect(after.blockingError, isNull);
        expect(after.appendError, isNull);
      },
    );
  });

  group('ContentPostReactionFacet', () {
    test('like/unlike command 与 query 使用同一 typed Facet', () async {
      final reactions = TestContentPostReactionFacet();
      await reactions.likePost(LikeContentPostCommand(postId: 'p1'));
      expect(reactions.commandCallCount, equals(1));
      expect(
        (await reactions.getReactionState(
          GetContentPostReactionStateQuery(postId: 'p1'),
        )).liked,
        isTrue,
      );
      await reactions.unlikePost(UnlikeContentPostCommand(postId: 'p1'));
      expect(reactions.commandCallCount, equals(2));
    });

    test('command 失败不伪造成功状态', () async {
      final reactions = TestContentPostReactionFacet()
        ..throwOnCommand = Exception('rate_limited');
      expect(
        () => reactions.likePost(LikeContentPostCommand(postId: 'p1')),
        throwsException,
      );
      expect(reactions.commandCallCount, 1);
      expect(
        (await reactions.getReactionState(
          GetContentPostReactionStateQuery(postId: 'p1'),
        )).liked,
        isFalse,
      );
    });
  });
}

// ─── test double ──────────────────────────────────────────────────────────────

class _FailingContentRepository extends MockContentRepository {
  @override
  Future<DiscoveryFeedPage> listDiscoveryFeedPage({
    required String category,
    String? identity,
    String? type,
    String? subCategory,
    int limit = 20,
    String? cursor,
    String sort = kFeedSortRecommend,
    String? sessionId,
    String? feedRequestId,
  }) async {
    throw Exception('network_error');
  }

  @override
  Future<List<PostBaseDto>> listDiscoveryFeed({
    required String category,
    String? identity,
    String? type,
    String? subCategory,
    int limit = 20,
    String? cursor,
    String sort = kFeedSortRecommend,
  }) async => throw Exception('network_error');
}

class _NoopPostInteractionStateNotifier extends PostInteractionStateNotifier {
  @override
  PostInteractionState build() => const PostInteractionState();

  @override
  void applyConfirmedPosts(Iterable<PostBaseDto> posts) {
    final nextConfirmedShareCounts = Map<String, int>.from(
      state.confirmedShareCounts,
    );
    final nextConfirmedCommentCounts = Map<String, int>.from(
      state.confirmedCommentCounts,
    );
    final nextPendingCommentDeltas = Map<String, int>.from(
      state.pendingCommentDeltas,
    );
    for (final post in posts) {
      if (post.id.trim().isEmpty) {
        continue;
      }
      nextConfirmedShareCounts[post.id] = post.shareCount;
      nextConfirmedCommentCounts[post.id] = post.commentCount;
      nextPendingCommentDeltas.remove(post.id);
    }
    state = state.copyWith(
      confirmedShareCounts: nextConfirmedShareCounts,
      confirmedCommentCounts: nextConfirmedCommentCounts,
      pendingCommentDeltas: nextPendingCommentDeltas,
    );
  }
}
