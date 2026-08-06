// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-001

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/content_api_contract_harness.dart';

void main() {
  late ContentApiContractHarness harness;

  setUpAll(() async => harness = await ContentApiContractHarness.create());
  tearDownAll(() => harness.close());

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
