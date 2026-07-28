// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/error-permission-display-semantics/spec.md#gwt-009
import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/analytics/analytics.dart';
import 'package:quwoquan_app/cloud/content/generated/content_errors.g.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/discovery/providers/discovery_feed_provider.dart';
import '../../../../../support/cloud_services/content_facet_overrides.dart';
import '../../../../../support/cloud_services/test_content_post_reaction_facet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';
import '../../../../../support/cloud_services/content/mock_content_repository.dart';

// ─── helpers ──────────────────────────────────────────────────────────────────

ProviderContainer _container(
  MockContentRepository repo, {
  AnalyticsService? analytics,
}) {
  return ProviderContainer(
    overrides: [
      ...mockContentFacetOverrides(repo),
      if (analytics != null) analyticsProvider.overrideWithValue(analytics),
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
      expect(feed!.blockingError, isA<CloudException>());
      final blockingError = feed.blockingError as CloudException;
      expect(blockingError.runtimeFailure, isNotNull);
      expect(
        blockingError.runtimeFailure.code,
        RuntimeFailureCodes.appSystemUnknownError,
      );
      expect(feed.staleDataError, isNull);
      expect(feed.appendError, isNull);
    });

    test('空缓存快照不能吞掉远端失败，首屏必须进入阻塞错误态', () async {
      final container = _container(_EmptyCacheFallbackContentRepository());
      addTearDown(container.dispose);

      await container.read(discoveryFeedMapProvider.notifier).load('photo');

      final feed = container.read(discoveryFeedMapProvider)['photo']?.value;
      expect(feed, isNotNull);
      expect(feed!.items, isEmpty);
      expect(feed.blockingError, isNotNull);
      expect(feed.staleDataError, isNull);
      expect(feed.appendError, isNull);
    });

    test('推荐初始成功空响应转为本地服务不可用阻塞态且不伪造 wire 字段', () async {
      final analytics = _CapturingAnalyticsService();
      final container = _container(
        _EmptyDiscoveryFeedContentRepository(),
        analytics: analytics,
      );
      addTearDown(container.dispose);

      await container.read(discoveryFeedMapProvider.notifier).load('recommend');

      final feed = container.read(discoveryFeedMapProvider)['recommend']?.value;
      expect(feed, isNotNull);
      expect(feed!.items, isEmpty);
      expect(feed.blockingError, isA<RuntimeFailure>());
      final failure = feed.blockingError! as RuntimeFailure;
      expect(failure.kind, RuntimeFailureKind.unavailable);
      expect(failure.code, ContentErrorCode.requiredDependencyUnavailable.code);
      expect(feed.feedRequestId, isNull);
      expect(feed.nextCursor, isNull);
      expect(feed.staleDataError, isNull);
      expect(feed.appendError, isNull);
      final reported = analytics.events.lastWhere(
        (event) =>
            event.eventName == 'page_lifecycle_state' &&
            event.properties['phase'] == 'blockingFailure',
      );
      expect(reported.properties['source'], 'localConsistency');
      expect(reported.properties['sourceCode'], failure.code);
      expect(reported.properties['failureKind'], 'unavailable');
      expect(reported.properties, isNot(contains('requestId')));
      expect(reported.properties, isNot(contains('traceId')));
    });

    test('following 初始成功空响应保留合法正常空态', () async {
      final container = _container(_EmptyDiscoveryFeedContentRepository());
      addTearDown(container.dispose);

      await container.read(discoveryFeedMapProvider.notifier).load('following');

      final feed = container.read(discoveryFeedMapProvider)['following']?.value;
      expect(feed, isNotNull);
      expect(feed!.items, isEmpty);
      expect(feed.blockingError, isNull);
      expect(feed.staleDataError, isNull);
      expect(feed.appendError, isNull);
      expect(feed.isLoading, isFalse);
    });

    test('appendNextPage 会在存在 nextCursor 时追加下一页并推进 cursor', () async {
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
      expect(afterFeed?.isLoading, isFalse);
      expect(afterFeed?.nextCursor, isNot(beforeFeed?.nextCursor));
      expect(afterFeed?.error, isNull);
    });

    test('分页 continuation end 保留已有数据并正常结束', () async {
      final container = _container(_EmptyContinuationContentRepository());
      addTearDown(container.dispose);
      final notifier = container.read(discoveryFeedMapProvider.notifier);

      await notifier.load('recommend');
      final before = container
          .read(discoveryFeedMapProvider)['recommend']!
          .value!;
      expect(before.items, isNotEmpty);
      expect(before.hasMore, isTrue);

      await notifier.appendNextPage('recommend');
      final after = container
          .read(discoveryFeedMapProvider)['recommend']!
          .value!;

      expect(after.items, before.items);
      expect(after.hasMore, isFalse);
      expect(after.blockingError, isNull);
      expect(after.staleDataError, isNull);
      expect(after.appendError, isNull);
    });

    test('分页失败保留已有数据并只写入 appendError', () async {
      final container = _container(_FailingAppendContentRepository());
      addTearDown(container.dispose);
      final notifier = container.read(discoveryFeedMapProvider.notifier);

      await notifier.load('recommend');
      final before = container
          .read(discoveryFeedMapProvider)['recommend']!
          .value!;
      await notifier.appendNextPage('recommend');
      final after = container
          .read(discoveryFeedMapProvider)['recommend']!
          .value!;

      expect(after.items, same(before.items));
      expect(after.appendError, isNotNull);
      expect(after.blockingError, isNull);
      expect(after.staleDataError, isNull);
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
        expect(after.items, same(seeded.items));
        expect(after.staleDataError, isNotNull);
        expect(after.blockingError, isNull);
        expect(after.appendError, isNull);
      },
    );

    test('推荐刷新返回空页时保留缓存并转为非阻断一致性失败', () async {
      final container = _container(_EmptyRefreshContentRepository());
      addTearDown(container.dispose);
      final notifier = container.read(discoveryFeedMapProvider.notifier);

      await notifier.load('recommend');
      final before = container
          .read(discoveryFeedMapProvider)['recommend']!
          .value!;
      expect(before.items, isNotEmpty);

      await notifier.load('recommend', force: true);
      final after = container
          .read(discoveryFeedMapProvider)['recommend']!
          .value!;

      expect(after.items, same(before.items));
      expect(after.blockingError, isNull);
      expect(after.staleDataError, isA<RuntimeFailure>());
      expect(
        (after.staleDataError! as RuntimeFailure).kind,
        RuntimeFailureKind.unavailable,
      );
      expect(after.appendError, isNull);
    });

    test(
      'cancelled load is absorbed without rendering an error state',
      () async {
        final container = _container(_CancelledContentRepository());
        addTearDown(container.dispose);

        await container.read(discoveryFeedMapProvider.notifier).load('photo');

        final feed = container.read(discoveryFeedMapProvider)['photo']?.value;
        expect(feed, isNotNull);
        expect(feed!.items, isEmpty);
        expect(feed.blockingError, isNull);
        expect(feed.staleDataError, isNull);
        expect(feed.appendError, isNull);
        expect(feed.isLoading, isFalse);
      },
    );

    test('缓存命中后台刷新时保留正文且不闪回首屏 loading', () async {
      final repo = _ControllableContentRepository();
      final container = _container(repo);
      addTearDown(container.dispose);

      final notifier = container.read(discoveryFeedMapProvider.notifier);
      await notifier.load('photo');
      final before = container.read(discoveryFeedMapProvider)['photo']!.value!;
      expect(before.items, isNotEmpty);

      repo.holdNextRequest = true;
      final refresh = notifier.load('photo', force: true);
      await container.pump();

      final during = container.read(discoveryFeedMapProvider)['photo']!.value!;
      expect(during.items, before.items);
      expect(during.isLoading, isFalse);

      repo.release();
      await refresh;
      expect(
        container.read(discoveryFeedMapProvider)['photo']!.value!.items,
        isNotEmpty,
      );
    });
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
    String? channelId,
    String? identity,
    String? type,
    String? subCategory,
    int limit = 20,
    String? cursor,
    String sort = kFeedSortRecommend,
    String? sessionId,
    String? feedRequestId,
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
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

class _CancelledContentRepository extends MockContentRepository {
  @override
  Future<DiscoveryFeedPage> listDiscoveryFeedPage({
    required String category,
    String? channelId,
    String? identity,
    String? type,
    String? subCategory,
    int limit = 20,
    String? cursor,
    String sort = kFeedSortRecommend,
    String? sessionId,
    String? feedRequestId,
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    throw const CloudOperationCancelledException();
  }
}

class _EmptyCacheFallbackContentRepository extends MockContentRepository {
  @override
  Future<DiscoveryFeedPage> listDiscoveryFeedPage({
    required String category,
    String? channelId,
    String? identity,
    String? type,
    String? subCategory,
    int limit = 20,
    String? cursor,
    String sort = kFeedSortRecommend,
    String? sessionId,
    String? feedRequestId,
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    return DiscoveryFeedPage(
      items: const <PostBaseDto>[],
      cacheFallbackError: StateError('remote_refresh_failed'),
      cacheAgeMs: 3000,
    );
  }
}

class _EmptyDiscoveryFeedContentRepository extends MockContentRepository {
  @override
  Future<DiscoveryFeedPage> listDiscoveryFeedPage({
    required String category,
    String? channelId,
    String? identity,
    String? type,
    String? subCategory,
    int limit = 20,
    String? cursor,
    String sort = kFeedSortRecommend,
    String? sessionId,
    String? feedRequestId,
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    return const DiscoveryFeedPage(items: <PostBaseDto>[]);
  }
}

class _EmptyContinuationContentRepository extends MockContentRepository {
  @override
  Future<DiscoveryFeedPage> listDiscoveryFeedPage({
    required String category,
    String? channelId,
    String? identity,
    String? type,
    String? subCategory,
    int limit = 20,
    String? cursor,
    String sort = kFeedSortRecommend,
    String? sessionId,
    String? feedRequestId,
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    if (cursor != null) {
      return const DiscoveryFeedPage(items: <PostBaseDto>[]);
    }
    final page = await super.listDiscoveryFeedPage(
      category: category,
      channelId: channelId,
      identity: identity,
      type: type,
      subCategory: subCategory,
      limit: limit,
      cursor: cursor,
      sort: sort,
      sessionId: sessionId,
      feedRequestId: feedRequestId,
      cancellation: cancellation,
      deadlineAt: deadlineAt,
    );
    return DiscoveryFeedPage(
      items: page.items.take(1).toList(growable: false),
      nextCursor: 'continuation-1',
      feedRequestId: page.feedRequestId,
      rankingVersion: page.rankingVersion,
      reasonVersion: page.reasonVersion,
    );
  }
}

class _FailingAppendContentRepository
    extends _EmptyContinuationContentRepository {
  @override
  Future<DiscoveryFeedPage> listDiscoveryFeedPage({
    required String category,
    String? channelId,
    String? identity,
    String? type,
    String? subCategory,
    int limit = 20,
    String? cursor,
    String sort = kFeedSortRecommend,
    String? sessionId,
    String? feedRequestId,
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    if (cursor != null) {
      throw Exception('append unavailable');
    }
    return super.listDiscoveryFeedPage(
      category: category,
      channelId: channelId,
      identity: identity,
      type: type,
      subCategory: subCategory,
      limit: limit,
      cursor: cursor,
      sort: sort,
      sessionId: sessionId,
      feedRequestId: feedRequestId,
      cancellation: cancellation,
      deadlineAt: deadlineAt,
    );
  }
}

class _EmptyRefreshContentRepository extends MockContentRepository {
  var _requestCount = 0;

  @override
  Future<DiscoveryFeedPage> listDiscoveryFeedPage({
    required String category,
    String? channelId,
    String? identity,
    String? type,
    String? subCategory,
    int limit = 20,
    String? cursor,
    String sort = kFeedSortRecommend,
    String? sessionId,
    String? feedRequestId,
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    _requestCount += 1;
    if (_requestCount > 1) {
      return const DiscoveryFeedPage(items: <PostBaseDto>[]);
    }
    return super.listDiscoveryFeedPage(
      category: category,
      channelId: channelId,
      identity: identity,
      type: type,
      subCategory: subCategory,
      limit: limit,
      cursor: cursor,
      sort: sort,
      sessionId: sessionId,
      feedRequestId: feedRequestId,
      cancellation: cancellation,
      deadlineAt: deadlineAt,
    );
  }
}

class _ControllableContentRepository extends MockContentRepository {
  bool holdNextRequest = false;
  Completer<DiscoveryFeedPage>? _pending;
  DiscoveryFeedPage? _heldPage;

  @override
  Future<DiscoveryFeedPage> listDiscoveryFeedPage({
    required String category,
    String? channelId,
    String? identity,
    String? type,
    String? subCategory,
    int limit = 20,
    String? cursor,
    String sort = kFeedSortRecommend,
    String? sessionId,
    String? feedRequestId,
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    final page = await super.listDiscoveryFeedPage(
      category: category,
      channelId: channelId,
      identity: identity,
      type: type,
      subCategory: subCategory,
      limit: limit,
      cursor: cursor,
      sort: sort,
      sessionId: sessionId,
      feedRequestId: feedRequestId,
      cancellation: cancellation,
      deadlineAt: deadlineAt,
    );
    if (!holdNextRequest) return page;
    holdNextRequest = false;
    _heldPage = page;
    _pending = Completer<DiscoveryFeedPage>();
    return _pending!.future;
  }

  void release() {
    _pending?.complete(_heldPage!);
  }
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

final class _CapturingAnalyticsService extends AnalyticsService {
  _CapturingAnalyticsService() : super.forTesting();

  final List<AnalyticsEvent> events = <AnalyticsEvent>[];

  @override
  Future<void> trackEvent(AnalyticsEvent event) async {
    events.add(event);
  }
}
