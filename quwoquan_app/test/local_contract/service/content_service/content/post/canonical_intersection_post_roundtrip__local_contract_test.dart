// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#sit-003
// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#sit-005
// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/home-recommend-intersection-redesign/spec.md#gwt-001
// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/home-recommend-intersection-redesign/spec.md#gwt-001.t1

import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/di/content_surface_view_mapper.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_detail_payload.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_projection_codec.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/domain/work_browser_view_data.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/application/public/intersection_reason_selection.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

File _canonicalReasonFixtureFile() {
  final candidates = <File>[
    File(
      '../quwoquan_service/contracts/metadata/_shared/test_fixtures/recommendation/intersection/co_wishlisted_entity_reason.json',
    ),
    File(
      'quwoquan_service/contracts/metadata/_shared/test_fixtures/recommendation/intersection/co_wishlisted_entity_reason.json',
    ),
  ];
  for (final candidate in candidates) {
    if (candidate.existsSync()) return candidate;
  }
  throw StateError(
    'co_wishlisted_entity_reason.json not found (cwd=${Directory.current.path})',
  );
}

Map<String, Object?> _canonicalReasonWire() {
  final decoded = jsonDecode(_canonicalReasonFixtureFile().readAsStringSync());
  if (decoded is! Map) {
    throw const FormatException(
      'canonical coWishlistedEntity fixture must be an object',
    );
  }
  return Map<String, Object?>.from(decoded);
}

ContentPostDetailPayload _canonicalDetailPayload() {
  final occurredAt = DateTime.utc(2026, 8, 12, 12);
  return ContentPostDetailPayload.fromWire(
    ContentPostDetailSlice.fromWire(<String, Object?>{
      'postId': 'post-west-lake-story',
      'contentType': 'video',
      'contentIdentity': 'work',
      'authorId': 'author-west-lake',
      'authorDisplayName': '西湖记录者',
      'title': '从共同想去到一起出发',
      'body': '同一条内容从首页、视频书和深链进入。',
      'mediaAssetIds': <String>['video-west-lake'],
      'mediaUrls': <String>[
        'media/video/s/video-west-lake/post/post-west-lake-story/v1/source.mp4',
      ],
      'mediaItems': <Object?>[
        <String, Object?>{
          'kind': 'video',
          'mediaAssetId': 'video-west-lake',
          'mediaAssetVersion': 3,
          'url': 'media/video/s/video-west-lake/post/post-west-lake-story/v1/source.mp4',
          'coverUrl':
              'media/image/s/cover/post/post-west-lake-story/v1/cover.png',
          'durationMs': 45000,
          'width': 1280,
          'height': 720,
        },
      ],
      'coverUrl': 'media/image/s/cover/post/post-west-lake-story/v1/cover.png',
      'thumbnailUrl':
          'media/image/s/cover/post/post-west-lake-story/v1/cover.png',
      'videoUrl': 'media/video/s/video-west-lake/post/post-west-lake-story/v1/source.mp4',
      'width': 1280,
      'height': 720,
      'durationMs': 45000,
      'primaryHomepageId': 'homepage-west-lake',
      'primaryHomepageType': 'place',
      'gatheringRef': 'gathering-west-lake',
      'status': 'published',
      'visibility': 'public',
      'likeCount': 11,
      'commentCount': 3,
      'shareCount': 2,
      'viewCount': 101,
      'viewerLiked': true,
      'intersectionReasons': <Object?>[_canonicalReasonWire()],
      'createdAt': occurredAt.toIso8601String(),
      'updatedAt': occurredAt.toIso8601String(),
      'publishedAt': occurredAt.toIso8601String(),
    }),
  );
}

void main() {
  test('真实物化 reason 在首页、视频书与深链 Post 投影保持同一合同', () {
    final deepLinkPayload = _canonicalDetailPayload();
    final homeProjection = ContentPostProjection.fromWire(
      contentPostProjectionFromViewData(deepLinkPayload.post).toWire(),
    );
    final homePost = ContentPostViewData.fromWire(homeProjection);
    final videoBookPost = deepLinkPayload.post;
    final deepLinkPost = ContentPostViewData.fromWire(
      ContentPostProjection.fromWire(
        contentPostProjectionFromViewData(deepLinkPayload.post).toWire(),
      ),
    );

    for (final post in <ContentPostViewData>[
      homePost,
      videoBookPost,
      deepLinkPost,
    ]) {
      expect(post.id, 'post-west-lake-story');
      expect(post.viewerLiked, isTrue);
      expect(post.primaryHomepageId, 'homepage-west-lake');
      expect(post.primaryHomepageType, 'place');
      expect(post.gatheringRef, 'gathering-west-lake');
      expect(post.mediaItems, hasLength(1));
      expect(post.mediaItems.single.mediaAssetId, 'video-west-lake');
      expect(post.mediaItems.single.durationMs, 45000);

      final reason = post.intersectionReasons!.single;
      expect(reason.kind, 'coWishlistedEntity');
      expect(reason.objectKind, 'place');
      expect(reason.displayBinding, 'explicit_link');
      expect(reason.subjectContext, 'homepage:homepage-west-lake');
      expect(
        reason.primarySpans.map((span) => span.text).join(),
        reason.primaryText,
      );
      expect(reason.primarySpans.last.target?.objectId, 'homepage-west-lake');
      expect(reason.primarySpans.last.target?.routeId, 'homepageDetail');
      // 行动阶梯整条来自注册表 actionHintsByKind，唯一 primary 是 start_gathering。
      final primaryHint = reason.actionHints.where((hint) => hint.isPrimary).single;
      expect(primaryHint.actionKey, 'start_gathering');
      expect(primaryHint.dispatch, 'gathering');
      expect(
        reason.actionHints.map((hint) => hint.target?.objectId).toSet(),
        {'homepage-west-lake'},
      );

      final surface = ContentSurfaceViewMapper.fromDto(post);
      expect(surface.intersectionReasons.single.toWire(), reason.toWire());
      final resolution = resolveIntersectionDisplay(
        surface.intersectionReasons,
        contextObjectTarget: IntersectionTarget(
          objectType: 'post',
          objectId: post.id,
          objectKind: 'content',
          routeId: 'workBrowser',
        ),
        now: DateTime.utc(2026, 8, 13),
      );
      expect(resolution?.reason.toWire(), reason.toWire());
      expect(resolution?.primaryHint?.actionKey, 'start_gathering');

      final work = WorkBrowserViewData.fromPost(
        post,
        detail: deepLinkPayload.detailWire,
      );
      expect(work.videoItems, hasLength(1));
      expect(work.videoItems.single.mediaAssetId, 'video-west-lake');
      expect(work.videoItems.single.durationMs, 45000);
    }
  });
}
