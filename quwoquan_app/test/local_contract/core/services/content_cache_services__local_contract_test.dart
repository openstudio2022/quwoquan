// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-004

import 'dart:async';
import '../../../support/fixtures/intersection_fixtures.dart';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_detail_payload.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_view_data.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/core/services/cache/cached_content_repository.dart';
import 'package:quwoquan_app/core/services/cache/cache_read_result.dart';
import 'package:quwoquan_app/core/services/cache/cache_management_service.dart';
import 'package:quwoquan_app/core/services/cache/cache_telemetry_sink.dart';
import 'package:quwoquan_app/core/services/cache/content_cache_services.dart';
import 'package:quwoquan_app/core/services/cache/conversation_cache_record.dart';
import 'package:quwoquan_app/core/services/cache/conversation_cache_service.dart';
import 'package:quwoquan_app/core/services/cache/object_cache_store.dart';
import 'package:quwoquan_app/core/services/cache/user_profile_cache_service.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../../support/cloud_services/content/mock_content_repository.dart';
import '../../../support/cloud_services/content/content_post_contract_fixture.dart';

CachedContentRepository _cachedContentRepository({
  required _CountingContentRepository delegate,
  required PostObjectCacheService postCache,
  required ContentQuerySnapshotStore querySnapshotStore,
  UserProfileCacheService? userProfileCache,
  Future<void> Function(String avatarUrl)? avatarPreloader,
  Future<List<String>> Function()? blockedKeywordsLoader,
}) {
  return CachedContentRepository(
    readDelegate: delegate,
    deleteDelegate: MockContentRepository(),
    postCache: postCache,
    querySnapshotStore: querySnapshotStore,
    userProfileCache: userProfileCache,
    avatarPreloader: avatarPreloader,
    blockedKeywordsLoader: blockedKeywordsLoader,
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('ObjectCacheStore', () {
    test('maxMemoryEntries constrains the only in-memory object LRU', () {
      final store = ObjectCacheStore<String>(maxMemoryEntries: 1);

      store.put('post_1', 'one');
      store.put('post_2', 'two');

      expect(store.count, 1);
      expect(store.get('post_1'), isNull);
      expect(store.get('post_2')?.source, CacheReadSource.memory);
    });
  });

  group('CachedContentRepository', () {
    test('快照 hydration 永久阻塞时取消立即终止且不请求远端', () async {
      final delegate = _CountingContentRepository();
      final hydration = Completer<void>();
      final store = _BlockingContentQuerySnapshotStore(hydration.future);
      final repo = _cachedContentRepository(
        delegate: delegate,
        postCache: PostObjectCacheService(),
        querySnapshotStore: store,
      );
      final cancellation = CloudOperationCancellationSignal();

      final pending = repo.listDiscoveryFeedPage(
        category: 'moment',
        cancellation: cancellation,
      );
      cancellation.cancel();

      await expectLater(
        pending.timeout(const Duration(seconds: 1)),
        throwsA(isA<CloudOperationCancelledException>()),
      );
      expect(delegate.feedRequestCount, 0);
      expect(store.count, 0);
    });

    test('快照 hydration 永久阻塞时由请求期限终止且不请求远端', () async {
      final delegate = _CountingContentRepository();
      final hydration = Completer<void>();
      final store = _BlockingContentQuerySnapshotStore(hydration.future);
      final repo = _cachedContentRepository(
        delegate: delegate,
        postCache: PostObjectCacheService(),
        querySnapshotStore: store,
      );

      final pending = repo.listDiscoveryFeedPage(
        category: 'moment',
        deadlineAt: DateTime.now().add(const Duration(milliseconds: 20)),
      );

      await expectLater(
        pending.timeout(const Duration(seconds: 1)),
        throwsA(isA<TimeoutException>()),
      );
      expect(delegate.feedRequestCount, 0);
      expect(store.count, 0);
    });

    test('feed 首屏先返回持久快照并用同一结果句柄完成远端再验证', () async {
      final delegate = _CountingContentRepository();
      final repo = _cachedContentRepository(
        delegate: delegate,
        postCache: PostObjectCacheService(),
        querySnapshotStore: ContentQuerySnapshotStore(),
      );

      final first = await repo.listDiscoveryFeedPage(category: 'moment');
      final refresh = Completer<DiscoveryFeedPage>();
      delegate.pendingFeedPage = refresh;
      final stale = await repo.listDiscoveryFeedPage(category: 'moment');

      expect(first.items.single.id, 'post_1');
      expect(stale.items.single.id, 'post_1');
      expect(stale.isStaleWhileRevalidate, isTrue);
      expect(stale.isCacheFallback, isFalse);
      expect(delegate.feedRequestCount, 2);

      refresh.complete(
        DiscoveryFeedPage(items: <ContentPostViewData>[_postDto('post_2')]),
      );
      final revalidated = await stale.revalidation!;
      expect(revalidated.items.single.id, 'post_2');
      expect(revalidated.isCacheFallback, isFalse);
      expect(delegate.feedRequestCount, 2);
    });

    test('feed 首屏远端再验证失败时保留快照并暴露真实失败', () async {
      final delegate = _CountingContentRepository();
      final repo = _cachedContentRepository(
        delegate: delegate,
        postCache: PostObjectCacheService(),
        querySnapshotStore: ContentQuerySnapshotStore(),
      );

      await repo.listDiscoveryFeedPage(category: 'moment');
      delegate.failFeedRequests = true;
      final stale = await repo.listDiscoveryFeedPage(category: 'moment');
      final fallback = await stale.revalidation!;

      expect(stale.items.single.id, 'post_1');
      expect(stale.isStaleWhileRevalidate, isTrue);
      expect(fallback.items.single.id, 'post_1');
      expect(fallback.isCacheFallback, isTrue);
      expect(fallback.cacheFallbackError, isA<StateError>());
      expect(delegate.feedRequestCount, 2);
    });

    test('feed 缓存回退仍过滤账号屏蔽关键词', () async {
      final delegate = _CountingContentRepository();
      final repo = _cachedContentRepository(
        delegate: delegate,
        postCache: PostObjectCacheService(),
        querySnapshotStore: ContentQuerySnapshotStore(),
        blockedKeywordsLoader: () async => <String>['缓存内容'],
      );

      await repo.listDiscoveryFeedPage(category: 'moment');
      delegate.failFeedRequests = true;
      final stale = await repo.listDiscoveryFeedPage(category: 'moment');
      final fallback = await stale.revalidation!;

      expect(stale.items, isEmpty);
      expect(fallback.items, isEmpty);
      expect(fallback.isCacheFallback, isTrue);
    });

    test('缓存回退关键词读取阻塞时取消终止且晚完成不产生新请求或写缓存', () async {
      final delegate = _CountingContentRepository();
      final store = ContentQuerySnapshotStore();
      final keywords = Completer<List<String>>();
      final loaderStarted = Completer<void>();
      final repo = _cachedContentRepository(
        delegate: delegate,
        postCache: PostObjectCacheService(),
        querySnapshotStore: store,
        blockedKeywordsLoader: () {
          if (!loaderStarted.isCompleted) {
            loaderStarted.complete();
          }
          return keywords.future;
        },
      );
      await repo.listDiscoveryFeedPage(category: 'moment');
      delegate.failFeedRequests = true;
      final cancellation = CloudOperationCancellationSignal();

      final pending = repo.listDiscoveryFeedPage(
        category: 'moment',
        cancellation: cancellation,
      );
      await loaderStarted.future;
      cancellation.cancel();
      await expectLater(
        pending.timeout(const Duration(seconds: 1)),
        throwsA(isA<CloudOperationCancelledException>()),
      );
      final requestCountAfterCancel = delegate.feedRequestCount;
      final cacheCountAfterCancel = store.count;

      keywords.complete(const <String>[]);
      await Future<void>.delayed(Duration.zero);
      expect(delegate.feedRequestCount, requestCountAfterCancel);
      expect(store.count, cacheCountAfterCancel);
      expect(requestCountAfterCancel, 1);
      expect(cacheCountAfterCancel, 1);
    });

    test('缓存回退关键词读取阻塞时由请求期限终止', () async {
      final delegate = _CountingContentRepository();
      final store = ContentQuerySnapshotStore();
      final keywords = Completer<List<String>>();
      final repo = _cachedContentRepository(
        delegate: delegate,
        postCache: PostObjectCacheService(),
        querySnapshotStore: store,
        blockedKeywordsLoader: () => keywords.future,
      );
      await repo.listDiscoveryFeedPage(category: 'moment');
      delegate.failFeedRequests = true;

      final pending = repo.listDiscoveryFeedPage(
        category: 'moment',
        deadlineAt: DateTime.now().add(const Duration(milliseconds: 20)),
      );

      await expectLater(
        pending.timeout(const Duration(seconds: 1)),
        throwsA(isA<TimeoutException>()),
      );
      expect(delegate.feedRequestCount, 1);
      expect(store.count, 1);
    });

    test('个人作品优先请求远端，失败时才回退快照', () async {
      final delegate = _CountingContentRepository();
      final repo = _cachedContentRepository(
        delegate: delegate,
        postCache: PostObjectCacheService(),
        querySnapshotStore: ContentQuerySnapshotStore(),
      );

      final first = await repo.listUserPosts(userId: 'user_1');
      final second = await repo.listUserPosts(userId: 'user_1');
      delegate.failUserPostsRequests = true;
      final fallback = await repo.listUserPosts(userId: 'user_1');

      expect(first.items.single.id, 'post_1');
      expect(second.items.single.id, 'post_1');
      expect(delegate.userPostsRequestCount, 3);
      expect(fallback.items.single.id, 'post_1');
      expect(fallback.isCacheFallback, isTrue);
      expect(fallback.cacheFallbackError, isA<StateError>());
    });

    test('post 详情命中对象缓存后不重复请求远端', () async {
      final delegate = _CountingContentRepository();
      final repo = _cachedContentRepository(
        delegate: delegate,
        postCache: PostObjectCacheService(),
        querySnapshotStore: ContentQuerySnapshotStore(),
      );

      final first = await repo.getPost(postId: 'post_1');
      final second = await repo.getPost(postId: 'post_1');

      expect(first.post.id, 'post_1');
      expect(second.post.id, 'post_1');
      expect(delegate.detailRequestCount, 1);
    });

    test('视频详情缓存保留播放 canary 的规范媒体字段', () async {
      const videoUrl =
          'media/video/s/video-primary-0001/post/video-content-0001/v1/source.mp4';
      const thumbnailUrl =
          'media/image/s/archived-image/post/fixture_video_001/v1/cover.png';
      final delegate = _CountingContentRepository(
        post: _videoPostDto(
          'fixture_video_001',
          videoUrl: videoUrl,
          thumbnailUrl: thumbnailUrl,
        ),
      );
      final repo = _cachedContentRepository(
        delegate: delegate,
        postCache: PostObjectCacheService(),
        querySnapshotStore: ContentQuerySnapshotStore(),
      );

      final first = await repo.getPost(postId: 'fixture_video_001');
      final second = await repo.getPost(postId: 'fixture_video_001');

      expect(first.post.type, 'video');
      expect(first.post.identity, 'work');
      expect(first.post.mediaVideoUrl, videoUrl);
      expect(first.post.mediaThumbnailUrl, thumbnailUrl);
      expect(first.post.durationMs, 45000);
      expect(first.post.isVideoLike, isTrue);
      expect(second.post.mediaVideoUrl, videoUrl);
      expect(delegate.detailRequestCount, 1);
    });

    test('feed 和详情写入时同步登记作者头像快照并预热头像资源', () async {
      final delegate = _CountingContentRepository(
        post: _postDto(
          'post_1',
          avatarUrl: 'https://cdn.example.com/avatar/user_1.png',
        ),
      );
      final userCache = UserProfileCacheService();
      final preloaded = <String>[];
      final repo = _cachedContentRepository(
        delegate: delegate,
        postCache: PostObjectCacheService(),
        querySnapshotStore: ContentQuerySnapshotStore(),
        userProfileCache: userCache,
        avatarPreloader: (url) async => preloaded.add(url),
      );

      await repo.listDiscoveryFeedPage(category: 'moment');
      await repo.getPost(postId: 'post_1');

      final cachedAuthor = userCache.get('user_1');
      expect(
        cachedAuthor?['avatarUrl'],
        'https://cdn.example.com/avatar/user_1.png',
      );
      expect(cachedAuthor?['displayName'], '用户一');
      expect(preloaded, contains('https://cdn.example.com/avatar/user_1.png'));
    });

    test('query snapshot 可持久化恢复用于短退重启回显', () async {
      SharedPreferences.setMockInitialValues(<String, Object>{});
      const storageKey = 'qwq.content_query_snapshots.test';
      const queryKey = 'surface=discoveryFeed&category=moment&cursor=';
      final store = ContentQuerySnapshotStore(
        persistToPreferences: true,
        storageKey: storageKey,
        telemetrySink: const NoopCacheTelemetrySink(),
      );
      await store.ensureHydrated();

      store.put(
        key: queryKey,
        items: <ContentPostViewData>[_postDto('post_1')],
        nextCursor: 'cursor_2',
        previousCursor: 'cursor_previous',
        paginationExpiresAt: DateTime.utc(2026, 7, 29, 12),
        paginationSessionId: 'session-persisted',
        feedRequestId: 'feed_request_1',
        policyDigest:
            'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      );
      await store.flushPersistence();
      final persistedPayload =
          jsonDecode(
                (await SharedPreferences.getInstance()).getString(storageKey)!,
              )
              as Map<String, dynamic>;
      expect(persistedPayload.keys, <String>['snapshots']);
      final memoryCached = store.get(queryKey);
      expect(memoryCached?.source, CacheReadSource.memory);

      final restored = ContentQuerySnapshotStore(
        persistToPreferences: true,
        storageKey: storageKey,
        telemetrySink: const NoopCacheTelemetrySink(),
      );
      await restored.ensureHydrated();
      final cached = restored.get(queryKey);

      expect(cached, isNotNull);
      expect(cached!.source, CacheReadSource.disk);
      expect(cached.value.items.single.id, 'post_1');
      expect(cached.value.nextCursor, 'cursor_2');
      expect(cached.value.previousCursor, 'cursor_previous');
      expect(cached.value.paginationExpiresAt, DateTime.utc(2026, 7, 29, 12));
      expect(cached.value.paginationSessionId, 'session-persisted');
      expect(cached.value.feedRequestId, 'feed_request_1');
      expect(
        cached.value.policyDigest,
        'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      );
      expect(cached.diagnostics.hitLayer, 'querySnapshot.disk');
    });

    test('query snapshot 反序列化严格拒绝非 canonical policyDigest', () async {
      SharedPreferences.setMockInitialValues(<String, Object>{});
      const storageKey = 'qwq.content_query_snapshots.policy_digest.test';
      const queryKey = 'surface=discoveryFeed&category=moment&cursor=';
      const canonical =
          'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';

      final valid = ContentQuerySnapshot.fromMap(<String, dynamic>{
        'key': queryKey,
        'items': const <Object?>[],
        'outcome': 'empty',
        'emptyReason': 'no_eligible_content',
        'fetchedAt': DateTime.utc(2026, 7, 29).toIso8601String(),
        'policyDigest': canonical,
      });
      expect(valid?.policyDigest, canonical);

      expect(
        ContentQuerySnapshot.fromMap(<String, dynamic>{
          'key': queryKey,
          'items': const <Object?>[],
          'fetchedAt': DateTime.utc(2026, 7, 29).toIso8601String(),
        }),
        isNull,
        reason: 'retired feed snapshots without canonical outcome must expire',
      );

      for (final invalid in <Object?>[
        '',
        'rank-v3',
        ' $canonical',
        '$canonical ',
        invalidSha256Fixture(List<String>.filled(64, 'A').join()),
        invalidSha256Fixture(List<String>.filled(63, 'a').join()),
        42,
      ]) {
        expect(
          ContentQuerySnapshot.fromMap(<String, dynamic>{
            'key': queryKey,
            'items': const <Object?>[],
            'fetchedAt': DateTime.utc(2026, 7, 29).toIso8601String(),
            'policyDigest': invalid,
          }),
          isNull,
          reason: 'must drop <$invalid> without coercion or normalization',
        );
      }

      final persisted = jsonEncode(<String, Object?>{
        'snapshots': <Object?>[
          <String, Object?>{
            'key': queryKey,
            'items': const <Object?>[],
            'fetchedAt': DateTime.now().toUtc().toIso8601String(),
            'policyDigest': ' $canonical',
          },
        ],
      });
      SharedPreferences.setMockInitialValues(<String, Object>{
        storageKey: persisted,
      });
      final restored = ContentQuerySnapshotStore(
        persistToPreferences: true,
        storageKey: storageKey,
        telemetrySink: const NoopCacheTelemetrySink(),
      );
      await restored.ensureHydrated();

      expect(restored.count, 0);
      expect(restored.get(queryKey), isNull);
      expect(
        () => restored.put(
          key: queryKey,
          items: const <ContentPostViewData>[],
          policyDigest: '',
        ),
        throwsFormatException,
      );
    });

    test('query snapshot 在 5 分钟后至 24 小时内只以 stale 回显', () {
      var now = DateTime.utc(2026, 7, 29, 0);
      const queryKey = 'surface=discoveryFeed&category=moment&cursor=';
      final store = ContentQuerySnapshotStore(
        telemetrySink: const NoopCacheTelemetrySink(),
        now: () => now,
      );

      store.put(
        key: queryKey,
        items: <ContentPostViewData>[_postDto('post_1')],
      );
      now = now.add(const Duration(minutes: 6));

      final cached = store.get(queryKey);
      expect(cached, isNotNull);
      expect(cached!.freshness, CacheFreshness.stale);
      expect(cached.syncState, CacheSyncState.refreshing);
      expect(store.count, 1);
    });

    test(
      'cached feed cursors require the same live session and unexpired boundary',
      () {
        final expiresAt = DateTime.utc(2026, 7, 29, 12);
        final snapshot = ContentQuerySnapshot(
          key: 'surface=discoveryFeed&cursor=',
          items: <ContentPostViewData>[_postDto('post_1')],
          fetchedAt: DateTime.utc(2026, 7, 29, 11),
          nextCursor: 'fc.next',
          previousCursor: 'fc.previous',
          paginationExpiresAt: expiresAt,
          paginationSessionId: 'session-a',
        );

        final live = snapshot.toDiscoveryFeedPage(
          currentSessionId: 'session-a',
          now: DateTime.utc(2026, 7, 29, 11, 30),
        );
        expect(live.nextCursor, 'fc.next');
        expect(live.previousCursor, 'fc.previous');

        final crossSession = snapshot.toDiscoveryFeedPage(
          currentSessionId: 'session-b',
          now: DateTime.utc(2026, 7, 29, 11, 30),
        );
        expect(crossSession.nextCursor, isNull);
        expect(crossSession.previousCursor, isNull);

        final expired = snapshot.toDiscoveryFeedPage(
          currentSessionId: 'session-a',
          now: expiresAt,
        );
        expect(expired.nextCursor, isNull);
        expect(expired.previousCursor, isNull);
      },
    );

    test('query snapshot 超过 24 小时后从内存和持久层主动清退', () async {
      SharedPreferences.setMockInitialValues(<String, Object>{});
      const storageKey = 'qwq.content_query_snapshots.expiry.test';
      const queryKey = 'surface=discoveryFeed&category=moment&cursor=';
      var now = DateTime.utc(2026, 7, 29, 0);
      final store = ContentQuerySnapshotStore(
        persistToPreferences: true,
        storageKey: storageKey,
        telemetrySink: const NoopCacheTelemetrySink(),
        now: () => now,
      );
      await store.ensureHydrated();
      store.put(
        key: queryKey,
        items: <ContentPostViewData>[_postDto('post_1')],
      );
      await store.flushPersistence();

      now = now.add(const Duration(hours: 24, microseconds: 1));
      final restored = ContentQuerySnapshotStore(
        persistToPreferences: true,
        storageKey: storageKey,
        telemetrySink: const NoopCacheTelemetrySink(),
        now: () => now,
      );
      await restored.ensureHydrated();
      await restored.flushPersistence();

      expect(restored.get(queryKey), isNull);
      expect(restored.count, 0);
      expect(
        (await SharedPreferences.getInstance()).containsKey(storageKey),
        isFalse,
      );
    });

    test('query snapshot 分块 JSON 编码保真转义字符和嵌套投影', () async {
      SharedPreferences.setMockInitialValues(<String, Object>{});
      const storageKey = 'qwq.content_query_snapshots.json_round_trip.test';
      const queryKey = 'surface=discoveryFeed&category=moment&cursor=';
      final body =
          '${List<String>.filled(1023, 'a').join()}🙂\n"quoted"\\slash\t\u0001';
      final store = ContentQuerySnapshotStore(
        persistToPreferences: true,
        storageKey: storageKey,
        telemetrySink: const NoopCacheTelemetrySink(),
      );
      await store.ensureHydrated();

      store.put(
        key: queryKey,
        items: <ContentPostViewData>[
          _postDto(
            'post_escaped',
            body: body,
            intersectionReasons: <IntersectionReason>[
              intersectionReasonFixture(primaryText: '共同喜欢雪山🙂'),
            ],
          ),
        ],
      );
      await store.flushPersistence();

      final restored = ContentQuerySnapshotStore(
        persistToPreferences: true,
        storageKey: storageKey,
        telemetrySink: const NoopCacheTelemetrySink(),
      );
      await restored.ensureHydrated();
      final post = restored.get(queryKey)!.value.items.single;

      expect(post.body, body);
      expect(post.intersectionReasons!.single.primaryText, '共同喜欢雪山🙂');
    });

    test('query snapshot 持久化保留有界连续 feed 完整页窗口', () async {
      SharedPreferences.setMockInitialValues(<String, Object>{});
      const storageKey = 'qwq.content_query_snapshots.policy.test';
      final store = ContentQuerySnapshotStore(
        persistToPreferences: true,
        storageKey: storageKey,
        persistencePolicy: const ContentQuerySnapshotPersistencePolicy(
          maxItemsPerSnapshot: 30,
          maxUserPostSubjects: 1,
          maxFeedPagesPerQuery: 3,
        ),
        telemetrySink: const NoopCacheTelemetrySink(),
      );
      await store.ensureHydrated();

      final firstFeedKey = contentFeedQueryKey(
        category: 'moment',
        cursor: null,
        sort: kFeedSortRecommend,
        limit: 20,
      );
      final middleFeedKey = contentFeedQueryKey(
        category: 'moment',
        cursor: 'cursor_1',
        sort: kFeedSortRecommend,
        limit: 20,
      );
      final latestFeedKey = contentFeedQueryKey(
        category: 'moment',
        cursor: 'cursor_2',
        sort: kFeedSortRecommend,
        limit: 20,
      );
      final overflowFeedKey = contentFeedQueryKey(
        category: 'moment',
        cursor: 'cursor_3',
        sort: kFeedSortRecommend,
        limit: 20,
      );
      final manyPosts = List<ContentPostViewData>.generate(
        30,
        (index) => _postDto('feed_$index'),
      );
      store.put(key: firstFeedKey, items: manyPosts, nextCursor: 'cursor_1');
      await Future<void>.delayed(const Duration(milliseconds: 1));
      store.put(
        key: middleFeedKey,
        items: <ContentPostViewData>[_postDto('middle_feed')],
        nextCursor: 'cursor_2',
      );
      await Future<void>.delayed(const Duration(milliseconds: 1));
      store.put(
        key: latestFeedKey,
        items: <ContentPostViewData>[_postDto('latest_feed')],
        nextCursor: 'cursor_3',
      );
      await Future<void>.delayed(const Duration(milliseconds: 1));
      store.put(
        key: overflowFeedKey,
        items: <ContentPostViewData>[_postDto('overflow_feed')],
      );

      final oldUserKey = contentUserPostsQueryKey(
        userId: 'old_user',
        cursor: null,
        limit: 20,
      );
      final latestUserKey = contentUserPostsQueryKey(
        userId: 'latest_user',
        cursor: null,
        limit: 20,
      );
      store.put(
        key: oldUserKey,
        items: <ContentPostViewData>[_postDto('old_user')],
      );
      await Future<void>.delayed(const Duration(milliseconds: 1));
      store.put(
        key: latestUserKey,
        items: <ContentPostViewData>[_postDto('latest_user')],
      );
      await store.flushPersistence();

      final restored = ContentQuerySnapshotStore(
        persistToPreferences: true,
        storageKey: storageKey,
        persistencePolicy: const ContentQuerySnapshotPersistencePolicy(
          maxItemsPerSnapshot: 30,
          maxUserPostSubjects: 1,
          maxFeedPagesPerQuery: 3,
        ),
        telemetrySink: const NoopCacheTelemetrySink(),
      );
      await restored.ensureHydrated();

      expect(restored.get(firstFeedKey)?.value.items, hasLength(30));
      expect(restored.get(middleFeedKey)?.value.items.single.id, 'middle_feed');
      expect(restored.get(latestFeedKey)?.value.items.single.id, 'latest_feed');
      expect(restored.get(overflowFeedKey), isNull);
      expect(restored.get(oldUserKey), isNull);
      expect(restored.get(latestUserKey)?.value.items.single.id, 'latest_user');
    });

    test('query snapshot 优先按多字节 UTF-8 预算保留完整 feed 页链', () async {
      const probeStorageKey = 'qwq.content_query_snapshots.bytes.probe.test';
      final firstFeedKey = contentFeedQueryKey(
        category: 'moment',
        cursor: null,
        sort: kFeedSortRecommend,
        limit: 20,
      );
      final secondFeedKey = contentFeedQueryKey(
        category: 'moment',
        cursor: 'cursor_1',
        sort: kFeedSortRecommend,
        limit: 20,
      );
      final firstPage = <ContentPostViewData>[
        _postDto('feed_1', body: List<String>.filled(24, '川西雪山🙂').join()),
      ];
      final secondPage = <ContentPostViewData>[
        _postDto('feed_2', body: List<String>.filled(48, '高原湖泊🏔️').join()),
      ];

      SharedPreferences.setMockInitialValues(<String, Object>{});
      final probe = ContentQuerySnapshotStore(
        persistToPreferences: true,
        storageKey: probeStorageKey,
        telemetrySink: const NoopCacheTelemetrySink(),
      );
      await probe.ensureHydrated();
      probe.put(key: firstFeedKey, items: firstPage, nextCursor: 'cursor_1');
      await probe.flushPersistence();
      final firstPagePayload = (await SharedPreferences.getInstance())
          .getString(probeStorageKey)!;
      probe.put(key: secondFeedKey, items: secondPage);
      await probe.flushPersistence();
      final fullPayload = (await SharedPreferences.getInstance()).getString(
        probeStorageKey,
      )!;
      final firstPageBytes = utf8.encode(firstPagePayload).length;
      final fullPayloadBytes = utf8.encode(fullPayload).length;
      final byteCap =
          firstPageBytes + ((fullPayloadBytes - firstPageBytes) ~/ 2);

      SharedPreferences.setMockInitialValues(<String, Object>{});
      const boundedStorageKey =
          'qwq.content_query_snapshots.bytes.bounded.test';
      final userPostsKey = contentUserPostsQueryKey(
        userId: 'large_profile',
        cursor: null,
        limit: 20,
      );
      final boundedPolicy = ContentQuerySnapshotPersistencePolicy(
        maxPersistedBytes: byteCap,
      );
      final bounded = ContentQuerySnapshotStore(
        persistToPreferences: true,
        storageKey: boundedStorageKey,
        persistencePolicy: boundedPolicy,
        telemetrySink: const NoopCacheTelemetrySink(),
      );
      await bounded.ensureHydrated();
      bounded.put(
        key: userPostsKey,
        items: <ContentPostViewData>[
          _postDto(
            'large_user_post',
            body: List<String>.filled(1000, '独立个人作品页🙂').join(),
          ),
        ],
      );
      await bounded.flushPersistence();
      bounded.put(key: firstFeedKey, items: firstPage, nextCursor: 'cursor_1');
      await bounded.flushPersistence();
      bounded.put(key: secondFeedKey, items: secondPage);
      await bounded.flushPersistence();

      final persisted = (await SharedPreferences.getInstance()).getString(
        boundedStorageKey,
      )!;
      expect(persisted, contains('川西雪山🙂'));
      expect(utf8.encode(persisted).length, greaterThan(persisted.length));
      expect(utf8.encode(persisted).length, lessThanOrEqualTo(byteCap));

      final restored = ContentQuerySnapshotStore(
        persistToPreferences: true,
        storageKey: boundedStorageKey,
        persistencePolicy: boundedPolicy,
        telemetrySink: const NoopCacheTelemetrySink(),
      );
      await restored.ensureHydrated();
      expect(restored.get(firstFeedKey)?.value.items.single.id, 'feed_1');
      expect(restored.get(firstFeedKey)?.value.nextCursor, 'cursor_1');
      expect(restored.get(secondFeedKey), isNull);
      expect(restored.get(userPostsKey), isNull);
    });

    test('query snapshot 超预算时整体拒绝且不持久化尾部 item', () async {
      SharedPreferences.setMockInitialValues(<String, Object>{});
      const storageKey =
          'qwq.content_query_snapshots.streaming_encode_budget.test';
      final queryKey = contentFeedQueryKey(
        category: 'moment',
        cursor: null,
        sort: kFeedSortRecommend,
        limit: 20,
      );
      final store = ContentQuerySnapshotStore(
        persistToPreferences: true,
        storageKey: storageKey,
        persistencePolicy: const ContentQuerySnapshotPersistencePolicy(
          maxPersistedBytes: 512,
        ),
        telemetrySink: const NoopCacheTelemetrySink(),
      );
      await store.ensureHydrated();

      store.put(
        key: queryKey,
        items: <ContentPostViewData>[
          _postDto('oversized', body: List<String>.filled(4096, 'x').join()),
          _postDto('must_not_encode', body: 'tail'),
        ],
      );
      await store.flushPersistence();

      final persisted = (await SharedPreferences.getInstance()).getString(
        storageKey,
      )!;
      final payload = jsonDecode(persisted) as Map<String, dynamic>;
      expect(payload['snapshots'], isEmpty);
      expect(utf8.encode(persisted).length, lessThanOrEqualTo(512));
    });

    test('query snapshot 在持久化前按 canonical UTF-8 总预算拒绝超额 Post', () async {
      SharedPreferences.setMockInitialValues(<String, Object>{});
      const storageKey =
          'qwq.content_query_snapshots.field_byte_admission.test';
      final queryKey = contentFeedQueryKey(
        category: 'moment',
        cursor: null,
        sort: kFeedSortRecommend,
        limit: 20,
      );
      final store = ContentQuerySnapshotStore(
        persistToPreferences: true,
        storageKey: storageKey,
        persistencePolicy: const ContentQuerySnapshotPersistencePolicy(
          maxPersistedBytes: 512,
        ),
        telemetrySink: const NoopCacheTelemetrySink(),
      );
      await store.ensureHydrated();
      store.put(
        key: queryKey,
        items: <ContentPostViewData>[
          _postDto(
            'oversized_author',
            authorId: List<String>.filled(43, '人').join(),
          ),
        ],
      );
      await store.flushPersistence();

      final persisted = (await SharedPreferences.getInstance()).getString(
        storageKey,
      );
      expect(persisted, isNot(contains('oversized_author')));

      final restored = ContentQuerySnapshotStore(
        persistToPreferences: true,
        storageKey: storageKey,
        telemetrySink: const NoopCacheTelemetrySink(),
      );
      await restored.ensureHydrated();
      expect(restored.get(queryKey), isNull);
    });

    test('query snapshot 不截断超 item 预算首屏且不持久化后续 cursor 页', () async {
      SharedPreferences.setMockInitialValues(<String, Object>{});
      const storageKey = 'qwq.content_query_snapshots.atomic_page.test';
      const policy = ContentQuerySnapshotPersistencePolicy(
        maxItemsPerSnapshot: 1,
      );
      final firstFeedKey = contentFeedQueryKey(
        category: 'moment',
        cursor: null,
        sort: kFeedSortRecommend,
        limit: 20,
      );
      final secondFeedKey = contentFeedQueryKey(
        category: 'moment',
        cursor: 'cursor_1',
        sort: kFeedSortRecommend,
        limit: 20,
      );
      final store = ContentQuerySnapshotStore(
        persistToPreferences: true,
        storageKey: storageKey,
        persistencePolicy: policy,
        telemetrySink: const NoopCacheTelemetrySink(),
      );
      await store.ensureHydrated();
      store.put(
        key: firstFeedKey,
        items: <ContentPostViewData>[_postDto('feed_1'), _postDto('feed_2')],
        nextCursor: 'cursor_1',
      );
      await store.flushPersistence();
      store.put(
        key: secondFeedKey,
        items: <ContentPostViewData>[_postDto('feed_3')],
      );
      await store.flushPersistence();

      final raw = (await SharedPreferences.getInstance()).getString(
        storageKey,
      )!;
      final decoded = jsonDecode(raw) as Map<String, dynamic>;
      expect(decoded['snapshots'], isEmpty);

      final restored = ContentQuerySnapshotStore(
        persistToPreferences: true,
        storageKey: storageKey,
        persistencePolicy: policy,
        telemetrySink: const NoopCacheTelemetrySink(),
      );
      await restored.ensureHydrated();
      expect(restored.get(firstFeedKey), isNull);
      expect(restored.get(secondFeedKey), isNull);
    });

    test('query snapshot 持久化单活跃合并写且 flush 等到最新状态', () async {
      const storageKey = 'qwq.content_query_snapshots.coalesced.test';
      final backend = _ControlledQuerySnapshotPersistenceBackend();
      final queryKey = contentFeedQueryKey(
        category: 'moment',
        cursor: null,
        sort: kFeedSortRecommend,
        limit: 20,
      );
      final store = ContentQuerySnapshotStore(
        persistToPreferences: true,
        storageKey: storageKey,
        persistenceBackend: backend,
        telemetrySink: const NoopCacheTelemetrySink(),
      );
      await store.ensureHydrated();

      store.put(
        key: queryKey,
        items: <ContentPostViewData>[_postDto('post_1')],
      );
      await backend.firstWriteStarted.future;
      store.put(
        key: queryKey,
        items: <ContentPostViewData>[_postDto('post_2')],
      );
      store.put(
        key: queryKey,
        items: <ContentPostViewData>[_postDto('post_3')],
      );
      await Future<void>.delayed(Duration.zero);

      expect(backend.writeCallCount, 1);
      expect(backend.maxConcurrentWrites, 1);

      backend.releaseFirstWrite.complete();
      await store.flushPersistence();

      expect(backend.writeCallCount, 2);
      expect(backend.maxConcurrentWrites, 1);
      final payload =
          jsonDecode(backend.values[storageKey]!) as Map<String, dynamic>;
      final snapshots = payload['snapshots'] as List<dynamic>;
      final snapshot = snapshots.single as Map<String, dynamic>;
      final items = snapshot['items'] as List<dynamic>;
      final item = items.single as Map<String, dynamic>;
      expect(item['postId'], 'post_3');
    });

    test('clear 和 invalidate 会 flush 持久化快照', () async {
      SharedPreferences.setMockInitialValues(<String, Object>{});
      const storageKey = 'qwq.content_query_snapshots.flush.test';
      final queryKey = contentFeedQueryKey(
        category: 'moment',
        cursor: null,
        sort: kFeedSortRecommend,
        limit: 20,
      );
      final store = ContentQuerySnapshotStore(
        persistToPreferences: true,
        storageKey: storageKey,
        telemetrySink: const NoopCacheTelemetrySink(),
      );
      await store.ensureHydrated();
      store.put(
        key: queryKey,
        items: <ContentPostViewData>[_postDto('post_1')],
      );
      await store.flushPersistence();
      store.invalidatePost('post_1');
      await store.flushPersistence();

      final afterInvalidate = ContentQuerySnapshotStore(
        persistToPreferences: true,
        storageKey: storageKey,
        telemetrySink: const NoopCacheTelemetrySink(),
      );
      await afterInvalidate.ensureHydrated();
      expect(afterInvalidate.get(queryKey), isNull);

      store.put(
        key: queryKey,
        items: <ContentPostViewData>[_postDto('post_2')],
      );
      await store.flushPersistence();
      store.clearAll();
      await store.flushPersistence();

      final afterClear = ContentQuerySnapshotStore(
        persistToPreferences: true,
        storageKey: storageKey,
        telemetrySink: const NoopCacheTelemetrySink(),
      );
      await afterClear.ensureHydrated();
      expect(afterClear.get(queryKey), isNull);
    });
  });

  group('CacheManagementService', () {
    test('清理离线内容会删除 post/query 缓存但保留会话保护计数', () async {
      final postCache = PostObjectCacheService();
      final queryStore = ContentQuerySnapshotStore();
      final conversationCache = ConversationCacheService();
      final service = CacheManagementService(
        postCache: postCache,
        querySnapshotStore: queryStore,
        userProfileCache: UserProfileCacheService(),
        conversationCache: conversationCache,
        clearTemporaryImages: () async {},
        clearAccountScopedPersistence: () async {},
      );
      postCache.putDetail(_detailPayload('post_1'));
      queryStore.put(
        key: 'surface=discoveryFeed&cursor=',
        items: <ContentPostViewData>[_postDto('post_1')],
      );

      final result = await service.clear(CacheClearLevel.offlineContent);

      expect(result.objectsRemoved, 2);
      expect(result.protectedObjects, conversationCache.activeDiskCount);
      expect(service.estimateUsage().postObjects, 1);
      expect(service.estimateUsage().querySnapshots, 0);
    });

    test('账号 closed 终态清除全部内存命名空间并执行持久层清理', () async {
      SharedPreferences.setMockInitialValues(const <String, Object>{});
      final postCache = PostObjectCacheService();
      final queryStore = ContentQuerySnapshotStore();
      final userCache = UserProfileCacheService(persistToPreferences: true);
      final conversationCache = ConversationCacheService()
        ..activateNamespace('owner-a::persona-a')
        ..put(const ConversationCacheRecord(id: 'conversation-a'))
        ..activateNamespace('owner-a::persona-b')
        ..put(const ConversationCacheRecord(id: 'conversation-b'));
      var imageClearCalls = 0;
      var persistenceClearCalls = 0;
      final service = CacheManagementService(
        postCache: postCache,
        querySnapshotStore: queryStore,
        userProfileCache: userCache,
        conversationCache: conversationCache,
        clearAllRebuildableImages: () async {
          imageClearCalls += 1;
        },
        clearAccountScopedPersistence: () async {
          persistenceClearCalls += 1;
        },
      );
      postCache.putDetail(_detailPayload('post-terminal'));
      queryStore.put(
        key: 'surface=terminal&cursor=',
        items: <ContentPostViewData>[_postDto('post-terminal')],
      );
      userCache.put('user-terminal', <String, dynamic>{
        'userId': 'user-terminal',
      });

      await service.clearForTerminalAccountClosure();

      expect(imageClearCalls, 1);
      expect(persistenceClearCalls, 1);
      expect(service.estimateUsage().totalTrackedObjects, 0);
      expect(conversationCache.totalEntryCount, 0);
      expect(userCache.memoryCount, 0);
      expect(userCache.entryCount, 0);
      expect(
        (await SharedPreferences.getInstance()).containsKey(
          'qwq.user_profile_cache',
        ),
        isFalse,
      );
    });
  });
}

String invalidSha256Fixture(String payload) => 'sha256:$payload';

class _BlockingContentQuerySnapshotStore extends ContentQuerySnapshotStore {
  _BlockingContentQuerySnapshotStore(this.hydration);

  final Future<void> hydration;

  @override
  Future<void> ensureHydrated() => hydration;
}

class _ControlledQuerySnapshotPersistenceBackend
    implements ContentQuerySnapshotPersistenceBackend {
  final Map<String, String> values = <String, String>{};
  final Completer<void> firstWriteStarted = Completer<void>();
  final Completer<void> releaseFirstWrite = Completer<void>();
  int writeCallCount = 0;
  int maxConcurrentWrites = 0;
  int _concurrentWrites = 0;

  @override
  Future<String?> read(String storageKey) async => values[storageKey];

  @override
  Future<void> remove(String storageKey) async {
    values.remove(storageKey);
  }

  @override
  Future<void> write(String storageKey, String payload) async {
    writeCallCount += 1;
    _concurrentWrites += 1;
    if (_concurrentWrites > maxConcurrentWrites) {
      maxConcurrentWrites = _concurrentWrites;
    }
    try {
      if (writeCallCount == 1) {
        firstWriteStarted.complete();
        await releaseFirstWrite.future;
      }
      values[storageKey] = payload;
    } finally {
      _concurrentWrites -= 1;
    }
  }
}

class _CountingContentRepository extends Fake implements ContentReadRepository {
  _CountingContentRepository({ContentPostViewData? post})
    : post = post ?? _postDto('post_1');

  final ContentPostViewData post;
  int feedRequestCount = 0;
  int detailRequestCount = 0;
  int userPostsRequestCount = 0;
  bool failFeedRequests = false;
  bool failUserPostsRequests = false;
  Completer<DiscoveryFeedPage>? pendingFeedPage;

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
    feedRequestCount += 1;
    if (failFeedRequests) {
      throw StateError('feed offline');
    }
    final pending = pendingFeedPage;
    if (pending != null) {
      return pending.future;
    }
    return DiscoveryFeedPage(
      items: <ContentPostViewData>[post],
      nextCursor: null,
      feedRequestId: feedRequestId?.trim().isNotEmpty == true
          ? feedRequestId!.trim()
          : 'frq_mock_${DateTime.now().microsecondsSinceEpoch}',
    );
  }

  @override
  Future<ContentPostDetailPayload> getPost({
    required String postId,
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    detailRequestCount += 1;
    return _detailPayload(postId, post: post);
  }

  @override
  Future<CursorPage<ContentPostViewData>> listUserPosts({
    required String userId,
    String? identity,
    String? type,
    String? visibility,
    String? cursor,
    int limit = 20,
  }) async {
    userPostsRequestCount += 1;
    if (failUserPostsRequests) {
      throw StateError('user posts offline');
    }
    return CursorPage<ContentPostViewData>(
      items: <ContentPostViewData>[post],
      nextCursor: null,
    );
  }
}

ContentPostViewData _postDto(
  String id, {
  String authorId = 'user_1',
  String avatarUrl = '',
  String body = '缓存内容',
  List<IntersectionReason>? intersectionReasons,
}) {
  return ContentPostViewData.fromWire(
    ContentPostProjection(
      postId: id,
      contentType: 'micro',
      contentIdentity: 'moment',
      assistantUsePolicy: 'inherit',
      authorId: authorId,
      authorDisplayName: '用户一',
      authorAvatarUrl: avatarUrl,
      body: body,
      mediaUrls: const <String>[],
      likeCount: 0,
      commentCount: 0,
      shareCount: 0,
      createdAt: DateTime.utc(2026, 5, 19),
      updatedAt: DateTime.utc(2026, 5, 19),
      intersectionReasons: intersectionReasons,
    ),
  );
}

ContentPostViewData _videoPostDto(
  String id, {
  required String videoUrl,
  required String thumbnailUrl,
}) {
  return ContentPostViewData.fromWire(
    ContentPostProjection(
      postId: id,
      contentType: 'video',
      contentIdentity: 'work',
      assistantUsePolicy: 'inherit',
      authorId: 'user_1',
      authorDisplayName: '用户一',
      authorAvatarUrl: '',
      body: '播放 canary',
      videoUrl: videoUrl,
      thumbnailUrl: thumbnailUrl,
      coverUrl: thumbnailUrl,
      width: 1280,
      height: 720,
      durationMs: 45000,
      likeCount: 0,
      commentCount: 0,
      shareCount: 0,
      createdAt: DateTime.utc(2026, 5, 19),
      updatedAt: DateTime.utc(2026, 5, 19),
    ),
  );
}

ContentPostDetailPayload _detailPayload(
  String id, {
  ContentPostViewData? post,
}) {
  final resolvedPost = post ?? _postDto(id);
  return ContentPostDetailPayload.fromWire(
    ContentPostDetailSlice(
      postId: id,
      contentType: resolvedPost.type,
      contentIdentity: resolvedPost.identity,
      assistantUsePolicy: resolvedPost.assistantUsePolicy,
      authorId: resolvedPost.authorId,
      authorDisplayName: resolvedPost.displayName,
      authorAvatarUrl: resolvedPost.avatarUrl,
      body: resolvedPost.body,
      mediaUrls: resolvedPost.mediaImageUrls,
      coverUrl: resolvedPost.coverUrl,
      videoUrl: resolvedPost.videoUrl,
      thumbnailUrl: resolvedPost.thumbnailUrl,
      durationMs: resolvedPost.durationMs,
      status: 'published',
      visibility: 'public',
      likeCount: resolvedPost.likeCount,
      commentCount: resolvedPost.commentCount,
      shareCount: resolvedPost.shareCount,
      viewCount: 0,
      createdAt: resolvedPost.createdAt,
      updatedAt: resolvedPost.updatedAt ?? resolvedPost.createdAt,
    ),
  );
}
