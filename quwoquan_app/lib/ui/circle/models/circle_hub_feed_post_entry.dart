import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 圈子 Hub 帖子的强类型页面模型。
///
/// 云侧公开内容事实由 [CircleFeedPostProjection] 提供；本类型只维护沉浸查看器
/// 返回的会话内互动快照，不保存或向 UI 暴露动态 wire map。
final class CircleHubFeedPostEntry {
  CircleHubFeedPostEntry._({
    required this.circleId,
    required this.placementId,
    required this.post,
    required this.presentation,
    this.pinned = false,
    this.featured = false,
    this.pinnedAt,
    this.featuredAt,
  }) : _likeCount = post.likeCount,
       _commentCount = post.commentCount,
       _shareCount = post.shareCount;

  /// 已取得 App DTO 的圈内帖子入口。
  ///
  /// [PostReadPresentation] 是 metadata 生成的只读展示契约；DTO 的动态序列化结果只在
  /// 该生成工厂的适配边界内使用，不向页面消费者暴露。
  factory CircleHubFeedPostEntry.fromPost({
    required String circleId,
    String placementId = '',
    required PostBaseDto post,
    bool pinned = false,
    bool featured = false,
    DateTime? pinnedAt,
    DateTime? featuredAt,
  }) {
    return CircleHubFeedPostEntry._(
      circleId: circleId,
      placementId: placementId,
      post: post,
      presentation: PostReadPresentation.fromPostBase(post, wire: post.toMap()),
      pinned: pinned,
      featured: featured,
      pinnedAt: pinnedAt,
      featuredAt: featuredAt,
    );
  }

  factory CircleHubFeedPostEntry.fromProjection({
    required CircleFeedPostProjection projection,
    required PostBaseDto post,
  }) {
    return CircleHubFeedPostEntry.fromPost(
      circleId: projection.circleId,
      placementId: projection.placementId,
      post: post,
      pinned: projection.pinned,
      featured: projection.featured,
      pinnedAt: projection.pinnedAt,
      featuredAt: projection.featuredAt,
    );
  }

  final String circleId;
  final String placementId;
  final PostBaseDto post;
  final PostReadPresentation presentation;
  final bool pinned;
  final bool featured;
  final DateTime? pinnedAt;
  final DateTime? featuredAt;

  int _likeCount;
  int _commentCount;
  int _shareCount;
  bool _isLiked = false;
  bool _isFollowingAuthor = false;

  String get postId => post.id;
  String get title => presentation.title.trim();
  String get bodyText => presentation.body.trim();
  String get contentIdentity => presentation.contentIdentity;
  String get displayFormat => post.displayFormat;
  String get articleTemplate => presentation.articleTemplate;
  String get authorRelationshipId => post.authorId;
  String get authorDisplayName => presentation.displayName.trim();
  String get authorAvatarUrl => presentation.avatarUrl.trim();
  int get likeCount => _likeCount;
  int get commentCount => _commentCount;
  int get shareCount => _shareCount;
  bool get isLiked => _isLiked;
  bool get isFollowingAuthor => _isFollowingAuthor;
  bool get isArticle => post.isArticleLike;
  bool get isVideo => post.isVideoLike;
  bool get showsVideoBadge => post.hasVideo;

  String get coverUrl {
    if (presentation.coverUrl.isNotEmpty) {
      return presentation.coverUrl;
    }
    return post.primaryVisualUrl.trim();
  }

  List<String> get imageUrls {
    final images = post.mediaImageUrls;
    if (images.isNotEmpty) {
      return images;
    }
    final cover = coverUrl;
    return cover.isEmpty ? const <String>[] : <String>[cover];
  }

  double get coverAspectRatio {
    final aspect = post.aspectRatio;
    if (aspect != null && aspect > 0) {
      return aspect;
    }
    if (post.hasVideo) {
      return 9 / 16;
    }
    if (imageUrls.isNotEmpty) {
      return 3 / 4;
    }
    return 1;
  }

  MediaViewerPostWireRow toMediaViewerWireRow() {
    return MediaViewerPostWireRow.fromPostBase(
      post,
      circleId: circleId,
      likeCount: likeCount,
      commentCount: commentCount,
      shareCount: shareCount,
      isLiked: isLiked,
      isFollowingAuthor: isFollowingAuthor,
    );
  }

  void applyMediaViewerResult(MediaViewerResult result) {
    if (result.effectiveScopePostIds.isNotEmpty &&
        !result.effectiveScopePostIds.contains(postId)) {
      return;
    }

    _likeCount = result.postLikesCount[postId] ?? _likeCount;
    _commentCount = result.postCommentCount[postId] ?? _commentCount;
    _shareCount = result.postSharesCount[postId] ?? _shareCount;
    _isLiked = result.likedPosts.contains(postId);

    final authorId = authorRelationshipId.trim();
    if (authorId.isNotEmpty &&
        (result.effectiveScopeProfileIds.isEmpty ||
            result.effectiveScopeProfileIds.contains(authorId))) {
      _isFollowingAuthor = result.followingUsers.contains(authorId);
    }
  }

  static void applyResultToList(
    List<CircleHubFeedPostEntry> items,
    MediaViewerResult result,
  ) {
    for (final item in items) {
      item.applyMediaViewerResult(result);
    }
  }
}
