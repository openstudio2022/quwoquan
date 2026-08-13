// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#req-009

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show AssistantUsePolicy, ContentPostProjection;

// feed 卡溯源标的物理载体契约：wire `ContentPostProjection.gatheringRef`
// 必须无损进入端侧 view data；无关联内容保持 null，端不本地推断。

ContentPostProjection _wire({String? gatheringRef}) {
  return ContentPostProjection(
    postId: 'post-ref-1',
    contentType: 'image',
    contentIdentity: 'work',
    assistantUsePolicy: AssistantUsePolicy.inherit,
    authorId: 'author-1',
    authorDisplayName: '作者',
    authorAvatarUrl: '',
    authorRoleLabel: '',
    authorIdentityTags: const <String>[],
    authorVerified: false,
    body: '回顾内容',
    mediaUrls: const <String>['media/image/s/fixture/a.jpg'],
    likeCount: 0,
    commentCount: 0,
    shareCount: 0,
    createdAt: DateTime.utc(2026, 8, 12),
    gatheringRef: gatheringRef,
  );
}

void main() {
  test('wire gatheringRef 无损映射进 view data', () {
    final view = ContentPostViewData.fromWire(
      _wire(gatheringRef: 'gathering-recap-1'),
    );
    expect(view.gatheringRef, 'gathering-recap-1');
  });

  test('无关联内容 gatheringRef 保持 null，端不本地推断', () {
    final view = ContentPostViewData.fromWire(_wire());
    expect(view.gatheringRef, isNull);
  });
}
