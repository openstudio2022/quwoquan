import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/cloud_services/content/content_mock_data.dart';
import '../../../../../support/cloud_services/content/content_post_contract_fixture.dart';

ContentPostProjection _projectionFromView(ContentPostViewData view) =>
    contentPostProjectionFixture(
      postId: view.id,
      contentType: view.type,
      contentIdentity: view.identity,
      assistantUsePolicy: view.assistantUsePolicy,
      authorId: view.authorId,
      authorDisplayName: view.displayName,
      authorAvatarUrl: view.avatarUrl,
      authorBackgroundUrl: view.authorBackgroundUrl,
      authorRoleLabel: view.authorRoleLabel,
      authorIdentityTags: view.authorIdentityTags,
      authorVerified: view.authorVerified,
      title: view.title,
      body: view.body,
      summary: view.summary,
      coverUrl: view.coverUrl,
      articleTemplate: view.articleTemplate,
      articleFontPreset: view.articleFontPreset,
      mediaUrls: view.imageUrls,
      videoUrl: view.videoUrl,
      thumbnailUrl: view.thumbnailUrl,
      width: view.width,
      height: view.height,
      durationMs: view.durationMs,
      likeCount: view.likeCount,
      commentCount: view.commentCount,
      shareCount: view.shareCount,
      createdAt: view.createdAt,
      updatedAt: view.updatedAt,
      publishedAt: view.publishedAt,
      contentVertical: view.contentVertical,
      recallPath: view.recallPath,
      supplySource: view.supplySource,
      intersectionReasons: view.intersectionReasons,
    );

ContentDiscoveryFeedPageSlice _page(List<ContentPostViewData> views) =>
    ContentDiscoveryFeedPageSlice(
      items: views.map(_projectionFromView).toList(growable: false),
      outcome: views.isEmpty
          ? ContentFeedOutcome.empty
          : ContentFeedOutcome.content,
      emptyReason: views.isEmpty
          ? ContentFeedEmptyReason.noEligibleContent
          : null,
      feedRequestId: 'feed-request-1',
      objectCards: const <FeedObjectCard>[],
    );

