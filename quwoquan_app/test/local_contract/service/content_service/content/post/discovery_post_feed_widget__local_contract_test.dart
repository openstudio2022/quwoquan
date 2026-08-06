// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/error-permission-display-semantics/spec.md#gwt-009
// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/spec.md#sit-002
// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-002
import 'dart:async';

import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/observability/analytics.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/application/public/discovery_feed_page.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/application/public/discovery_feed_query.dart'
    show kFeedSortRecommend;
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/post_interaction_state.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/discovery_feed_provider.dart';
import '../../../../../support/service/content_service/content/post/content_facet_overrides.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';
import '../../../../../support/service/content_service/content/post/mock_content_repository.dart';

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
        expect(feed.items.first, isA<ContentPostViewData>());
        expect(feed.items.first.type, 'image');
      },
    );

    test('load(video) returns canonical video presentation items', () async {
      final container = _container(MockContentRepository());
      addTearDown(container.dispose);

      await container.read(discoveryFeedMapProvider.notifier).load('video');

      final feed = container.read(discoveryFeedMapProvider)['video']?.value;
      expect(feed, isNotNull);
      expect(feed!.items, isNotEmpty);
      expect(feed.items.first, isA<ContentPostViewData>());
      expect(feed.items.first.type, 'video');
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

    test('推荐初始空响应缺 canonical empty envelope 时转为本地协议阻塞态', () async {
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
      expect(failure.kind, RuntimeFailureKind.contract);
      expect(failure.code, RuntimeFailureCodes.appContractInvalidResponse);
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
      expect(reported.properties['failureKind'], 'contract');
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
      expect(feed.isRefreshing, isFalse);
      expect(feed.isAppending, isFalse);
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

    test('分页远端失败命中 QuerySnapshot 时追加可见缓存但不伪报在线成功', () async {
      final analytics = _CapturingAnalyticsService();
      final container = _container(
        _CachedContinuationFallbackContentRepository(),
        analytics: analytics,
      );
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

      expect(after.items.length, greaterThan(before.items.length));
      expect(after.appendError, isA<CloudException>());
      expect(after.blockingError, isNull);
      expect(after.staleDataError, isNull);
      final appendTerminal = analytics.events.lastWhere(
        (event) => event.eventName == 'list_append_state',
      );
      expect(appendTerminal.properties['result'], 'cacheFallback');
      expect(appendTerminal.properties['copyKey'], 'appendFailedRetry');
      expect(appendTerminal.properties['sourceCode'], isNotNull);
      final cacheTerminal = analytics.events.lastWhere(
        (event) =>
            event.eventName == 'page_lifecycle_state' &&
            event.properties['phase'] == 'cacheFallback',
      );
      expect(cacheTerminal.properties['source'], 'cache');
      expect(cacheTerminal.properties['hasCache'], isTrue);
      expect(cacheTerminal.properties['cacheAgeMs'], 5000);
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

    test('推荐刷新返回非法空页时保留缓存并转为非阻断协议失败', () async {
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
        RuntimeFailureKind.contract,
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

    test('推荐首屏在 6000ms 取消 transport 并进入唯一超时终态', () {
      fakeAsync((async) {
        final repo = _NeverCompletingContentRepository();
        final container = _container(repo);
        addTearDown(container.dispose);

        unawaited(
          container.read(discoveryFeedMapProvider.notifier).load('recommend'),
        );
        async.flushMicrotasks();

        expect(repo.cancellation, isNotNull);
        expect(repo.deadlineAt, isNotNull);
        expect(
          repo.deadlineAt!.difference(repo.requestedAt!).inMilliseconds,
          inInclusiveRange(5900, 6100),
        );

        async.elapse(const Duration(milliseconds: 5999));
        async.flushMicrotasks();
        final beforeDeadline = container
            .read(discoveryFeedMapProvider)['recommend']!
            .value!;
        expect(beforeDeadline.isLoading, isTrue);
        expect(beforeDeadline.blockingError, isNull);
        expect(repo.cancellation!.isCancelled, isFalse);

        async.elapse(const Duration(milliseconds: 1));
        async.flushMicrotasks();
        final afterDeadline = container
            .read(discoveryFeedMapProvider)['recommend']!
            .value!;
        expect(repo.cancellation!.isCancelled, isTrue);
        expect(afterDeadline.isLoading, isFalse);
        expect(afterDeadline.blockingError, isA<CloudException>());
        expect(
          (afterDeadline.blockingError! as CloudException).runtimeFailure.kind,
          RuntimeFailureKind.timeout,
        );
        expect(afterDeadline.staleDataError, isNull);
        expect(afterDeadline.appendError, isNull);
        expect(afterDeadline.isRefreshing, isFalse);
        expect(afterDeadline.isAppending, isFalse);
      });
    });

    test('新首刷 supersede 旧请求，旧 transport 即使晚返回也不得回写', () async {
      final repo = _SupersedingContentRepository();
      final container = _container(repo);
      addTearDown(container.dispose);
      final notifier = container.read(discoveryFeedMapProvider.notifier);

      final first = notifier.load('photo', force: true);
      await container.pump();
      expect(repo.requests, hasLength(1));

      final second = notifier.load('photo', force: true);
      await container.pump();
      expect(repo.requests, hasLength(2));
      expect(repo.requests.first.cancellation?.isCancelled, isTrue);

      repo.complete(1, feedRequestId: 'feed-request-new');
      await second;
      expect(
        container.read(discoveryFeedMapProvider)['photo']!.value!.feedRequestId,
        'feed-request-new',
      );

      repo.complete(0, feedRequestId: 'feed-request-old');
      await first;
      final finalState = container
          .read(discoveryFeedMapProvider)['photo']!
          .value!;
      expect(finalState.feedRequestId, 'feed-request-new');
      expect(finalState.items, isNotEmpty);
      expect(finalState.blockingError, isNull);
      expect(finalState.staleDataError, isNull);
    });

    test('refresh supersede 旧 append，新 append 不得反向取消 refresh', () async {
      final repo = _SupersedingContentRepository();
      final container = _container(repo);
      addTearDown(container.dispose);
      final notifier = container.read(discoveryFeedMapProvider.notifier);

      final initial = notifier.load('photo', force: true);
      await container.pump();
      repo.complete(0, feedRequestId: 'feed-request-initial');
      await initial;

      final append = notifier.appendNextPage('photo');
      await container.pump();
      expect(repo.requests, hasLength(2));
      expect(repo.requests[1].cursor, isNotNull);
      final duringAppend = container
          .read(discoveryFeedMapProvider)['photo']!
          .value!;
      expect(duringAppend.isLoading, isTrue);
      expect(duringAppend.isRefreshing, isFalse);
      expect(duringAppend.isAppending, isTrue);

      final refresh = notifier.load('photo', force: true);
      await container.pump();
      expect(repo.requests, hasLength(3));
      expect(repo.requests[1].cancellation?.isCancelled, isTrue);
      expect(repo.requests[2].cursor, isNull);
      expect(repo.requests[2].cancellation?.isCancelled, isFalse);

      final duringRefresh = container
          .read(discoveryFeedMapProvider)['photo']!
          .value!;
      expect(duringRefresh.items, isNotEmpty);
      expect(duringRefresh.isLoading, isFalse);
      expect(duringRefresh.isRefreshing, isTrue);
      expect(duringRefresh.isAppending, isFalse);

      await notifier.appendNextPage('photo');
      expect(repo.requests, hasLength(3));
      expect(repo.requests[2].cancellation?.isCancelled, isFalse);

      repo.complete(2, feedRequestId: 'feed-request-refreshed');
      await refresh;
      repo.complete(1, feedRequestId: 'feed-request-stale-append');
      await append;

      final finalState = container
          .read(discoveryFeedMapProvider)['photo']!
          .value!;
      expect(finalState.feedRequestId, 'feed-request-refreshed');
      expect(finalState.isLoading, isFalse);
      expect(finalState.isRefreshing, isFalse);
      expect(finalState.isAppending, isFalse);
      expect(finalState.appendError, isNull);
    });

    test('append 超时取消 transport，超时后晚到结果不回写', () {
      fakeAsync((async) {
        final repo = _PendingAppendContentRepository();
        final container = _container(repo);
        addTearDown(container.dispose);
        final notifier = container.read(discoveryFeedMapProvider.notifier);

        unawaited(notifier.load('photo'));
        async.flushMicrotasks();
        final before = container
            .read(discoveryFeedMapProvider)['photo']!
            .value!;
        expect(before.items, isNotEmpty);
        expect(before.hasMore, isTrue);

        unawaited(notifier.appendNextPage('photo'));
        async.flushMicrotasks();
        final pending = container
            .read(discoveryFeedMapProvider)['photo']!
            .value!;
        expect(pending.isLoading, isTrue);
        expect(pending.isRefreshing, isFalse);
        expect(pending.isAppending, isTrue);
        expect(repo.cancellation?.isCancelled, isFalse);

        async.elapse(const Duration(seconds: 6));
        async.flushMicrotasks();
        final timedOut = container
            .read(discoveryFeedMapProvider)['photo']!
            .value!;
        expect(repo.cancellation?.isCancelled, isTrue);
        expect(timedOut.items, same(before.items));
        expect(timedOut.isLoading, isFalse);
        expect(timedOut.isRefreshing, isFalse);
        expect(timedOut.isAppending, isFalse);
        expect(timedOut.appendError, isA<CloudException>());
        expect(
          (timedOut.appendError! as CloudException).runtimeFailure.kind,
          RuntimeFailureKind.timeout,
        );

        repo.completeLate();
        async.flushMicrotasks();
        final afterLateCompletion = container
            .read(discoveryFeedMapProvider)['photo']!
            .value!;
        expect(afterLateCompletion.items, same(before.items));
        expect(afterLateCompletion.appendError, same(timedOut.appendError));
        expect(afterLateCompletion.isAppending, isFalse);
      });
    });

    test('频道离开会取消该频道 append 并保留可恢复正文与 cursor', () async {
      final repo = _PendingAppendContentRepository();
      final container = _container(repo);
      addTearDown(container.dispose);
      final notifier = container.read(discoveryFeedMapProvider.notifier);

      await notifier.load('photo');
      final before = container.read(discoveryFeedMapProvider)['photo']!.value!;
      final append = notifier.appendNextPage('photo');
      await container.pump();
      expect(repo.cancellation?.isCancelled, isFalse);

      notifier.deactivateChannel('photo');
      final deactivated = container
          .read(discoveryFeedMapProvider)['photo']!
          .value!;
      expect(repo.cancellation?.isCancelled, isTrue);
      expect(deactivated.items, same(before.items));
      expect(deactivated.nextCursor, before.nextCursor);
      expect(deactivated.isLoading, isFalse);
      expect(deactivated.isRefreshing, isFalse);
      expect(deactivated.isAppending, isFalse);

      repo.completeLate();
      await append;
      final afterLate = container
          .read(discoveryFeedMapProvider)['photo']!
          .value!;
      expect(afterLate.items, same(before.items));
      expect(afterLate.nextCursor, before.nextCursor);
    });

    test('频道离开会清除空的半成品 load，晚到 generation 不回写', () async {
      final repo = _SupersedingContentRepository();
      final container = _container(repo);
      addTearDown(container.dispose);
      final notifier = container.read(discoveryFeedMapProvider.notifier);

      final load = notifier.load('recommend', force: true);
      await container.pump();
      expect(repo.requests, hasLength(1));

      notifier.deactivateChannel('recommend');
      expect(repo.requests.single.cancellation?.isCancelled, isTrue);
      expect(
        container.read(discoveryFeedMapProvider).containsKey('recommend'),
        isFalse,
      );

      repo.complete(0, feedRequestId: 'feed-request-too-late');
      await load;
      expect(
        container.read(discoveryFeedMapProvider).containsKey('recommend'),
        isFalse,
      );
    });

    test('SWR 首屏先展示 stale snapshot，同 generation 再原子采纳远端', () async {
      final repo = _StaleWhileRevalidateContentRepository();
      final container = _container(repo);
      addTearDown(container.dispose);
      final notifier = container.read(discoveryFeedMapProvider.notifier);

      final load = notifier.load('photo');
      await container.pump();
      expect(repo.requests, hasLength(1));

      final stale = container.read(discoveryFeedMapProvider)['photo']!.value!;
      expect(stale.items, isNotEmpty);
      expect(stale.feedRequestId, 'feed-request-cached-0');
      expect(stale.isLoading, isFalse);
      expect(stale.isRefreshing, isTrue);
      expect(stale.isAppending, isFalse);
      expect(stale.blockingError, isNull);
      expect(stale.staleDataError, isNull);

      repo.completeRemote(0, feedRequestId: 'feed-request-remote-0');
      await load;
      final fresh = container.read(discoveryFeedMapProvider)['photo']!.value!;
      expect(fresh.feedRequestId, 'feed-request-remote-0');
      expect(fresh.isLoading, isFalse);
      expect(fresh.isRefreshing, isFalse);
      expect(fresh.isAppending, isFalse);
      expect(fresh.staleDataError, isNull);
    });

    test('SWR 再验证被新刷新 supersede 后，旧远端晚到不回写', () async {
      final repo = _StaleWhileRevalidateContentRepository();
      final container = _container(repo);
      addTearDown(container.dispose);
      final notifier = container.read(discoveryFeedMapProvider.notifier);

      final first = notifier.load('photo', force: true);
      await container.pump();
      expect(repo.requests, hasLength(1));
      expect(
        container.read(discoveryFeedMapProvider)['photo']!.value!.feedRequestId,
        'feed-request-cached-0',
      );

      final second = notifier.load('photo', force: true);
      await container.pump();
      expect(repo.requests, hasLength(2));
      expect(repo.requests[0].cancellation?.isCancelled, isTrue);
      expect(repo.requests[1].cancellation?.isCancelled, isFalse);

      repo.completeRemote(1, feedRequestId: 'feed-request-remote-new');
      await second;
      repo.completeRemote(0, feedRequestId: 'feed-request-remote-old');
      await first;

      final finalState = container
          .read(discoveryFeedMapProvider)['photo']!
          .value!;
      expect(finalState.feedRequestId, 'feed-request-remote-new');
      expect(finalState.isRefreshing, isFalse);
      expect(finalState.staleDataError, isNull);
    });

    test('SWR 远端再验证失败保留 stale snapshot 并进入非阻塞错误态', () async {
      final repo = _StaleWhileRevalidateContentRepository();
      final container = _container(repo);
      addTearDown(container.dispose);
      final notifier = container.read(discoveryFeedMapProvider.notifier);

      final load = notifier.load('photo');
      await container.pump();
      final stale = container.read(discoveryFeedMapProvider)['photo']!.value!;

      repo.completeRemote(
        0,
        feedRequestId: 'feed-request-cached-0',
        error: StateError('remote revalidation failed'),
      );
      await load;

      final fallback = container
          .read(discoveryFeedMapProvider)['photo']!
          .value!;
      expect(fallback.items, orderedEquals(stale.items));
      expect(fallback.isRefreshing, isFalse);
      expect(fallback.blockingError, isNull);
      expect(fallback.staleDataError, isA<CloudException>());
    });

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
      expect(during.isRefreshing, isTrue);
      expect(during.isAppending, isFalse);

      repo.release();
      await refresh;
      final after = container.read(discoveryFeedMapProvider)['photo']!.value!;
      expect(after.items, isNotEmpty);
      expect(after.isLoading, isFalse);
      expect(after.isRefreshing, isFalse);
      expect(after.isAppending, isFalse);
    });
  });

  group('ContentPostReactionFacet', () {
    test('like/unlike command 与 query 使用同一 typed Facet', () async {
      final reactions = InMemoryContentPostReactionPort();
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
      final reactions = InMemoryContentPostReactionPort()
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
  Future<List<ContentPostViewData>> listDiscoveryFeed({
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
      items: const <ContentPostViewData>[],
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
    if (category == 'following' || channelId == 'following') {
      return DiscoveryFeedPage(
        items: <ContentPostViewData>[],
        outcome: ContentFeedOutcome.empty,
        emptyReason: ContentFeedEmptyReason.followingEmpty,
      );
    }
    return DiscoveryFeedPage(items: <ContentPostViewData>[]);
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
      return DiscoveryFeedPage(
        items: const <ContentPostViewData>[],
        feedRequestId: feedRequestId,
        policyDigest:
            'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        outcome: ContentFeedOutcome.empty,
        emptyReason: ContentFeedEmptyReason.continuationEnd,
      );
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
      policyDigest: page.policyDigest,
      outcome: ContentFeedOutcome.content,
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

class _CachedContinuationFallbackContentRepository
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
    if (cursor == null) {
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
    final page = await MockContentRepository().listDiscoveryFeedPage(
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
      items: page.items,
      nextCursor: page.nextCursor,
      feedRequestId: page.feedRequestId,
      policyDigest: page.policyDigest,
      cacheFallbackError: StateError('offline continuation cache fallback'),
      cacheAgeMs: 5000,
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
      return DiscoveryFeedPage(items: <ContentPostViewData>[]);
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

class _NeverCompletingContentRepository extends MockContentRepository {
  final Completer<DiscoveryFeedPage> _pending = Completer<DiscoveryFeedPage>();
  CloudOperationCancellationSignal? cancellation;
  DateTime? deadlineAt;
  DateTime? requestedAt;

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
  }) {
    requestedAt = DateTime.now();
    this.cancellation = cancellation;
    this.deadlineAt = deadlineAt;
    return _pending.future;
  }
}

class _PendingAppendContentRepository extends MockContentRepository {
  final Completer<DiscoveryFeedPage> _pending = Completer<DiscoveryFeedPage>();
  DiscoveryFeedPage? _heldPage;
  CloudOperationCancellationSignal? cancellation;

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
      cancellation: null,
      deadlineAt: deadlineAt,
    );
    if (cursor == null) return page;
    _heldPage = page;
    this.cancellation = cancellation;
    return _pending.future;
  }

  void completeLate() {
    _pending.complete(_heldPage!);
  }
}

class _StaleWhileRevalidateContentRepository extends MockContentRepository {
  final List<_PendingRevalidationRequest> requests =
      <_PendingRevalidationRequest>[];

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
    final basePage = await super.listDiscoveryFeedPage(
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
      cancellation: null,
      deadlineAt: deadlineAt,
    );
    final index = requests.length;
    final request = _PendingRevalidationRequest(
      basePage: basePage,
      cancellation: cancellation,
    );
    requests.add(request);
    return DiscoveryFeedPage(
      items: basePage.items,
      objectCards: basePage.objectCards,
      nextCursor: basePage.nextCursor,
      feedRequestId: 'feed-request-cached-$index',
      policyDigest: basePage.policyDigest,
      cacheAgeMs: 3000,
      revalidation: request.completer.future,
    );
  }

  void completeRemote(
    int index, {
    required String feedRequestId,
    Object? error,
  }) {
    final request = requests[index];
    request.completer.complete(
      DiscoveryFeedPage(
        items: request.basePage.items,
        objectCards: request.basePage.objectCards,
        nextCursor: request.basePage.nextCursor,
        feedRequestId: feedRequestId,
        policyDigest: request.basePage.policyDigest,
        cacheFallbackError: error,
        cacheAgeMs: error == null ? null : 3000,
      ),
    );
  }
}

final class _PendingRevalidationRequest {
  _PendingRevalidationRequest({
    required this.basePage,
    required this.cancellation,
  });

  final DiscoveryFeedPage basePage;
  final CloudOperationCancellationSignal? cancellation;
  final Completer<DiscoveryFeedPage> completer = Completer<DiscoveryFeedPage>();
}

class _SupersedingContentRepository extends MockContentRepository {
  final List<_PendingFeedRequest> requests = <_PendingFeedRequest>[];

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
    final basePage = await super.listDiscoveryFeedPage(
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
      cancellation: null,
      deadlineAt: deadlineAt,
    );
    final request = _PendingFeedRequest(
      basePage: basePage,
      cancellation: cancellation,
      cursor: cursor,
    );
    requests.add(request);
    return request.completer.future;
  }

  void complete(int index, {required String feedRequestId}) {
    final request = requests[index];
    request.completer.complete(
      DiscoveryFeedPage(
        items: request.basePage.items,
        objectCards: request.basePage.objectCards,
        nextCursor: request.basePage.nextCursor,
        feedRequestId: feedRequestId,
        policyDigest: request.basePage.policyDigest,
      ),
    );
  }
}

final class _PendingFeedRequest {
  _PendingFeedRequest({
    required this.basePage,
    required this.cancellation,
    required this.cursor,
  });

  final DiscoveryFeedPage basePage;
  final CloudOperationCancellationSignal? cancellation;
  final String? cursor;
  final Completer<DiscoveryFeedPage> completer = Completer<DiscoveryFeedPage>();
}

class _NoopPostInteractionStateNotifier extends PostInteractionStateNotifier {
  @override
  PostInteractionState build() => const PostInteractionState();

  @override
  void applyConfirmedPosts(Iterable<ContentPostViewData> posts) {
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
