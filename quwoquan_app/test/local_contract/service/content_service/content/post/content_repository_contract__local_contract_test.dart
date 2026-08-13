import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_detail_payload.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:test/test.dart';

import '../../../../../support/service/content_service/content/post/content_post_test_builder.dart';
import '../../../../../support/service/content_service/content/post/content_post_typed_doubles.dart';

List<ContentPostViewData> _suitePosts() => <ContentPostViewData>[
  contentPostViewDataBuilder(
    postId: 'repository-image',
    contentType: 'image',
    mediaUrls: const <String>[testContentImageUrl],
  ),
  contentPostViewDataBuilder(
    postId: 'repository-video',
    contentType: 'video',
    videoUrl: testContentVideoUrl,
  ),
  contentPostViewDataBuilder(postId: 'repository-micro', contentType: 'micro'),
  contentPostViewDataBuilder(
    postId: 'repository-article',
    contentType: 'article',
    title: 'Repository typed contract',
  ),
  contentPostViewDataBuilder(
    postId: 'repository-author-article',
    contentType: 'article',
    authorId: 'nature_photographer',
    title: '作者作品',
  ),
];

void main() {
  late List<ContentPostViewData> posts;
  late InMemoryContentPostStore store;
  late InMemoryContentDiscoveryFeedQuery feedQuery;
  late InMemoryContentPostDetailReader detailReader;
  late InMemoryContentAuthorPostsReader authorPostsReader;

  setUp(() {
    posts = _suitePosts();
    store = InMemoryContentPostStore(
      posts: posts,
      details: <String, ContentPostDetailPayload>{
        for (final post in posts)
          post.id: contentPostDetailPayloadBuilder(
            post: post,
            articleMarkdown: post.isArticleLike
                ? '# ${post.title}\n\nSuite-local detail.'
                : null,
          ),
      },
    );
    feedQuery = InMemoryContentDiscoveryFeedQuery(store);
    detailReader = InMemoryContentPostDetailReader(store);
    authorPostsReader = InMemoryContentAuthorPostsReader(store);
  });

  group('Content 对象级 typed doubles — 常规契约', () {
    test('feed query 返回最小多形态集合', () async {
      final page = await feedQuery.listDiscoveryFeedPage(
        category: 'all',
        limit: 0,
      );

      expect(page.items, hasLength(posts.length));
      expect(
        page.items.map((post) => post.type),
        containsAll(<String>['image', 'video', 'micro', 'article']),
      );
    });

    test('feed query 支持 identity/type 过滤', () async {
      final page = await feedQuery.listDiscoveryFeedPage(
        category: 'work',
        identity: 'work',
        type: 'article',
      );

      expect(page.items, isNotEmpty);
      expect(page.items.every((post) => post.identity == 'work'), isTrue);
      expect(page.items.every((post) => post.isArticleLike), isTrue);
    });

    test('feed query 分页并回显权威 feedRequestId', () async {
      final first = await feedQuery.listDiscoveryFeedPage(
        category: 'all',
        limit: 2,
        feedRequestId: 'frq_echo_001',
      );
      final second = await feedQuery.listDiscoveryFeedPage(
        category: 'all',
        limit: 2,
        cursor: first.nextCursor,
      );

      expect(first.items, hasLength(2));
      expect(first.nextCursor, '2');
      expect(first.feedRequestId, 'frq_echo_001');
      expect(first.policyDigest, isNotEmpty);
      expect(second.items, hasLength(2));
      expect(second.items.first.id, isNot(first.items.first.id));
    });

    test('detail reader 对已知对象返回 typed payload', () async {
      final article = posts.firstWhere((post) => post.isArticleLike);
      final detail = await detailReader.getPost(postId: article.id);

      expect(detail.post.id, article.id);
      expect(detail.detailWire.articleMarkdown, contains('#'));
      expect(detail.detailWire.articleAssetManifest, isNotNull);
    });

    test('detail reader 对未知对象返回结构化失败', () async {
      expect(
        () => detailReader.getPost(postId: 'nonexistent'),
        throwsA(isA<CloudException>()),
      );
    });

    test('author posts reader 只返回指定作者并支持 identity', () async {
      final page = await authorPostsReader.listUserPosts(
        userId: 'nature_photographer',
        identity: 'work',
      );

      expect(page.items, isNotEmpty);
      expect(
        page.items.every(
          (post) =>
              post.authorId == 'nature_photographer' && post.identity == 'work',
        ),
        isTrue,
      );
    });

    test('config double 返回显式测试配置', () async {
      final config = await InMemoryContentConfigRepository().getAppConfig();

      expect(config.content.featureFlags.enableCreateActionEntry, isTrue);
      expect(config.content.featureFlags.enableUnifiedCreateEditor, isTrue);
      expect(config.content.featureFlags.enableArticleBookReader, isTrue);
      expect(config.content.grayRelease.experimentBucket, isNotEmpty);
    });

    test('MediaAssetSlice 仅接受 canonical typed wire', () {
      final asset = MediaAssetSlice.fromWire(<String, Object?>{
        'assetId': 'm1',
        'version': 1,
        'mediaType': 'image',
        'mimeType': 'image/jpeg',
        'fileSize': 1024,
        'status': 'ready',
        'accessPolicy': 'public',
        'imageWidth': 200,
        'imageHeight': 100,
        'cdnUrl': 'https://cdn.example/m1.jpg',
      });

      expect(asset.assetId, 'm1');
      expect(asset.status, MediaAssetStatus.ready);
      expect(asset.cdnUrl, Uri.parse('https://cdn.example/m1.jpg'));
      expect(
        () => MediaAssetSlice.fromWire(<String, Object?>{
          ...asset.toWire(),
          'moderationStatus': 'approved',
        }),
        throwsFormatException,
      );
    });
  });

  group('Content 对象级 typed doubles — 边界契约', () {
    test('limit=0 返回全部对象', () async {
      final page = await feedQuery.listDiscoveryFeedPage(
        category: 'all',
        limit: 0,
      );
      expect(page.items, hasLength(posts.length));
    });

    test('空 category 不崩溃', () async {
      final page = await feedQuery.listDiscoveryFeedPage(category: '');
      expect(page.items, isList);
    });
  });
}