void main() {
  group('ContentDiscoveryFeedPageSlice — canonical items', () {
    test('photo item 保持作者、媒体、统计和时间事实', () {
      final original = ContentMockData.discoveryPhotoData.first;
      final projection = _page(<ContentPostViewData>[original]).items.single;
      final item = ContentPostViewData.fromWire(projection);

      expect(item.id, 'd1');
      expect(item.type, 'image');
      expect(item.authorId, 'nature_photographer');
      expect(item.displayName, '自然摄影师');
      expect(item.avatarUrl, contains('media/avatar/s/archived-avatar/'));
      expect(item.coverUrl, contains('media/image/s/archived-image/'));
      expect(item.imageUrls, isNotEmpty);
      expect(item.likeCount, 1200);
      expect(item.commentCount, 45);
      expect(item.shareCount, 18);
      expect(item.createdAt.year, 2025);
    });

    test('video item 保持单一视频形态和时长', () {
      final original = ContentMockData.discoveryVideoData.first;
      final item = ContentPostViewData.fromWire(
        _page(<ContentPostViewData>[original]).items.single,
      );

      expect(item.id, 'video_tokyo_midnight');
      expect(item.type, 'video');
      expect(item.authorId, 'a1');
      expect(item.displayName, '楹语小筑');
      expect(item.body, contains('东京'));
      expect(item.durationMs, 125000);
      expect(item.likeCount, 12500);
      expect(item.commentCount, 892);
      expect(item.hasVideo, isTrue);
      expect(item.imageUrls, isEmpty);
    });

    test('moment 与 article 使用同一 ContentPostProjection owner', () {
      final source = <ContentPostViewData>[
        ContentMockData.discoveryMomentData.first,
        ContentMockData.discoveryArticleData.first,
      ];
      final page = _page(source);
      final items = page.items
          .map(ContentPostViewData.fromWire)
          .toList(growable: false);

      expect(items.map((item) => item.type), <String>['micro', 'article']);
      expect(items.first.identity, 'moment');
      expect(items.last.identity, 'work');
      expect(items.last.title, contains('Web开发'));
    });

    test('每个 feed item 均具有 canonical post/author identity', () {
      final page = _page(<ContentPostViewData>[
        ...ContentMockData.discoveryPhotoData,
        ...ContentMockData.discoveryVideoData,
        ...ContentMockData.discoveryMomentData,
        ...ContentMockData.discoveryArticleData,
      ]);

      for (final projection in page.items) {
        final item = ContentPostViewData.fromWire(projection);
        expect(item.id, isNotEmpty);
        expect(item.authorId, isNotEmpty, reason: 'postId=${item.id}');
        expect(item.displayName, isNotEmpty, reason: 'postId=${item.id}');
      }
    });
  });

  group('ContentDiscoveryFeedPageSlice — single track', () {
    test('authorId 是唯一作者身份，personaId alias 被 generated decoder 拒绝', () {
      final wire = contentPostProjectionFixture(
        postId: 'subject-1',
        contentType: 'video',
        authorId: 'current-author',
        videoUrl: 'https://example.com/video.mp4',
      ).toWire()..['personaId'] = 'retired-persona';

      expect(() => ContentPostProjection.fromWire(wire), throwsFormatException);
    });

    test('feed page round-trip 保持 typed cursor envelope 和 items', () {
      final source = ContentMockData.discoveryPhotoData.first;
      final page = ContentDiscoveryFeedPageSlice(
        items: <ContentPostProjection>[_projectionFromView(source)],
        outcome: ContentFeedOutcome.content,
        nextCursor: 'feed.next',
        previousCursor: 'feed.previous',
        paginationExpiresAt: DateTime.utc(2026, 8, 4, 12),
        feedRequestId: 'feed-request-roundtrip',
        policyDigest:
            'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        objectCards: const <FeedObjectCard>[],
      );

      final decoded = ContentDiscoveryFeedPageSlice.fromWire(page.toWire());

      expect(decoded.items.single.postId, source.id);
      expect(decoded.nextCursor, 'feed.next');
      expect(decoded.previousCursor, 'feed.previous');
      expect(decoded.paginationExpiresAt, DateTime.utc(2026, 8, 4, 12));
      expect(decoded.feedRequestId, 'feed-request-roundtrip');
    });

    test('generated decoder 拒绝旧 item 字段和未知 page 字段', () {
      final page = _page(<ContentPostViewData>[
        ContentMockData.discoveryPhotoData.first,
      ]).toWire();
      final item = Map<String, Object?>.from(
        (page['items']! as List<Object?>).single! as Map,
      )..['id'] = 'retired-id';
      page['items'] = <Object?>[item];

      expect(
        () => ContentDiscoveryFeedPageSlice.fromWire(page),
        throwsFormatException,
      );

      final unknownPage = _page(const <ContentPostViewData>[]).toWire()
        ..['cursor'] = 'retired-cursor';
      expect(
        () => ContentDiscoveryFeedPageSlice.fromWire(unknownPage),
        throwsFormatException,
      );
    });

    test('缺少 required counts 或 page envelope 不再静默补零', () {
      final itemWire = contentPostProjectionFixture(
        postId: 'missing-counts',
        contentType: 'image',
      ).toWire()..remove('likeCount');
      expect(
        () => ContentPostProjection.fromWire(itemWire),
        throwsFormatException,
      );

      expect(
        () => ContentDiscoveryFeedPageSlice.fromWire(const <String, Object?>{}),
        throwsFormatException,
      );
    });

    test('empty feed 使用明确 outcome/emptyReason，不伪造成功内容', () {
      final page = _page(const <ContentPostViewData>[]);
      final decoded = ContentDiscoveryFeedPageSlice.fromWire(page.toWire());

      expect(decoded.items, isEmpty);
      expect(decoded.outcome, ContentFeedOutcome.empty);
      expect(decoded.emptyReason, ContentFeedEmptyReason.noEligibleContent);
    });
  });
}
