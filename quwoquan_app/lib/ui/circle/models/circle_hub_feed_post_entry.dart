import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';

/// 首页圈子流中单条帖子：保留 wire map 供 MediaViewer 写回，同时缓存解析后的 [PostBaseDto]。
class CircleHubFeedPostEntry {
  CircleHubFeedPostEntry._(this.raw, this.dto);

  Map<String, dynamic> raw;
  PostBaseDto? dto;

  factory CircleHubFeedPostEntry.fromMap(Map<String, dynamic> source) {
    final next = Map<String, dynamic>.from(source);
    PostBaseDto? parsed;
    try {
      parsed = postBaseDtoFromMap(next);
    } catch (_) {
      parsed = null;
    }
    return CircleHubFeedPostEntry._(next, parsed);
  }

  String get postIdForKey => (raw['postId'] ?? raw['id'] ?? '').toString();

  void applyMediaViewerResult(MediaViewerResult result) {
    final id = postIdForKey;
    if (id.isEmpty) return;

    final authorId =
        (raw['authorProfileSubjectId'] ??
                raw['authorId'] ??
                raw['userId'] ??
                '')
            .toString();

    final likeCount = result.postLikesCount[id];
    if (likeCount != null) {
      raw['likeCount'] = likeCount;
      raw['likes'] = likeCount;
    }

    final bookmarkCount = result.postBookmarksCount[id];
    if (bookmarkCount != null) {
      raw['favoriteCount'] = bookmarkCount;
      raw['bookmarkCount'] = bookmarkCount;
    }

    final shareCount = result.postSharesCount[id];
    if (shareCount != null) {
      raw['shareCount'] = shareCount;
    }

    raw['isLiked'] = result.likedPosts.contains(id);
    raw['isSaved'] = result.savedPosts.contains(id);
    if (authorId.isNotEmpty) {
      raw['isFollowingAuthor'] = result.followingUsers.contains(authorId);
    }

    try {
      dto = postBaseDtoFromMap(raw);
    } catch (_) {
      dto = null;
    }
  }

  static void applyResultToList(
    List<CircleHubFeedPostEntry> items,
    MediaViewerResult result,
  ) {
    for (final e in items) {
      e.applyMediaViewerResult(result);
    }
  }
}
