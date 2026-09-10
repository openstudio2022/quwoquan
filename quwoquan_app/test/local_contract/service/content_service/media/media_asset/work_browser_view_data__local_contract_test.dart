// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-012

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_detail_payload.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/domain/work_browser_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('来源记录原样保留权利词汇并拒绝非法 schema', () {
    final wire = <String, Object?>{
      'isOriginal': false,
      'originalCreatorName': '摄影师',
      'platform': 'Wikimedia Commons',
      'sourcePostUrl': 'https://example.com/source',
      'originalAssetUrl': 'https://example.com/image.jpg',
      'attributionText': '摄影师 / CC BY 4.0',
      'rightsBasis': 'CC BY 4.0',
      'commercialAuthorizationStatus': 'unverified',
      'publicationAdmission': 'research_release',
      'derivedModifications': <String>['crop', 'resize'],
      'watermarkKind': 'author_signature',
      'watermarkNote': '保留作者签名',
      'watermarkStatus': 'present',
      'audioRightsStatus': 'no_audio',
      'modelReleaseStatus': 'not_required',
      'propertyReleaseStatus': 'not_required',
      'collectedAt': '2026-09-09T00:00:00.000Z',
      'takedownPolicy': 'notice_and_takedown',
    };
    final attribution = SourceAttribution.fromWire(wire);
    expect(attribution.toWire()['derivedModifications'], <String>[
      'crop',
      'resize',
    ]);
    expect(attribution.watermarkKind, SourceWatermarkKind.authorSignature);
    expect(attribution.watermarkNote, '保留作者签名');
    expect(attribution.commercialAuthorizationStatus, 'unverified');
    expect(attribution.rightsBasis, 'CC BY 4.0');
    expect(attribution.publicationAdmission, 'research_release');
    expect(attribution.toWire(), wire);
    // 来源权利记录不是 release 类别，解码不得重写或升级原始权利事实。
    final commerciallyAuthorizedWire = <String, Object?>{
      ...wire,
      'commercialAuthorizationStatus': 'verified',
      'publicationAdmission': 'commercial_release',
    };
    final commerciallyAuthorized = SourceAttribution.fromWire(
      commerciallyAuthorizedWire,
    );
    expect(commerciallyAuthorized.publicationAdmission, 'commercial_release');
    expect(commerciallyAuthorized.commercialAuthorizationStatus, 'verified');
    expect(commerciallyAuthorized.rightsBasis, 'CC BY 4.0');
    expect(commerciallyAuthorized.toWire(), commerciallyAuthorizedWire);
    for (final invalid in <Map<String, Object?>>[
      <String, Object?>{...wire, 'publicationAdmission': 42},
      <String, Object?>{...wire, 'publicationAdmission': null},
      <String, Object?>{...wire}..remove('publicationAdmission'),
      <String, Object?>{...wire, 'riskAcceptanceId': null},
      <String, Object?>{...wire, 'derivedModifications': null},
      <String, Object?>{
        ...wire,
        'derivedModifications': <String>['unknown'],
      },
      <String, Object?>{...wire}..remove('derivedModifications'),
    ]) {
      expect(
        () => SourceAttribution.fromWire(invalid),
        throwsA(isA<FormatException>()),
      );
    }
    final unchanged = SourceAttribution.fromWire(<String, Object?>{
      ...wire,
      'derivedModifications': <String>[],
    });
    expect(unchanged.derivedModifications, isEmpty);
  });
  test('decoded image captions keep asset order and never borrow titles', () {
    final payload = ContentPostDetailPayload.fromWire(
      ContentPostDetailSlice.fromWire(<String, Object?>{
        'postId': 'image-caption-chain',
        'contentType': 'image',
        'contentIdentity': 'work',
        'authorId': 'author-1',
        'authorDisplayName': '作者',
        'authorAvatarUrl': '',
        'title': '作品标题不是逐图说明',
        'body': '作品正文不是逐图说明',
        'sourceAttribution': <String, Object?>{
          'isOriginal': false,
          'originalCreatorName': '摄影师甲',
          'platform': 'Wikimedia Commons',
          'sourcePostUrl': 'https://example.com/source',
          'originalAssetUrl': 'https://example.com/image.jpg',
          'attributionText': '摄影师甲 / CC BY 4.0',
          'rightsBasis': 'CC BY 4.0',
          'commercialAuthorizationStatus': 'unverified',
          'publicationAdmission': 'research_release',
          'derivedModifications': <String>['crop', 'resize'],
          'watermarkKind': 'author_signature',
          'watermarkNote': '保留作者签名',
          'watermarkStatus': 'present',
          'audioRightsStatus': 'no_audio',
          'modelReleaseStatus': 'not_required',
          'propertyReleaseStatus': 'not_required',
          'collectedAt': '2026-09-09T00:00:00.000Z',
          'takedownPolicy': 'notice_and_takedown',
        },
        'mediaItems': <Object?>[
          <String, Object?>{
            'kind': 'image',
            'url': 'https://img.example.com/b.jpg',
            'mediaAssetId': 'asset-b',
            'accessMode': 'public',
            'title': '资产标题',
            'caption': '第一图的真实说明',
          },
          <String, Object?>{
            'kind': 'image',
            'url': 'https://img.example.com/a.jpg',
            'mediaAssetId': 'asset-a',
            'accessMode': 'public',
            'title': '不能伪造说明',
          },
        ],
        'status': 'published',
        'visibility': 'public',
        'likeCount': 0,
        'commentCount': 0,
        'shareCount': 0,
        'viewCount': 0,
        'createdAt': '2026-09-09T00:00:00Z',
        'updatedAt': '2026-09-09T00:00:00Z',
      }),
    );
    final attribution = payload.post.sourceAttribution!;
    expect(attribution.commercialAuthorizationStatus, 'unverified');
    expect(attribution.rightsBasis, 'CC BY 4.0');
    expect(attribution.publicationAdmission, 'research_release');
    expect(attribution.toWire()['publicationAdmission'], 'research_release');
    expect(attribution.derivedModifications, <SourceDerivedModification>[
      SourceDerivedModification.crop,
      SourceDerivedModification.resize,
    ]);
    expect(attribution.watermarkKind, SourceWatermarkKind.authorSignature);
    expect(attribution.watermarkNote, '保留作者签名');
    expect(attribution.toWire().containsKey('riskAcceptanceId'), isFalse);
    for (final view in <WorkBrowserViewData>[
      WorkBrowserViewData.fromPost(payload.post),
      WorkBrowserViewData.fromPost(payload.post, detail: payload.detailWire),
      WorkBrowserViewData.fromPost(
        payload.post,
        supplemental: <String, Object?>{
          'mediaItems': <Object?>[
            <String, Object?>{
              'kind': 'image',
              'url': 'https://img.example.com/stale.jpg',
              'title': '旧语义 fallback 不得覆盖新 caption',
            },
          ],
        },
      ),
      WorkBrowserViewData.fromPost(
        payload.post,
        supplemental: payload.mergedArticleWireMap,
      ),
    ]) {
      expect(view.mediaItems.map((item) => item.mediaAssetId), <String>[
        'asset-b',
        'asset-a',
      ]);
      expect(view.effectiveImageUrls, <String>[
        'https://img.example.com/b.jpg',
        'https://img.example.com/a.jpg',
      ]);
      expect(view.imageCaptionAt(0), '第一图的真实说明');
      expect(view.mediaItems.first.title, '资产标题');
      expect(view.imageCaptionAt(1), isNull);
      expect(view.imageCaptionAt(-1), isNull);
      expect(view.imageCaptionAt(2), isNull);
    }
  });
  test('typed Post detail keeps entity mentions for immersive routing', () {
    final occurredAt = DateTime.utc(2026, 8, 4);
    final payload = ContentPostDetailPayload.fromWire(
      ContentPostDetailSlice(
        postId: 'article-entity-mention',
        contentType: 'article',
        contentIdentity: 'work',
        authorId: 'author-1',
        authorDisplayName: '作者',
        authorAvatarUrl: '',
        title: '杭州一日游',
        articleMarkdown: '@[灵隐寺](entity:sight:west_lake)',
        markdownDialect: 'qwq-rich-md',
        entityMentions: const <PostEntityMention>[
          PostEntityMention(
            subjectType: 'entity',
            subjectId: 'entity:sight:west_lake',
            homepageId: 'homepage_sight_west_lake',
            displayName: '灵隐寺',
            rangeStart: 0,
            rangeEnd: 3,
          ),
        ],
        status: 'published',
        visibility: 'public',
        likeCount: 0,
        commentCount: 0,
        shareCount: 0,
        viewCount: 0,
        createdAt: occurredAt,
        updatedAt: occurredAt,
      ),
    );

    final view = WorkBrowserViewData.fromPost(
      payload.post,
      supplemental: payload.mergedArticleWireMap,
    );

    expect(view.entityMentions, hasLength(1));
    expect(view.entityMentions.single.subjectId, 'entity:sight:west_lake');
    expect(view.entityMentions.single.homepageId, 'homepage_sight_west_lake');
  });
  test('canonical Post mediaItems provide immersive typed delivery without supplemental raw', () {
    final occurredAt = DateTime.utc(2026, 8, 4);
    final post = ContentPostViewData.fromWire(
      ContentPostProjection(
        postId: 'video-post-media-items',
        contentType: 'video',
        contentIdentity: 'work',
        assistantUsePolicy: AssistantUsePolicy.inherit,
        authorId: 'author-1',
        authorDisplayName: '作者',
        authorAvatarUrl: '',
        authorRoleLabel: '',
        authorIdentityTags: const <String>[],
        authorVerified: false,
        videoUrl: 'media/video/s/video-1/v1/source.mp4',
        mediaItems: const <PostMediaItem>[
          PostMediaItem(
            kind: 'video',
            url: 'media/video/s/video-1/v1/source.mp4',
            mediaAssetId: 'asset-video-1',
            accessMode: MediaDeliveryAccessMode.signedGrant,
          ),
        ],
        likeCount: 0,
        commentCount: 0,
        shareCount: 0,
        createdAt: occurredAt,
      ),
    );

    final view = WorkBrowserViewData.fromPost(post);

    expect(view.mediaItems, hasLength(1));
    expect(view.mediaItems.single.mediaAssetId, 'asset-video-1');
    expect(
      view.mediaItems.single.accessMode,
      MediaDeliveryAccessMode.signedGrant,
    );
  });
}
