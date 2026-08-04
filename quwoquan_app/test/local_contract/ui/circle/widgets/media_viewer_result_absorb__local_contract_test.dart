import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_view_data.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/ui/circle/models/circle_hub_feed_post_entry.dart';
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
            assistantUsePolicy: 'inherit',
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

    CircleHubFeedPostEntry.applyResultToList(items, result);
    final next = items.single;

    expect(next.likeCount, 12);
    expect(next.shareCount, 5);
    expect(next.isLiked, isTrue);
    expect(next.isFollowingAuthor, isTrue);
  });
}
