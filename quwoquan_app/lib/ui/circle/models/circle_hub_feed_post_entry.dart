import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';

/// 首页圈子流中单条帖子：保留 wire map 供 MediaViewer 写回，同时缓存解析后的 [PostBaseDto]。
class CircleHubFeedPostEntry {
  CircleHubFeedPostEntry._(this.raw, this.dto);

  /// 圈子流 wire 行（含扩展键）；与 [dto] 同步更新，供 [applyMediaViewerResult] 写回。
  /// 展示逻辑优先 [dto] / [tryReadPresentation]；长期可评估缩为写回所需窄键或二次 [ContentRepository.getPost]。
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

  /// 由 [PostBaseDto] 构建；补齐圈子创作区常用的 wire 键（contentType / postId 等）。
  factory CircleHubFeedPostEntry.fromPostDto(PostBaseDto p) {
    final raw = Map<String, dynamic>.from(p.toMap());
    raw['postId'] = raw['postId'] ?? p.id;
    raw['contentType'] = raw['contentType'] ?? raw['type'] ?? p.type;
    raw['contentIdentity'] =
        raw['contentIdentity'] ?? raw['identity'] ?? p.identity;
    raw['authorNickname'] =
        raw['authorNickname'] ?? raw['displayName'] ?? p.displayName;
    raw['authorAvatarUrl'] =
        raw['authorAvatarUrl'] ?? raw['avatarUrl'] ?? p.avatarUrl;
    return CircleHubFeedPostEntry._(raw, p);
  }

  String get postIdForKey => (raw['postId'] ?? raw['id'] ?? '').toString();

  /// 圈子故事卡片 / 筛选用；避免在 UI 上散写 `raw['circleId']`。
  String get wireCircleId => (raw['circleId'] ?? '').toString();

  /// MediaViewer 回写关注态、互动快照 fallback 等用同一作者主键解析顺序。
  String get wireAuthorRelationshipId =>
      (raw['subAccountId'] ?? raw['authorId'] ?? raw['userId'] ?? '')
          .toString();

  /// Wire 计数优先（含用户操作后的回写），其次 [dto]。
  int get wireLikeCount =>
      (raw['likeCount'] as num?)?.toInt() ??
      (raw['likes'] as num?)?.toInt() ??
      dto?.likeCount ??
      0;

  int get wireBookmarkCount =>
      (raw['favoriteCount'] as num?)?.toInt() ??
      (raw['bookmarkCount'] as num?)?.toInt() ??
      dto?.favoriteCount ??
      0;

  int get wireShareCount =>
      (raw['shareCount'] as num?)?.toInt() ?? dto?.shareCount ?? 0;

  /// [dto] 已解析则直接返回，否则尝试 [postBaseDtoFromMap]（失败返回 null）。
  PostBaseDto? tryResolveDto() {
    if (dto != null) return dto;
    try {
      return postBaseDtoFromMap(raw);
    } catch (_) {
      return null;
    }
  }

  /// 封面 / 缩略：与圈子 hub 卡片一致（先 presentation / DTO 视觉主 URL，再 wire）。
  String get wireCoverUrl {
    final rp = tryReadPresentation();
    if (rp != null && rp.coverUrl.isNotEmpty) return rp.coverUrl;
    final d = dto;
    if (d != null) {
      final u = d.primaryVisualUrl.trim();
      if (u.isNotEmpty) return u;
    }
    final cover = (raw['coverUrl'] ?? raw['thumbnailUrl'] ?? '').toString();
    if (cover.isNotEmpty) return cover;
    final imageUrls = raw['imageUrls'];
    if (imageUrls is List && imageUrls.isNotEmpty) {
      return imageUrls.first.toString();
    }
    return '';
  }

  String get wireTitle {
    final d = dto;
    if (d != null && d.normalizedTitle.isNotEmpty) return d.normalizedTitle;
    final rp = tryReadPresentation();
    if (rp != null && rp.title.isNotEmpty) return rp.title;
    return (raw['title'] ?? '').toString();
  }

  String get wireBodyText {
    final d = dto;
    if (d != null && d.normalizedBody.isNotEmpty) return d.normalizedBody;
    final rp = tryReadPresentation();
    if (rp != null && rp.body.isNotEmpty) return rp.body;
    return (raw['body'] ?? raw['description'] ?? raw['content'] ?? '')
        .toString();
  }

  /// 含 `username` / `authorId` 等 wire 别名，供 hub 信息流卡片使用。
  String get wireAuthorDisplayName {
    final d = dto;
    if (d != null && d.displayName.trim().isNotEmpty) {
      return d.displayName.trim();
    }
    final rp = tryReadPresentation();
    if (rp != null && rp.displayName.trim().isNotEmpty) {
      return rp.displayName.trim();
    }
    return (raw['authorNickname'] ??
            raw['displayName'] ??
            raw['username'] ??
            raw['authorId'] ??
            '')
        .toString();
  }

  String get wireAuthorAvatarUrl {
    final d = dto;
    if (d != null && d.avatarUrl.trim().isNotEmpty) {
      return d.avatarUrl.trim();
    }
    final rp = tryReadPresentation();
    if (rp != null && rp.avatarUrl.trim().isNotEmpty) {
      return rp.avatarUrl.trim();
    }
    return (raw['authorAvatarUrl'] ?? raw['avatarUrl'] ?? '').toString();
  }

  bool get wireIsLiked => raw['isLiked'] as bool? ?? false;

  bool get wireShowsVideoBadge =>
      (raw['videoUrl']?.toString().trim() ?? '').isNotEmpty ||
      (dto?.mediaVideoUrl.isNotEmpty ?? false);

  double wireCoverAspectRatio() {
    final d = dto;
    final aspect = d?.aspectRatio;
    if (aspect != null && aspect > 0) {
      return aspect;
    }
    final width = (raw['width'] as num?)?.toDouble();
    final height = (raw['height'] as num?)?.toDouble();
    if (width != null && height != null && width > 0 && height > 0) {
      return width / height;
    }
    final hasVideo =
        (raw['videoUrl']?.toString().trim() ?? '').isNotEmpty ||
        (d?.mediaVideoUrl.isNotEmpty ?? false);
    if (hasVideo) return 9 / 16;
    final hasImage =
        raw['imageUrls'] is List && (raw['imageUrls'] as List).isNotEmpty;
    if (hasImage) return 3 / 4;
    return 1.0;
  }

  /// Metadata 只读投影；解析失败时返回 null（回退到 [raw] 辅助逻辑）。
  PostReadPresentation? tryReadPresentation() {
    try {
      final base = dto ?? postBaseDtoFromMap(raw);
      return PostReadPresentation.fromPostBase(base, wire: raw);
    } catch (_) {
      return null;
    }
  }

  void applyMediaViewerResult(MediaViewerResult result) {
    final id = postIdForKey;
    if (id.isEmpty) return;
    final scopePostIds = result.effectiveScopePostIds;
    if (scopePostIds.isNotEmpty && !scopePostIds.contains(id)) {
      return;
    }

    final authorId = wireAuthorRelationshipId;

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

    final commentCount = result.postCommentCount[id];
    if (commentCount != null) {
      raw['commentCount'] = commentCount;
      raw['commentsCount'] = commentCount;
    }

    raw['isLiked'] = result.likedPosts.contains(id);
    raw['isSaved'] = result.savedPosts.contains(id);
    if (authorId.isNotEmpty &&
        (result.effectiveScopeProfileIds.isEmpty ||
            result.effectiveScopeProfileIds.contains(authorId))) {
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
