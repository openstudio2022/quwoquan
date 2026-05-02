import 'package:quwoquan_app/cloud/runtime/generated/content/feed_item_dto.g.dart';
import 'package:quwoquan_app/cloud/services/content/feed_item_discovery_wire_map.dart';
import 'package:quwoquan_app/ui/content/post_summary_view.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/post_base_dto.dart';

/// 媒体浏览器按帖子 id 携带的发现区/沉浸扩展数据。
///
/// 强类型主视图为 [feedItem]；全量 wire 见 [toDynamicMap]（存量沉浸路径逐步淘汰）。
class MediaViewerPostWireRow {
  MediaViewerPostWireRow._(this._wire);

  final Map<String, dynamic> _wire;

  late final FeedItemDto feedItem = FeedItemDto.fromMap(_wire);

  factory MediaViewerPostWireRow.fromFeedItem(
    FeedItemDto item, {
    Map<String, dynamic>? extra,
  }) {
    final merged = <String, dynamic>{
      ...item.toDiscoveryWireMap(),
      if (extra != null) ...extra,
    };
    return MediaViewerPostWireRow._(merged);
  }

  factory MediaViewerPostWireRow.fromDynamicMap(Map<String, dynamic> map) {
    return MediaViewerPostWireRow._(Map<String, dynamic>.from(map));
  }

  factory MediaViewerPostWireRow.fromObjectEntries(
    Map<String, Object?> entries,
  ) {
    return MediaViewerPostWireRow._(
      entries.map((k, v) => MapEntry(k, v as dynamic)),
    );
  }

  Map<String, dynamic> toDynamicMap() => Map<String, dynamic>.from(_wire);

  /// 沉浸器等仍消费 `Map<String, Object?>` 时的兼容视图。
  Map<String, Object?> toObjectMap() =>
      _wire.map((k, v) => MapEntry(k, v as Object?));
}

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
    this.rawPostsById = const <String, MediaViewerPostWireRow>{},
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
  final Map<String, MediaViewerPostWireRow> rawPostsById;
  final MediaViewerInteractionSnapshot interactionSnapshot;
}
