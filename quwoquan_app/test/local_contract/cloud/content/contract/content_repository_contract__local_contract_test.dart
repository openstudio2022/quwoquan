import 'package:test/test.dart';
import 'package:quwoquan_app/cloud/runtime/contract_fixture_runtime_loader.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/models/post_engagement_counters.dart';
import 'package:quwoquan_app/cloud/services/content/content_read_model_projection.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';

void main() {
  group('Content facets — 常规契约', () {
    late MockContentRepository repo;

    setUp(() {
      repo = MockContentRepository();
    });

    test('listDiscoveryFeed 返回非空帖子列表', () async {
      final posts = await repo.listDiscoveryFeed(category: 'all');
      expect(posts, isNotEmpty);
    });

    test('共享内容 seed 只保留 read-model 字段，并由 codegen 投影为 App DTO', () {
      const retiredClientAliases = <String>{
        'id',
        'type',
        'identity',
        'displayName',
        'avatarUrl',
        'imageUrls',
      };
      final rawPosts = ContractFixtureRuntimeLoader.contentSeedSet()?['posts'];
      expect(rawPosts, isA<List>());
      final source = (rawPosts! as List)
          .whereType<Map>()
          .map((row) => row.cast<String, dynamic>())
          .first;

      expect(source.keys.toSet().intersection(retiredClientAliases), isEmpty);
      final post = contentPostDtoFromReadModelMap(source);
      expect(post.id, source['postId']);
      expect(post.type, source['contentType']);
      expect(post.identity, source['contentIdentity']);
      expect(post.displayName, source['authorDisplayName']);
      expect(post.avatarUrl, source['authorAvatarUrl']);
      expect(post.imageUrls, source['mediaUrls']);
    });

    test('mock 内容作者头像均引用可归档用户/圈子头像，不返回缺失 content/default 资产', () async {
      final feedPosts = await repo.listDiscoveryFeed(category: 'all', limit: 0);
      final previewPost = await repo.getPost(postId: 'nature_photographer_p1');
      final avatarUrls = <String>[
        ...feedPosts.map((post) => post.avatarUrl),
        previewPost.post.avatarUrl,
      ];

      expect(avatarUrls, isNotEmpty);
      for (final url in avatarUrls) {
        expect(url.trim(), isNotEmpty);
        expect(
          url,
          isNot(contains('media/avatar/s/archived-avatar/content/default/')),
        );
      }
    });

    test('listDiscoveryFeed 支持按 identity/type 过滤', () async {
      final works = await repo.listDiscoveryFeed(
        category: 'work',
        identity: 'work',
        type: 'article',
      );
      expect(works, isNotEmpty);
      expect(works.every((post) => post.identity == 'work'), isTrue);
      expect(works.every((post) => post.displayFormat == 'note'), isTrue);
    });

    test('alpha 首页推荐稳定返回全样式 showcase 顺序', () async {
      const expectedIds = <String>[
        'alpha_moment_grid_1',
        'alpha_moment_grid_2',
        'alpha_moment_grid_3',
        'alpha_moment_grid_4',
        'alpha_moment_grid_5',
        'alpha_moment_grid_6',
        'alpha_moment_grid_7',
        'alpha_moment_grid_8',
        'alpha_moment_grid_10',
        'alpha_photo_landscape_single',
        'alpha_photo_landscape_carousel',
        'alpha_photo_portrait_single',
        'alpha_photo_portrait_carousel',
        'alpha_photo_extreme_ratio_guard',
        'alpha_video_portrait_playable',
        'alpha_video_landscape_playable',
        'alpha_article_text_short',
        'alpha_article_text_long',
        'alpha_article_top_image',
        'alpha_article_side_image',
        'alpha_article_top_three_images',
      ];

      final recommend = await repo.listDiscoveryFeed(
        category: 'micro',
        identity: 'moment',
        limit: 0,
      );
      final explicitRecommend = await repo.listDiscoveryFeed(
        category: 'recommend',
        limit: 0,
      );
      final moment = await repo.listDiscoveryFeed(
        category: 'moment',
        identity: 'moment',
        limit: 0,
      );

      expect(recommend.map((post) => post.id).toList(), expectedIds);
      expect(explicitRecommend.map((post) => post.id).toList(), expectedIds);
      expect(moment.map((post) => post.id).toList(), expectedIds);
      expect(recommend.length, expectedIds.length);

      PostBaseDto byId(String id) =>
          recommend.firstWhere((post) => post.id == id);

      expect(byId('alpha_moment_grid_1').mediaImageUrls, hasLength(1));
      expect(byId('alpha_moment_grid_2').mediaImageUrls, hasLength(2));
      expect(byId('alpha_moment_grid_3').mediaImageUrls, hasLength(3));
      expect(byId('alpha_moment_grid_4').mediaImageUrls, hasLength(4));
      expect(byId('alpha_moment_grid_5').mediaImageUrls, hasLength(5));
      expect(byId('alpha_moment_grid_6').mediaImageUrls, hasLength(6));
      expect(byId('alpha_moment_grid_7').mediaImageUrls, hasLength(7));
      expect(byId('alpha_moment_grid_8').mediaImageUrls, hasLength(8));
      expect(
        byId('alpha_moment_grid_10').mediaImageUrls.length,
        greaterThan(9),
      );

      expect(byId('alpha_photo_landscape_single').mediaImageUrls, hasLength(1));
      expect(byId('alpha_photo_landscape_single').aspectRatio, greaterThan(1));
      expect(byId('alpha_photo_landscape_carousel').mediaImageUrls.length, 7);
      expect(byId('alpha_photo_portrait_single').mediaImageUrls, hasLength(1));
      expect(byId('alpha_photo_portrait_single').aspectRatio, lessThan(1));
      expect(byId('alpha_photo_portrait_carousel').mediaImageUrls.length, 5);
      expect(byId('alpha_photo_portrait_carousel').aspectRatio, lessThan(1));
      expect(
        byId('alpha_photo_extreme_ratio_guard').aspectRatio,
        greaterThan(4),
      );

      expect(byId('alpha_video_portrait_playable').identity, 'moment');
      expect(byId('alpha_video_portrait_playable').normalizedTitle, isEmpty);
      expect(byId('alpha_video_portrait_playable').hasVideo, isTrue);
      expect(byId('alpha_video_portrait_playable').aspectRatio, lessThan(1));
      expect(byId('alpha_video_landscape_playable').hasVideo, isTrue);
      expect(
        byId('alpha_video_landscape_playable').aspectRatio,
        greaterThan(1),
      );
      expect(byId('alpha_video_landscape_playable').durationMs, isNotNull);

      expect(byId('alpha_article_text_short').mediaCoverUrl, isEmpty);
      expect(byId('alpha_article_text_long').mediaCoverUrl, isEmpty);
      expect(byId('alpha_article_top_image').mediaCoverUrl, isNotEmpty);
      expect(byId('alpha_article_side_image').mediaCoverUrl, isNotEmpty);
      expect(byId('alpha_article_top_three_images').mediaCoverUrl, isNotEmpty);
      expect(
        recommend.every((post) => post.intersectionReasons?.isNotEmpty == true),
        isTrue,
      );
    });

    test('alpha 首页推荐分页首刷返回 showcase，禁止写入空首屏', () async {
      final page = await repo.listDiscoveryFeedPage(
        category: 'micro',
        identity: 'moment',
        limit: 20,
      );

      expect(page.items, hasLength(20));
      expect(page.nextCursor, '20');
      expect(page.items.first.id, 'alpha_moment_grid_1');
      expect(page.items.any((post) => post.mediaImageUrls.isNotEmpty), isTrue);
      expect(page.items.any((post) => post.hasVideo), isTrue);
      expect(
        page.items.every(
          (post) => post.avatarUrl.isNotEmpty && post.displayName.isNotEmpty,
        ),
        isTrue,
      );
    });

    test('listDiscoveryFeedPage 返回带游标的分页结果', () async {
      final page = await repo.listDiscoveryFeedPage(category: 'all');
      expect(page.items, isNotEmpty);
    });

    test('listDiscoveryFeedPage envelope 携带服务端权威 feedRequestId', () async {
      final page = await repo.listDiscoveryFeedPage(category: 'all');
      expect(page.feedRequestId, isNotNull);
      expect(page.feedRequestId, isNotEmpty);
      expect(page.rankingVersion, isNotEmpty);
      expect(page.reasonVersion, isNotEmpty);
    });

    test('listDiscoveryFeedPage 回显端侧传入的 feedRequestId', () async {
      final page = await repo.listDiscoveryFeedPage(
        category: 'all',
        feedRequestId: 'frq_echo_001',
      );
      expect(page.feedRequestId, 'frq_echo_001');
    });

    test('alpha/discovery mock 媒体输出与 contract seed archived 家族同源', () async {
      final posts = await repo.listDiscoveryFeed(category: 'all', limit: 0);
      final mediaUrls = posts
          .expand(
            (post) => <String>[
              post.avatarUrl,
              post.authorBackgroundUrl ?? '',
              post.mediaCoverUrl,
              post.mediaThumbnailUrl,
              post.mediaVideoUrl,
              ...post.mediaImageUrls,
            ],
          )
          .map((url) => url.trim())
          .where((url) => url.isNotEmpty)
          .toList(growable: false);

      expect(mediaUrls, isNotEmpty);
      expect(mediaUrls.any((url) => url.contains('/s/mock/')), isFalse);
      expect(
        mediaUrls.any((url) => url.contains('media/image/s/archived-image/')),
        isTrue,
      );
      expect(mediaUrls.any((url) => url.contains('media/video/s/')), isTrue);
      expect(
        mediaUrls.any((url) => url.contains('media/avatar/s/archived-avatar/')),
        isTrue,
      );
    });

    test('getPost 不存在的 ID 抛出异常', () async {
      expect(
        () async => await repo.getPost(postId: 'nonexistent'),
        throwsException,
      );
    });

    test('updatePostSettings / promotePostToWork 返回结果', () async {
      const existingPostId = 'fixture_photo_001';
      final settings = await repo.updatePostSettings(
        postId: existingPostId,
        body: UpdatePostSettingsRequestWire.fromMap({
          'assistantUsePolicy': 'exclude',
        }),
      );
      final promoted = await repo.promotePostToWork(
        postId: existingPostId,
        body: PromotePostToWorkRequestWire.fromMap({
          'contentType': 'image',
          'title': '整理后的作品',
        }),
      );

      expect(settings, isA<PostBaseDto>());
      expect(settings.id, existingPostId);
      expect(promoted, isA<PostBaseDto>());
      expect(promoted.id, existingPostId);
    });

    test('getAppConfig 返回 feature flags 与 gray release 结构', () async {
      final config = await repo.getAppConfig();
      final content = config.wireRoot['content'];
      expect(content, isA<Map>());
      final contentMap = Map<String, dynamic>.from(content! as Map);
      final featureFlags = contentMap['feature_flags'] as Map<String, dynamic>?;
      final grayRelease = contentMap['gray_release'] as Map<String, dynamic>?;

      expect(featureFlags, isNotNull);
      expect(
        featureFlags?.keys,
        containsAll(<String>[
          'enable_create_action_entry',
          'enable_unified_create_editor',
          'enable_identity_based_surfaces',
          'enable_identity_share_template',
          'enable_article_book_reader',
          'enable_article_page_curl',
          'enable_assistant_content_identity_index',
        ]),
      );
      expect(grayRelease, isNotNull);
      expect(grayRelease?['experiment_bucket'], isA<String>());
      expect(grayRelease?['current_stage'], isA<String>());
      expect(grayRelease?['canary_matrix'], isA<List<dynamic>>());

      final parsed = config.clientParsed;
      expect(
        parsed.featureFlagOverrides['enable_article_book_reader'],
        isA<bool>(),
      );
      expect(parsed.grayRelease.experimentBucket, isNotEmpty);
      expect(parsed.grayRelease.currentStage, isNotEmpty);
      expect(parsed.grayRelease.canaryMatrix, isNotEmpty);
      expect(parsed.clientStateSyncMap, isA<Map<String, dynamic>>());
    });

    test('listUserPosts 支持按 identity 过滤', () async {
      final page = await repo.listUserPosts(
        userId: 'fixture_user_photo',
        identity: 'work',
      );
      expect(page.items, isNotEmpty);
      expect(page.items.every((post) => post.identity == 'work'), isTrue);
    });

    test('listUserPosts 为用户主页 mock 记录补齐长文类型', () async {
      final page = await repo.listUserPosts(userId: 'nature_photographer');
      final articleTitles = page.items
          .where((post) => post.isArticleLike)
          .map((post) => post.normalizedTitle)
          .toList(growable: false);

      expect(articleTitles, contains('极简摄影的真谛'));
    });

    test('getPost 支持用户主页互动 targetContentId 关联内容', () async {
      final image = await repo.getPost(postId: 'nature_photographer_p1');
      final video = await repo.getPost(postId: 'nature_photographer_v2');
      final article = await repo.getPost(postId: 'nature_photographer_a2');

      expect(image.post.id, 'nature_photographer_p1');
      expect(image.post.displayFormat, 'image');
      expect(video.post.id, 'nature_photographer_v2');
      expect(video.post.isVideoLike, isTrue);
      expect(article.post.id, 'nature_photographer_a2');
      expect(article.post.isArticleLike, isTrue);
    });

    test('reportBehaviors 不崩溃', () async {
      await repo.reportBehaviors(events: []);
    });

    test('reportBehaviors 非空 ContentBehaviorBatchEventDto 不崩溃', () async {
      await repo.reportBehaviors(
        events: <ContentBehaviorBatchEventDto>[
          ContentBehaviorBatchEventDto.canonical(
            contentId: 'p1',
            eventType: 'impression',
            timestamp: DateTime.now().toUtc().toIso8601String(),
            durationMs: 12,
          ),
        ],
      );
    });

    test('ContentMediaAssetWireDto 解析 derivatives 与 moderationStatus', () {
      final dto = ContentMediaAssetWireDto.fromMap({
        'id': 'm1',
        'status': 'ready',
        'derivatives': <Map<String, dynamic>>[
          <String, dynamic>{'url': 'https://cdn.example/w200', 'width': 200},
        ],
        'moderationStatus': 'approved',
        'errorCode': 'none',
      });
      expect(dto.derivatives, isNotNull);
      expect(dto.derivatives!.length, 1);
      expect(dto.derivatives!.first['url'], 'https://cdn.example/w200');
      expect(dto.moderationStatus, 'approved');
      expect(dto.errorCode, 'none');
    });

    test('getCounters 返回计数器', () async {
      final counters = await repo.getCounters(postId: 'test');
      expect(counters, isA<PostEngagementCounters>());
    });

    test('接口包含 identity create-flow 关键 API 方法', () {
      final methods = <String>[
        'createPost',
        'publishPost',
        'updatePostSettings',
        'promotePostToWork',
        'updatePost',
        'deletePost',
      ];
      expect(
        methods,
        containsAll(<String>[
          'createPost',
          'publishPost',
          'updatePostSettings',
          'promotePostToWork',
        ]),
      );
    });
  });

  group('Content facets — 异常/边界契约', () {
    late MockContentRepository repo;

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
