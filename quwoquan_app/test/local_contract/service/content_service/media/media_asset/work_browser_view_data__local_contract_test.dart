// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-012

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_detail_payload.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/domain/work_browser_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
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
