import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/ui/circle/models/circle_hub_feed_post_entry.dart';

void main() {
  test('circle feed 吸收 viewer result 时回写完整状态与计数', () {
    final items = <CircleHubFeedPostEntry>[
      CircleHubFeedPostEntry.fromPost(
        circleId: 'circle-1',
        post: PhotoPostDto(
          id: 'post-1',
          type: 'image',
          identity: 'work',
          assistantUsePolicy: 'inherit',
          authorId: 'author-1',
          displayName: '测试作者',
          avatarUrl: '',
          authorRoleLabel: '',
          authorIdentityTags: const <String>[],
          authorVerified: false,
          coverUrl: '',
          imageUrls: const <String>[],
          likeCount: 10,
          commentCount: 0,
          shareCount: 3,
          createdAt: DateTime.utc(2026),
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
