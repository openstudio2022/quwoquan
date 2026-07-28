import 'package:quwoquan_app/cloud/runtime/generated/content/feed_item_dto.g.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/cloud/services/content/feed_item_discovery_wire_map.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view.dart';
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
    final merged = <String, dynamic>{...item.toDiscoveryWireMap(), ...?extra};
    return MediaViewerPostWireRow._(merged);
  }

  factory MediaViewerPostWireRow.fromDynamicMap(Map<String, dynamic> map) {
    return MediaViewerPostWireRow._(Map<String, dynamic>.from(map));
  }

  factory MediaViewerPostWireRow.fromPostBase(
    PostBaseDto post, {
    String? circleId,
    int? likeCount,
    int? commentCount,
    int? shareCount,
    bool isLiked = false,
    bool isFollowingAuthor = false,
  }) {
    final wire = Map<String, dynamic>.from(post.toMap())
      ..['postId'] = post.id
      ..['contentType'] = post.type
      ..['likeCount'] = likeCount ?? post.likeCount
      ..['commentCount'] = commentCount ?? post.commentCount
      ..['shareCount'] = shareCount ?? post.shareCount
      ..['isLiked'] = isLiked
      ..['isFollowingAuthor'] = isFollowingAuthor;
    final normalizedCircleId = circleId?.trim() ?? '';
    if (normalizedCircleId.isNotEmpty) {
      wire['circleId'] = normalizedCircleId;
    }
    return MediaViewerPostWireRow._(wire);
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
    this.scopePostIds = const <String>{},
    this.scopeProfileIds = const <String>{},
    this.followingUsers = const <String>{},
    this.likedPosts = const <String>{},
    this.postLikesCount = const <String, int>{},
    this.postSharesCount = const <String, int>{},
    this.postCommentCount = const <String, int>{},
  });

  final Set<String> scopePostIds;
  final Set<String> scopeProfileIds;
  final Set<String> followingUsers;
  final Set<String> likedPosts;
  final Map<String, int> postLikesCount;
  final Map<String, int> postSharesCount;
  final Map<String, int> postCommentCount;

  Set<String> get effectiveScopePostIds {
    if (scopePostIds.isNotEmpty) {
      return scopePostIds;
    }
    return <String>{
      ...likedPosts,
      ...postLikesCount.keys,
      ...postSharesCount.keys,
      ...postCommentCount.keys,
    };
  }

  Set<String> get effectiveScopeProfileIds {
    if (scopeProfileIds.isNotEmpty) {
      return scopeProfileIds;
    }
    return followingUsers;
  }

  MediaViewerInteractionSnapshot copyWith({
    Set<String>? scopePostIds,
    Set<String>? scopeProfileIds,
    Set<String>? followingUsers,
    Set<String>? likedPosts,
    Map<String, int>? postLikesCount,
    Map<String, int>? postSharesCount,
    Map<String, int>? postCommentCount,
  }) {
    return MediaViewerInteractionSnapshot(
      scopePostIds: scopePostIds ?? this.scopePostIds,
      scopeProfileIds: scopeProfileIds ?? this.scopeProfileIds,
      followingUsers: followingUsers ?? this.followingUsers,
      likedPosts: likedPosts ?? this.likedPosts,
      postLikesCount: postLikesCount ?? this.postLikesCount,
      postSharesCount: postSharesCount ?? this.postSharesCount,
      postCommentCount: postCommentCount ?? this.postCommentCount,
    );
  }
}

class MediaViewerResult extends MediaViewerInteractionSnapshot {
  const MediaViewerResult({
    super.scopePostIds = const <String>{},
    super.scopeProfileIds = const <String>{},
    super.followingUsers = const <String>{},
    super.likedPosts = const <String>{},
    super.postLikesCount = const <String, int>{},
    super.postSharesCount = const <String, int>{},
    super.postCommentCount = const <String, int>{},
  });

  factory MediaViewerResult.fromSnapshot(
    MediaViewerInteractionSnapshot snapshot,
  ) {
    return MediaViewerResult(
      scopePostIds: Set<String>.from(snapshot.effectiveScopePostIds),
      scopeProfileIds: Set<String>.from(snapshot.effectiveScopeProfileIds),
      followingUsers: Set<String>.from(snapshot.followingUsers),
      likedPosts: Set<String>.from(snapshot.likedPosts),
      postLikesCount: Map<String, int>.from(snapshot.postLikesCount),
      postSharesCount: Map<String, int>.from(snapshot.postSharesCount),
      postCommentCount: Map<String, int>.from(snapshot.postCommentCount),
    );
  }
}

/// work browser / 沉浸式评论直达上下文。
///
/// `openComments=true` 表示进入帖子后直接展开评论分屏；`target*` 用于恢复
/// “查看原评论 / 在上下文中定位”的目标语义，`replyToCommentId` 用于落地后
/// 直接进入回复输入态。
///
/// 评论深链 query 参数由 `app_routes.yaml#workBrowser` 声明；本类只负责将
/// Router 已解析的 query 映射为 typed context。所有入口必须使用
/// `AppRoutePaths.workBrowser(...)`，禁止手工 URI 拼接或维护第二套方言。
class MediaViewerCommentContext {
  const MediaViewerCommentContext({
    this.openComments = false,
    this.replyToCommentId,
    this.targetCommentId,
    this.targetParentCommentId,
    this.targetReplyId,
    this.entrySource,
  });

