import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 评论页面的本地展示状态。
///
/// 云侧 [CommentListItem] 只负责 canonical wire；折叠、乐观反应和回复分页等
/// 可变展示状态在此模型中维护，避免为生成契约增加第二 decoder 或兼容 API。
final class CommentViewData {
  const CommentViewData({
    required this.id,
    required this.version,
    required this.postId,
    required this.authorId,
    this.authorDisplayNameSnapshot,
    this.authorAvatarUrlSnapshot,
    required this.content,
    this.parentCommentId,
    required this.attachments,
    required this.authorIpLocation,
    required this.status,
    required this.isPinned,
    this.pinnedAt,
    required this.createdAt,
    required this.replyCount,
    required this.replyPreview,
    this.replyNextCursor,
    required this.likeCount,
    required this.dislikeCount,
    required this.viewerReaction,
    required this.authorLiked,
    required this.viewerRelation,
    required this.isAuthor,
    required this.canDelete,
    required this.canReply,
    required this.canReport,
    required this.canPin,
  });

  factory CommentViewData.fromWire(CommentListItem wire) => CommentViewData(
    id: wire.id,
    version: wire.version,
    postId: wire.postId,
    authorId: wire.authorId,
    authorDisplayNameSnapshot: wire.authorDisplayNameSnapshot,
    authorAvatarUrlSnapshot: wire.authorAvatarUrlSnapshot?.toString(),
    content: wire.content,
    parentCommentId: wire.parentCommentId,
    attachments: wire.attachments
        .map(CommentAttachmentViewData.fromWire)
        .toList(growable: false),
    authorIpLocation: wire.authorIpLocation,
    status: wire.status,
    isPinned: wire.isPinned,
    pinnedAt: wire.pinnedAt,
    createdAt: wire.createdAt,
    replyCount: wire.replyCount,
    replyPreview: wire.replyPreview
        .map(CommentViewData.fromWire)
        .toList(growable: false),
    replyNextCursor: wire.replyNextCursor,
    likeCount: wire.likeCount,
    dislikeCount: wire.dislikeCount,
    viewerReaction: wire.viewerReaction,
    authorLiked: wire.authorLiked,
    viewerRelation: wire.viewerRelation,
    isAuthor: wire.isAuthor,
    canDelete: wire.canDelete,
    canReply: wire.canReply,
    canReport: wire.canReport,
    canPin: wire.canPin,
  );

  final String id;
  final int version;
  final String postId;
  final String authorId;
  final String? authorDisplayNameSnapshot;
  final String? authorAvatarUrlSnapshot;
  final String content;
  final String? parentCommentId;
  final List<CommentAttachmentViewData> attachments;
  final String? authorIpLocation;
  final CommentStatus status;
  final bool isPinned;
  final DateTime? pinnedAt;
  final DateTime createdAt;
  final int replyCount;
  final List<CommentViewData> replyPreview;
  final String? replyNextCursor;
  final int likeCount;
  final int dislikeCount;
  final CommentReactionType viewerReaction;
  final bool authorLiked;
  final CommentViewerRelation viewerRelation;
  final bool isAuthor;
  final bool canDelete;
  final bool canReply;
  final bool canReport;
  final bool canPin;

  CommentViewData copyWith({
    int? version,
    CommentStatus? status,
    bool? isPinned,
    DateTime? Function()? pinnedAt,
    int? replyCount,
    List<CommentViewData>? replyPreview,
    String? Function()? replyNextCursor,
    int? likeCount,
    int? dislikeCount,
    CommentReactionType? viewerReaction,
  }) => CommentViewData(
    id: id,
    version: version ?? this.version,
    postId: postId,
    authorId: authorId,
    authorDisplayNameSnapshot: authorDisplayNameSnapshot,
    authorAvatarUrlSnapshot: authorAvatarUrlSnapshot,
    content: content,
    parentCommentId: parentCommentId,
    attachments: attachments,
    authorIpLocation: authorIpLocation,
    status: status ?? this.status,
    isPinned: isPinned ?? this.isPinned,
    pinnedAt: pinnedAt == null ? this.pinnedAt : pinnedAt(),
    createdAt: createdAt,
    replyCount: replyCount ?? this.replyCount,
    replyPreview: replyPreview ?? this.replyPreview,
    replyNextCursor: replyNextCursor == null
        ? this.replyNextCursor
        : replyNextCursor(),
    likeCount: likeCount ?? this.likeCount,
    dislikeCount: dislikeCount ?? this.dislikeCount,
    viewerReaction: viewerReaction ?? this.viewerReaction,
    authorLiked: authorLiked,
    viewerRelation: viewerRelation,
    isAuthor: isAuthor,
    canDelete: canDelete,
    canReply: canReply,
    canReport: canReport,
    canPin: canPin,
  );
}

final class CommentAttachmentViewData {
  const CommentAttachmentViewData({
    required this.mediaId,
    this.displayUrl,
    required this.aspectRatio,
    required this.available,
  });

  factory CommentAttachmentViewData.fromWire(CommentAttachmentSlice wire) {
    final width = wire.width;
    final height = wire.height;
    return CommentAttachmentViewData(
      mediaId: wire.mediaId,
      displayUrl: wire.url?.toString(),
      aspectRatio: width != null && height != null && height > 0
          ? width / height
          : 1,
      available: wire.available,
    );
  }

  final String mediaId;
  final String? displayUrl;
  final double aspectRatio;
  final bool available;
}
