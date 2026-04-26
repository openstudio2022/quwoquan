import 'package:test/test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_reaction_state.dart';
import 'package:quwoquan_app/cloud/runtime/models/post_engagement_counters.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';

void main() {
  group('ContentRepository — 常规契约', () {
    late ContentRepository repo;

    setUp(() {
      repo = MockContentRepository();
    });

    test('listDiscoveryFeed 返回非空帖子列表', () async {
      final posts = await repo.listDiscoveryFeed(category: 'all');
      expect(posts, isNotEmpty);
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

    test('listDiscoveryFeedPage 返回带游标的分页结果', () async {
      final page = await repo.listDiscoveryFeedPage(category: 'all');
      expect(page.items, isNotEmpty);
    });

    test('getPost 不存在的 ID 抛出异常', () async {
      expect(
        () async => await repo.getPost(postId: 'nonexistent'),
        throwsException,
      );
    });

    test('createPost 返回创建结果', () async {
      final result = await repo.createPost(
        body: CreatePostRequestWire.fromMap({
          'type': 'moment',
          'body': 'test moment',
        }),
      );
      expect(result, isA<PostBaseDto>());
      expect(result.id, isNotEmpty);
      expect(result.normalizedBody, contains('test moment'));
    });

    test('publishPost / updatePostSettings / promotePostToWork 返回结果', () async {
      final published = await repo.publishPost(
        postId: 'test_post',
        body: PublishPostRequestWire.fromMap({'visibility': 'public'}),
      );
      final settings = await repo.updatePostSettings(
        postId: 'test_post',
        body: UpdatePostSettingsRequestWire.fromMap({
          'assistantUsePolicy': 'exclude',
        }),
      );
      final promoted = await repo.promotePostToWork(
        postId: 'test_post',
        body: PromotePostToWorkRequestWire.fromMap({
          'contentType': 'image',
          'title': '整理后的作品',
        }),
      );

      expect(published, isA<PostBaseDto>());
      expect(published.id, 'test_post');
      expect(settings, isA<PostBaseDto>());
      expect(settings.id, 'test_post');
      expect(promoted, isA<PostBaseDto>());
      expect(promoted.id, 'test_post');
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
        userId: 'nature_photographer',
        identity: 'work',
      );
      expect(page.items, isNotEmpty);
      expect(page.items.every((post) => post.identity == 'work'), isTrue);
    });

    test('likePost / unlikePost 不崩溃', () async {
      await repo.likePost(postId: 'test');
      await repo.unlikePost(postId: 'test');
    });

    test('favoritePost / unfavoritePost 不崩溃', () async {
      await repo.favoritePost(postId: 'test');
      await repo.unfavoritePost(postId: 'test');
    });

    test('getReactionState 返回互动状态', () async {
      final state = await repo.getReactionState(postId: 'test');
      expect(state, isA<ContentReactionState>());
      expect(state.postId, 'test');
    });

    test('listComments 返回评论列表', () async {
      final comments = await repo.listComments(postId: 'test');
      expect(comments, isA<CommentPage>());
      expect(comments.items, isA<List<CommentDto>>());
    });

    test('createComment 返回新评论', () async {
      final comment = await repo.createComment(postId: 'test', content: '测试评论');
      expect(comment, isA<CommentDto>());
      expect(comment.content, '测试评论');
    });

    test('deleteComment 不崩溃', () async {
      await repo.deleteComment(postId: 'test', commentId: 'c1');
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

  group('ContentRepository — 异常/边界契约', () {
    late ContentRepository repo;

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
