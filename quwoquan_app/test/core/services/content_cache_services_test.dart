import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_detail_payload.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/core/services/cache/cached_content_repository.dart';
import 'package:quwoquan_app/core/services/cache/cache_management_service.dart';
import 'package:quwoquan_app/core/services/cache/content_cache_services.dart';
import 'package:quwoquan_app/core/services/cache/conversation_cache_service.dart';
import 'package:quwoquan_app/core/services/cache/user_profile_cache_service.dart';

void main() {
  group('CachedContentRepository', () {
    test('feed 查询快照命中后不重复请求远端', () async {
      final delegate = _CountingContentRepository();
      final repo = CachedContentRepository(
        delegate: delegate,
        postCache: PostObjectCacheService(),
        querySnapshotStore: ContentQuerySnapshotStore(),
      );

      final first = await repo.listDiscoveryFeedPage(category: 'moment');
      final second = await repo.listDiscoveryFeedPage(category: 'moment');

      expect(first.items.single.id, 'post_1');
      expect(second.items.single.id, 'post_1');
      expect(delegate.feedRequestCount, 1);
    });

    test('post 详情命中对象缓存后不重复请求远端', () async {
      final delegate = _CountingContentRepository();
      final repo = CachedContentRepository(
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
      final repo = CachedContentRepository(
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

class _CountingContentRepository extends Fake implements ContentRepository {
  _CountingContentRepository({PostBaseDto? post})
    : post = post ?? _postDto('post_1');

  final PostBaseDto post;
  int feedRequestCount = 0;
  int detailRequestCount = 0;

  @override
  Future<CursorPage<PostBaseDto>> listDiscoveryFeedPage({
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
    return CursorPage<PostBaseDto>(
      items: <PostBaseDto>[post],
      nextCursor: null,
    );
  }

  @override
  Future<ContentPostDetailPayload> getPost({required String postId}) async {
    detailRequestCount += 1;
    return _detailPayload(postId, post: post);
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
    'favoriteCount': 0,
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
