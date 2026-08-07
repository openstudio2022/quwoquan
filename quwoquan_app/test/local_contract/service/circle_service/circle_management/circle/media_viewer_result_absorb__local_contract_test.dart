import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/public/media_viewer_extra.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/application/public/circle_hub_feed_post_entry.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/adapters/home_circles_hub_media_viewer_wiring.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('circle feed 吸收 viewer result 时回写完整状态与计数', () {
    final items = <CircleHubFeedPostEntry>[
      CircleHubFeedPostEntry.fromPost(
        circleId: 'circle-1',
        post: ContentPostViewData.fromWire(
          ContentPostProjection(
            postId: 'post-1',
            contentType: 'image',
            contentIdentity: 'work',
            assistantUsePolicy: AssistantUsePolicy.inherit,
            authorId: 'author-1',
            authorDisplayName: '测试作者',
            authorAvatarUrl: '',
            authorRoleLabel: '',
            authorIdentityTags: const <String>[],
            authorVerified: false,
            coverUrl: '',
            mediaUrls: const <String>[],
            likeCount: 10,
            commentCount: 0,
            shareCount: 3,
            createdAt: DateTime.utc(2026),
          ),
        ),
      ),
    ];

    final result = MediaViewerResult(
      followingUsers: {'author-1'},
      likedPosts: {'post-1'},
      postLikesCount: const {'post-1': 12},
      postSharesCount: const {'post-1': 5},
    );

    applyCircleHubMediaViewerResult(items, result);
    final next = items.single;

    expect(next.likeCount, 12);
    expect(next.shareCount, 5);
    expect(next.isLiked, isTrue);
    expect(next.isFollowingAuthor, isTrue);
  });

  test('circle feed projection maps once into the public read view', () {
    final entry = CircleHubFeedPostEntry.fromProjection(
      projection: CircleFeedItemView(
        circleId: 'circle-2',
        placementId: 'placement-2',
        postId: 'post-2',
        contentType: 'article',
        contentIdentity: 'work',
        authorId: 'author-2',
        authorDisplayName: '作者二',
        authorVerified: false,
        title: '公开投影',
        body: '正文',
        likeCount: 3,
        commentCount: 2,
        shareCount: 1,
        createdAt: DateTime.utc(2026),
        contentVertical: 'retired-travel-bucket',
        recallPath: 'circle_feed',
        supplySource: 'creator',
        pinned: true,
        featured: false,
      ),
    );

    expect(entry.circleId, 'circle-2');
    expect(entry.placementId, 'placement-2');
    expect(entry.postId, 'post-2');
    expect(entry.title, '公开投影');
    expect(entry.likeCount, 3);
    expect(entry.pinned, isTrue);
    expect(entry.post.recallPath, 'circle_feed');
    expect(entry.post.supplySource, 'creator');
  });
}