  /// 评论深链 query 参数键（单一方言唯一真相源）。
  static const String queryOpenComments = 'openComments';
  static const String queryEntrySource = 'commentEntrySource';
  static const String queryTargetCommentId = 'targetCommentId';
  static const String queryTargetParentCommentId = 'targetParentCommentId';
  static const String queryTargetReplyId = 'targetReplyId';
  static const String queryReplyToCommentId = 'replyToCommentId';

  /// 评论深链入口来源（用于分析口径与落地 mode 判定）。
  static const String entrySourceProfileInteraction = 'profile-interaction';
  static const String entrySourceProfileComments = 'profile-comments';
  static const String entrySourceNotification = 'notification';

  final bool openComments;

  /// 打开评论区后直接进入回复态的目标 id。
  final String? replyToCommentId;

  /// 一级评论定位目标。
  final String? targetCommentId;

  /// 二级回复所属一级评论 id。
  final String? targetParentCommentId;

  /// 二级回复定位目标。
  final String? targetReplyId;

  /// 深链入口来源（见 entrySource* 常量）。
  final String? entrySource;

  /// 来自「我的互动 / 我的评论」等个人页深链，落地统一使用 profileInteraction
  /// mode；entrySource 仍保留具体来源用于分析口径。
  bool get usesProfileInteractionMode =>
      entrySource == entrySourceProfileInteraction ||
      entrySource == entrySourceProfileComments;

  bool get shouldOpen =>
      openComments ||
      (replyToCommentId?.trim().isNotEmpty ?? false) ||
      (targetCommentId?.trim().isNotEmpty ?? false) ||
      (targetParentCommentId?.trim().isNotEmpty ?? false) ||
      (targetReplyId?.trim().isNotEmpty ?? false);

  static MediaViewerCommentContext fromQueryParameters(
    Map<String, String> query,
  ) {
    String? clean(String key) {
      final value = query[key]?.trim();
      return (value == null || value.isEmpty) ? null : value;
    }

    return MediaViewerCommentContext(
      openComments:
          (query[queryOpenComments] ?? '').trim().toLowerCase() == 'true',
      replyToCommentId: clean(queryReplyToCommentId),
      targetCommentId: clean(queryTargetCommentId),
      targetParentCommentId: clean(queryTargetParentCommentId),
      targetReplyId: clean(queryTargetReplyId),
      entrySource: clean(queryEntrySource),
    );
  }
}

/// 媒体查看器路由传参：列表、浏览器、作者详情共享同一 feed
class MediaViewerExtra {
  const MediaViewerExtra({
    required this.posts,
    this.dtoPosts = const <PostBaseDto>[],
    required this.initialIndex,
    this.initialImageIndex = 0,
    this.source = 'default',
    this.circleId,
    this.showWorksNavigation = false,
    this.rawPostsById = const <String, MediaViewerPostWireRow>{},
    this.interactionSnapshot = const MediaViewerInteractionSnapshot(),
    this.referralSource = ReferralSource.organicFeed,
    this.feedRequestId,
    this.position,
    this.commentContext = const MediaViewerCommentContext(),
  });

  final List<ContentSurfaceView> posts;
  final List<PostBaseDto> dtoPosts;

  /// 入口 post 在列表中的序号（沉浸器初始定位用）。
  final int initialIndex;

  /// 单帖内图片索引（nested 模式使用，默认为 0）。
  final int initialImageIndex;
  final String source;
  final String? circleId;
  final bool showWorksNavigation;
  final Map<String, MediaViewerPostWireRow> rawPostsById;
  final MediaViewerInteractionSnapshot interactionSnapshot;
  final ReferralSource referralSource;
  final String? feedRequestId;

  /// 入口 post 在 feed 中的位置（推荐归因用；从 feed 列表序号透传）。
  final int? position;

  final MediaViewerCommentContext commentContext;

  MediaViewerExtra copyWith({MediaViewerCommentContext? commentContext}) {
    return MediaViewerExtra(
      posts: posts,
      dtoPosts: dtoPosts,
      initialIndex: initialIndex,
      initialImageIndex: initialImageIndex,
      source: source,
      circleId: circleId,
      showWorksNavigation: showWorksNavigation,
      rawPostsById: rawPostsById,
      interactionSnapshot: interactionSnapshot,
      referralSource: referralSource,
      feedRequestId: feedRequestId,
      position: position,
      commentContext: commentContext ?? this.commentContext,
    );
  }
}

/// 只有 workId 的直达浏览器仍需保留来源与 feed 归因。
class WorkBrowserEntryRouteExtra {
  const WorkBrowserEntryRouteExtra({
    required this.referralSource,
    this.feedRequestId,
  });

  final ReferralSource referralSource;
  final String? feedRequestId;
}
