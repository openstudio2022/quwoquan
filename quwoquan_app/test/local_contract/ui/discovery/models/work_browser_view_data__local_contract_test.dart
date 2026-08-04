// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-012

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_detail_payload.dart';
import 'package:quwoquan_app/content/media/media_asset/domain/work_browser_view_data.dart';
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
}
