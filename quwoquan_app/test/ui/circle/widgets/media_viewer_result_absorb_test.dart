import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/ui/circle/widgets/media_viewer_result_absorber.dart';

void main() {
  test('circle feed 吸收 viewer result 时回写完整状态与计数', () {
    final items = <Map<String, dynamic>>[
      {
        'postId': 'post-1',
        'authorId': 'author-1',
        'likeCount': 10,
        'likes': 10,
        'shareCount': 3,
        'favoriteCount': 1,
      },
    ];

    final result = MediaViewerResult(
      followingUsers: {'author-1'},
      likedPosts: {'post-1'},
      savedPosts: {'post-1'},
      postLikesCount: const {'post-1': 12},
      postBookmarksCount: const {'post-1': 2},
      postSharesCount: const {'post-1': 5},
    );

    final next = applyMediaViewerResultToFeedItems(items, result);

    expect(next.single['likeCount'], 12);
    expect(next.single['likes'], 12);
    expect(next.single['shareCount'], 5);
    expect(next.single['favoriteCount'], 2);
    expect(next.single['isLiked'], isTrue);
    expect(next.single['isSaved'], isTrue);
    expect(next.single['isFollowingAuthor'], isTrue);
  });
}
