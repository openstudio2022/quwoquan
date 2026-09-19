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
  contentPostViewDataBuilder(
    postId: 'repository-plain-article',
    contentType: 'article',
    body: '无标题的纯文字文章',
  ),
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
            articleMarkdown: post.type == ContentType.article
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
        containsAll(<ContentType>[
          ContentType.image,
          ContentType.video,
          ContentType.article,
        ]),
      );
    });

    test('feed query 仅按 canonical type 筛选文章', () async {
      final page = await feedQuery.listDiscoveryFeedPage(
        category: 'article',
        type: 'article',
      );

      expect(page.items, isNotEmpty);
      expect(
        page.items.every((post) => post.type == ContentType.article),
        isTrue,
      );
    });

    test('显式类型与类型 category 精确筛选，photo 仅作为 surface 别名', () async {
      for (final type in ContentType.values) {
        final expected = posts
            .where((post) => post.type == type)
            .map((post) => post.id);
        final explicit = await feedQuery.listDiscoveryFeedPage(
          category: 'all',
          type: type.wireName,
          limit: 0,
        );
        final category = await feedQuery.listDiscoveryFeedPage(
          category: type.wireName,
          limit: 0,
        );
        expect(explicit.items.map((post) => post.id), expected);
        expect(category.items.map((post) => post.id), expected);
        expect(explicit.items, isNotEmpty);
      }
      final photo = await feedQuery.listDiscoveryFeedPage(category: 'photo');
      expect(photo.items.map((post) => post.id), ['repository-image']);
    });

    test('非类型推荐 category 不误筛成空列表，channel 路由忽略类型筛选', () async {
      for (final category in ['', 'all', 'recommend', 'following', 'travel']) {
        final page = await feedQuery.listDiscoveryFeedPage(
          category: category,
          limit: 0,
        );
        expect(page.items.map((post) => post.id), posts.map((post) => post.id));
      }
      final page = await feedQuery.listDiscoveryFeedPage(
        category: 'article',
        channelId: 'recommend',
        type: 'article',
        limit: 0,
      );
      expect(page.items.map((post) => post.id), posts.map((post) => post.id));
    });

    test('精品池仍只返回明确登记的对象，不按类型替代精品资格', () async {
      final premiumQuery = InMemoryContentDiscoveryFeedQuery(
        store,
        premiumPostIds: {'repository-image', 'repository-article'},
      );
      final page = await premiumQuery.listDiscoveryFeedPage(
        category: 'premium',
      );
      expect(page.items.map((post) => post.id), [
        'repository-image',
        'repository-article',
      ]);
    });

    test('显式未知和退役类型失败，不用别名降级或空列表伪装', () async {
      for (final type in ['micro', 'photo', 'note', 'future-type']) {
        await expectLater(
          feedQuery.listDiscoveryFeedPage(category: 'all', type: type),
          throwsFormatException,
        );
        await expectLater(
          authorPostsReader.listUserPosts(
            userId: posts.first.authorId,
            type: type,
          ),
          throwsFormatException,
        );
      }
    });

    test('作者类型过滤保留匹配对象与分页顺序', () async {
      final authorId = posts.first.authorId;
      final expected = posts
          .where(
            (post) =>
                post.authorId == authorId && post.type == ContentType.article,
          )
          .toList();
      expect(expected, hasLength(2));
      final first = await authorPostsReader.listUserPosts(
        userId: authorId,
        type: 'article',
        limit: 1,
      );
      final second = await authorPostsReader.listUserPosts(
        userId: authorId,
        type: 'article',
        cursor: first.nextCursor,
        limit: 1,
      );
      expect(first.items.single.id, expected.first.id);
      expect(first.nextCursor, '1');
      expect(second.items.single.id, expected.last.id);
      expect(second.nextCursor, isNull);
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
      final article = posts.firstWhere(
        (post) => post.type == ContentType.article,
      );
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

    test('author posts reader 只返回指定作者，不按旧身份分轨', () async {
      final page = await authorPostsReader.listUserPosts(
        userId: 'nature_photographer',
      );

      expect(page.items, isNotEmpty);
      expect(
        page.items.every((post) => post.authorId == 'nature_photographer'),
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
      expect(page.items.map((post) => post.id), posts.map((post) => post.id));
    });
  });
}
