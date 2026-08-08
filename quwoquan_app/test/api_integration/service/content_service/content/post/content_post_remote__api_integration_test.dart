// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-001
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/text-post-commercial-publication/spec.md#gwt-005
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/spec.md#sit-002
// readiness_case: post_get_feed_app_api
// readiness_case: post_submit_post_publication_app_api
// readiness_case: post_get_post_app_api
// readiness_case: post_list_user_posts_app_api
// readiness_case: post_delete_post_app_api

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/content_api_contract_harness.dart';

void main() {
  late ContentApiContractHarness harness;
  var harnessCreated = false;

  setUpAll(() async {
    harness = await ContentApiContractHarness.create();
    harnessCreated = true;
  });
  tearDownAll(() async {
    if (harnessCreated) {
      await harness.close();
    }
  });

  test('production feed Remote 返回 canonical image ViewData 与 cursor', () async {
    final stopwatch = Stopwatch()..start();
    final page = await harness.feed.listDiscoveryFeedPage(
      category: 'photo',
      type: 'image',
      limit: 20,
    );
    stopwatch.stop();

    expect(stopwatch.elapsedMilliseconds, lessThan(800));
    expect(page.items, isNotEmpty);
    expect(page.nextCursor, allOf(isNotNull, isNotEmpty));
    expect(page.feedRequestId, allOf(isNotNull, isNotEmpty));
    expect(page.policyDigest, isA<String>());
    expect(page.items.map((item) => item.type), everyElement('image'));
  });

  test('production feed Remote 第二页与第一页无重叠 postId', () async {
    final first = await harness.feed.listDiscoveryFeedPage(
      category: 'photo',
      type: 'image',
      limit: 20,
    );
    final second = await harness.feed.listDiscoveryFeedPage(
      category: 'photo',
      type: 'image',
      limit: 20,
      cursor: first.nextCursor,
    );

    expect(
      first.items
          .map((item) => item.id)
          .toSet()
          .intersection(second.items.map((item) => item.id).toSet()),
      isEmpty,
    );
  });

  test('image feed 在具备尺寸时投影正数 aspectRatio', () async {
    final page = await harness.feed.listDiscoveryFeedPage(
      category: 'photo',
      type: 'image',
      limit: 5,
    );

    expect(page.items, isNotEmpty);
    for (final item in page.items) {
      final hasDimensions =
          item.width != null && item.height != null && item.height! > 0;
      expect(item.aspectRatio, hasDimensions ? greaterThan(0) : isNull);
    }
  });

  test('视频书 feed 返回可播放 canonical video ViewData', () async {
    final page = await harness.feed.listDiscoveryFeedPage(
      category: 'video',
      identity: 'work',
      type: 'video',
      limit: 20,
    );

    expect(page.items, isNotEmpty);
    for (final item in page.items) {
      expect(item.identity, 'work');
      expect(item.type, 'video');
      expect(item.videoUrl, allOf(isNotNull, isNotEmpty));
    }
  });

  test('production publication 立即由 GetPost 与 Persona 作品列表回读同一 micro', () async {
    final sequence = DateTime.now().microsecondsSinceEpoch;
    final publishIntentId = 'content-api-micro-$sequence';
    final personaId = harness.session.activePersona?.personaId.trim() ?? '';
    expect(personaId, isNotEmpty);
    final command = SubmitContentPostPublicationCommand(
      publishIntentId: publishIntentId,
      localDraftId: 'draft-$publishIntentId',
      contentType: ContentType.micro,
      contentIdentity: ContentIdentity.moment,
      body: 'API contract micro $sequence',
      visibility: Visibility.public,
    );

    final receipt = await harness.publication.submitPostPublication(command);
    final replay = await harness.publication.submitPostPublication(command);
    expect(receipt.publishIntentId, publishIntentId);
    expect(receipt.localDraftId, command.localDraftId);
    expect(receipt.postId, isNotEmpty);
    expect(receipt.state, 'published');
    expect(receipt.committedVersion, greaterThan(0));
    expect(replay.toWire(), receipt.toWire());

    final detail = await harness.posts.getPost(postId: receipt.postId);
    expect(detail.post.id, receipt.postId);
    expect(detail.post.authorId, personaId);
    expect(detail.post.type, 'micro');
    expect(detail.post.identity, 'moment');
    expect(detail.post.publishedAt, isNotNull);

    final posts = await harness.posts.listUserPosts(
      userId: personaId,
      identity: 'moment',
      type: 'micro',
      visibility: 'public',
      limit: 20,
    );
    expect(posts.items, isNotEmpty);
    expect(posts.items.map((item) => item.id), contains(receipt.postId));
    final projected = posts.items.firstWhere(
      (item) => item.id == receipt.postId,
    );
    expect(projected.authorId, personaId);
    expect(projected.publishedAt, isNotNull);

    final deleteIntentId = 'delete-$publishIntentId';
    final deleted = await harness.postDeletion.deletePost(
      postId: receipt.postId,
      idempotencyKey: deleteIntentId,
    );
    final deleteReplay = await harness.postDeletion.deletePost(
      postId: receipt.postId,
      idempotencyKey: deleteIntentId,
    );
    expect(deleted.postId, receipt.postId);
    expect(deleted.status, PostStatus.deleted);
    expect(deleted.replayed, isFalse);
    expect(deleteReplay.postId, receipt.postId);
    expect(deleteReplay.status, PostStatus.deleted);
    expect(deleteReplay.replayed, isTrue);
    await expectLater(
      harness.posts.getPost(postId: receipt.postId),
      throwsA(
        isA<CloudException>()
            .having((error) => error.statusCode, 'statusCode', 410)
            .having(
              (error) => error.code,
              'code',
              'CONTENT.USER.content_deleted',
            )
            .having(
              (error) => error.sourceOperationId,
              'sourceOperationId',
              AppCloudOperationIds.contentPostGetPost,
            ),
      ),
    );

    final events = await harness.telemetry.waitForEvents(minimumCount: 7);
    for (final expected in const <(String, int)>[
      (AppCloudOperationIds.contentPostSubmitPostPublication, 202),
      (AppCloudOperationIds.contentPostGetPost, 200),
      (AppCloudOperationIds.contentPostListUserPosts, 200),
      (AppCloudOperationIds.contentPostDeletePost, 200),
    ]) {
      final operationId = expected.$1;
      final operationEvents = events
          .where((event) => event.canonicalOperationId == operationId)
          .toList(growable: false);
      expect(operationEvents, isNotEmpty, reason: operationId);
      expect(
        operationEvents.any(
          (event) => event.succeeded && event.statusCode == expected.$2,
        ),
        isTrue,
      );
      expect(
        operationEvents.every((event) => event.requestId.isNotEmpty),
        isTrue,
      );
      expect(
        operationEvents.every((event) => event.traceId.isNotEmpty),
        isTrue,
      );
    }
    final deletedReadbackEvent = events.firstWhere(
      (event) =>
          event.canonicalOperationId ==
              AppCloudOperationIds.contentPostGetPost &&
          !event.succeeded &&
          event.statusCode == 410,
    );
    expect(deletedReadbackEvent.requestId, isNotEmpty);
    expect(deletedReadbackEvent.traceId, isNotEmpty);
  });

  test('production post Remote 保留 canonical post_not_found error', () async {
    await expectLater(
      harness.posts.getPost(postId: 'nonexistent_00000000'),
      throwsA(
        isA<CloudException>()
            .having((error) => error.statusCode, 'statusCode', 404)
            .having(
              (error) => error.code,
              'code',
              'CONTENT.USER.post_not_found',
            ),
      ),
    );
  });

  test(
    'production publication Remote 保留 media_not_ready retry error',
    () async {
      final publishIntentId =
          'content-media-not-ready-${DateTime.now().microsecondsSinceEpoch}';
      await expectLater(
        harness.publication.submitPostPublication(
          SubmitContentPostPublicationCommand(
            publishIntentId: publishIntentId,
            localDraftId: 'draft-$publishIntentId',
            contentType: ContentType.image,
            contentIdentity: ContentIdentity.work,
            mediaAssetIds: const <String>['fixture_media_not_ready'],
            visibility: Visibility.public,
          ),
        ),
        throwsA(
          isA<CloudException>()
              .having(
                (error) => error.code,
                'code',
                'CONTENT.USER.media_not_ready',
              )
              .having(
                (error) => error.retryAfter,
                'retryAfter',
                const Duration(seconds: 3),
              ),
        ),
      );
    },
  );
}
