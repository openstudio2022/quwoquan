import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_detail_payload.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/core/services/cache/cached_content_repository.dart';
import 'package:quwoquan_app/core/services/cache/cache_read_result.dart';
import 'package:quwoquan_app/core/services/cache/cache_management_service.dart';
import 'package:quwoquan_app/core/services/cache/cache_telemetry_sink.dart';
import 'package:quwoquan_app/core/services/cache/content_cache_services.dart';
import 'package:quwoquan_app/core/services/cache/conversation_cache_service.dart';
import 'package:quwoquan_app/core/services/cache/object_cache_store.dart';
import 'package:quwoquan_app/core/services/cache/user_profile_cache_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

CachedContentRepository _cachedContentRepository({
  required _CountingContentRepository delegate,
  required PostObjectCacheService postCache,
  required ContentQuerySnapshotStore querySnapshotStore,
  UserProfileCacheService? userProfileCache,
  Future<void> Function(String avatarUrl)? avatarPreloader,
}) {
  return CachedContentRepository(
    readDelegate: delegate,
    writeDelegate: MockContentRepository(),
    postCache: postCache,
    querySnapshotStore: querySnapshotStore,
    userProfileCache: userProfileCache,
    avatarPreloader: avatarPreloader,
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('ObjectCacheStore', () {
    test(
      'maxMemoryEntries constrains hot memory while rebuildable bucket remains available',
      () {
        final store = ObjectCacheStore<String>(maxMemoryEntries: 1);

        store.put('post_1', 'one');
        store.put('post_2', 'two');

        expect(store.memoryCount, 1);
        expect(store.diskCount, 2);
        expect(store.get('post_1')?.value, 'one');
        expect(store.memoryCount, 1);
      },
    );
  });

  group('CachedContentRepository', () {
    test('feed 查询优先请求远端，失败时才回退快照', () async {
      final delegate = _CountingContentRepository();
      final repo = _cachedContentRepository(
        delegate: delegate,
        postCache: PostObjectCacheService(),
        querySnapshotStore: ContentQuerySnapshotStore(),
      );

      final first = await repo.listDiscoveryFeedPage(category: 'moment');
      final second = await repo.listDiscoveryFeedPage(category: 'moment');
      delegate.failFeedRequests = true;
      final fallback = await repo.listDiscoveryFeedPage(category: 'moment');

      expect(first.items.single.id, 'post_1');
      expect(second.items.single.id, 'post_1');
      expect(delegate.feedRequestCount, 3);
      expect(fallback.items.single.id, 'post_1');
      expect(fallback.isCacheFallback, isTrue);
      expect(fallback.cacheFallbackError, isA<StateError>());
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
        items: <PostBaseDto>[_postDto('post_1')],
        nextCursor: 'cursor_2',
        feedRequestId: 'feed_request_1',
      );
      await store.flushPersistence();
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
      expect(cached.value.feedRequestId, 'feed_request_1');
      expect(cached.diagnostics.hitLayer, 'querySnapshot.disk');
    });

    test('query snapshot 持久化只保留第一页和最近页并截断 projection', () async {
      SharedPreferences.setMockInitialValues(<String, Object>{});
      const storageKey = 'qwq.content_query_snapshots.policy.test';
      final store = ContentQuerySnapshotStore(
        persistToPreferences: true,
        storageKey: storageKey,
        persistencePolicy: const ContentQuerySnapshotPersistencePolicy(
          maxItemsPerSnapshot: 30,
          maxUserPostSubjects: 1,
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
      final manyPosts = List<PostBaseDto>.generate(
        35,
        (index) => _postDto('feed_$index'),
      );
      store.put(key: firstFeedKey, items: manyPosts);
      await Future<void>.delayed(const Duration(milliseconds: 1));
      store.put(
        key: middleFeedKey,
        items: <PostBaseDto>[_postDto('middle_feed')],
      );
      await Future<void>.delayed(const Duration(milliseconds: 1));
      store.put(
        key: latestFeedKey,
        items: <PostBaseDto>[_postDto('latest_feed')],
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
      store.put(key: oldUserKey, items: <PostBaseDto>[_postDto('old_user')]);
      await Future<void>.delayed(const Duration(milliseconds: 1));
      store.put(
        key: latestUserKey,
        items: <PostBaseDto>[_postDto('latest_user')],
      );
      await store.flushPersistence();

      final restored = ContentQuerySnapshotStore(
        persistToPreferences: true,
        storageKey: storageKey,
        persistencePolicy: const ContentQuerySnapshotPersistencePolicy(
          maxItemsPerSnapshot: 30,
          maxUserPostSubjects: 1,
        ),
        telemetrySink: const NoopCacheTelemetrySink(),
      );
      await restored.ensureHydrated();

      expect(restored.get(firstFeedKey)?.value.items, hasLength(30));
      expect(restored.get(middleFeedKey), isNull);
      expect(restored.get(latestFeedKey)?.value.items.single.id, 'latest_feed');
      expect(restored.get(oldUserKey), isNull);
      expect(restored.get(latestUserKey)?.value.items.single.id, 'latest_user');
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
      store.put(key: queryKey, items: <PostBaseDto>[_postDto('post_1')]);
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

      store.put(key: queryKey, items: <PostBaseDto>[_postDto('post_2')]);
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
      );
      postCache.putDetail(_detailPayload('post_1'));
      queryStore.put(
        key: 'surface=discoveryFeed&cursor=',
        items: <PostBaseDto>[_postDto('post_1')],
      );

      final result = await service.clear(CacheClearLevel.offlineContent);

      expect(result.objectsRemoved, 2);
      expect(result.protectedObjects, conversationCache.activeDiskCount);
      expect(service.estimateUsage().postObjects, 1);
      expect(service.estimateUsage().querySnapshots, 0);
    });
  });
}

class _CountingContentRepository extends Fake implements ContentReadRepository {
  _CountingContentRepository({PostBaseDto? post})
    : post = post ?? _postDto('post_1');

  final PostBaseDto post;
  int feedRequestCount = 0;
  int detailRequestCount = 0;
  int userPostsRequestCount = 0;
  bool failFeedRequests = false;
  bool failUserPostsRequests = false;

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
    feedRequestCount += 1;
    if (failFeedRequests) {
      throw StateError('feed offline');
    }
    return DiscoveryFeedPage(
      items: <PostBaseDto>[post],
      nextCursor: null,
      feedRequestId: feedRequestId?.trim().isNotEmpty == true
          ? feedRequestId!.trim()
          : 'frq_mock_${DateTime.now().microsecondsSinceEpoch}',
    );
  }

  @override
  Future<ContentPostDetailPayload> getPost({required String postId}) async {
    detailRequestCount += 1;
    return _detailPayload(postId, post: post);
  }

  @override
  Future<CursorPage<PostBaseDto>> listUserPosts({
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
    return CursorPage<PostBaseDto>(
      items: <PostBaseDto>[post],
      nextCursor: null,
    );
  }
}

PostBaseDto _postDto(String id, {String avatarUrl = ''}) {
  return postBaseDtoFromMap(<String, dynamic>{
    'postId': id,
    'id': id,
    '_id': id,
    'contentType': 'micro',
    'contentIdentity': 'moment',
    'identity': 'moment',
    'authorId': 'user_1',
    'displayName': '用户一',
    'avatarUrl': avatarUrl,
    'body': '缓存内容',
    'mediaUrls': <String>[],
    'likeCount': 0,
    'commentCount': 0,
    'shareCount': 0,
    'createdAt': '2026-05-19T00:00:00.000Z',
    'updatedAt': '2026-05-19T00:00:00.000Z',
  });
}

ContentPostDetailPayload _detailPayload(String id, {PostBaseDto? post}) {
  return ContentPostDetailPayload.fromWire(<String, dynamic>{
    ...(post ?? _postDto(id)).toMap(),
    'postId': id,
    '_id': id,
    'cards': <Map<String, dynamic>>[],
    'circleSummaries': <Map<String, dynamic>>[],
  });
}
