import 'package:quwoquan_app/ui/content/post_summary_view.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/post_base_dto.dart';

class MediaViewerInteractionSnapshot {
  const MediaViewerInteractionSnapshot({
    this.followingUsers = const <String>{},
    this.savedPosts = const <String>{},
    this.likedPosts = const <String>{},
    this.postLikesCount = const <String, int>{},
    this.postBookmarksCount = const <String, int>{},
    this.postSharesCount = const <String, int>{},
  });

  final Set<String> followingUsers;
  final Set<String> savedPosts;
  final Set<String> likedPosts;
  final Map<String, int> postLikesCount;
  final Map<String, int> postBookmarksCount;
  final Map<String, int> postSharesCount;

  MediaViewerInteractionSnapshot copyWith({
    Set<String>? followingUsers,
    Set<String>? savedPosts,
    Set<String>? likedPosts,
    Map<String, int>? postLikesCount,
    Map<String, int>? postBookmarksCount,
    Map<String, int>? postSharesCount,
  }) {
    return MediaViewerInteractionSnapshot(
      followingUsers: followingUsers ?? this.followingUsers,
      savedPosts: savedPosts ?? this.savedPosts,
      likedPosts: likedPosts ?? this.likedPosts,
      postLikesCount: postLikesCount ?? this.postLikesCount,
      postBookmarksCount: postBookmarksCount ?? this.postBookmarksCount,
      postSharesCount: postSharesCount ?? this.postSharesCount,
    );
  }
}

class MediaViewerResult extends MediaViewerInteractionSnapshot {
  const MediaViewerResult({
    super.followingUsers = const <String>{},
    super.savedPosts = const <String>{},
    super.likedPosts = const <String>{},
    super.postLikesCount = const <String, int>{},
    super.postBookmarksCount = const <String, int>{},
    super.postSharesCount = const <String, int>{},
  });
}

/// 媒体查看器路由传参：列表、浏览器、作者详情共享同一 feed
class MediaViewerExtra {
  const MediaViewerExtra({
    required this.posts,
    this.dtoPosts = const <PostBaseDto>[],
    required this.initialIndex,
    required this.category,
    this.initialImageIndex = 0,
    this.source = 'default',
    this.circleId,
    this.showWorksNavigation = false,
    this.rawPostsById = const <String, Map<String, dynamic>>{},
    this.interactionSnapshot = const MediaViewerInteractionSnapshot(),
  });

  final List<PostSummaryView> posts;
  final List<PostBaseDto> dtoPosts;
  final int initialIndex; // post index for moment, image index for photo
  final String category; // 'photo' | 'video' | 'moment'
  /// 同微趣内图片索引（nested 模式使用，默认为 0）
  final int initialImageIndex;
  final String source;
  final String? circleId;
  final bool showWorksNavigation;
  final Map<String, Map<String, dynamic>> rawPostsById;
  final MediaViewerInteractionSnapshot interactionSnapshot;
}
