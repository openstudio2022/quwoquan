import 'package:quwoquan_app/core/models/media_viewer_extra.dart';

List<Map<String, dynamic>> applyMediaViewerResultToFeedItems(
  List<Map<String, dynamic>> items,
  MediaViewerResult result,
) {
  return items.map((item) {
    final id = (item['postId'] ?? item['id'] ?? '').toString();
    if (id.isEmpty) return item;

    final next = Map<String, dynamic>.from(item);
    final authorId =
        (item['authorProfileSubjectId'] ?? item['authorId'] ?? item['userId'] ?? '')
            .toString();

    final likeCount = result.postLikesCount[id];
    if (likeCount != null) {
      next['likeCount'] = likeCount;
      next['likes'] = likeCount;
    }

    final bookmarkCount = result.postBookmarksCount[id];
    if (bookmarkCount != null) {
      next['favoriteCount'] = bookmarkCount;
      next['bookmarkCount'] = bookmarkCount;
    }

    final shareCount = result.postSharesCount[id];
    if (shareCount != null) {
      next['shareCount'] = shareCount;
    }

    next['isLiked'] = result.likedPosts.contains(id);
    next['isSaved'] = result.savedPosts.contains(id);
    if (authorId.isNotEmpty) {
      next['isFollowingAuthor'] = result.followingUsers.contains(authorId);
    }

    return next;
  }).toList(growable: false);
}
