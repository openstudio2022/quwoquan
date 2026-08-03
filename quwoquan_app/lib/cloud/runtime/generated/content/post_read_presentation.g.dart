// GENERATED FILE — DO NOT EDIT BY HAND.
// Source: services/content-service/contracts/content/post/projections/post_read_presentation.yaml
// Regenerate: make codegen-app

/// 帖子只读投影；字段与类型只来自 canonical metadata。
class PostReadPresentation {
  const PostReadPresentation({
    required this.postId,
    required this.contentType,
    required this.contentIdentity,
    required this.displayName,
    required this.avatarUrl,
    required this.title,
    required this.body,
    required this.coverUrl,
    required this.likeCount,
    required this.commentCount,
    required this.shareCount,
    required this.createdAt,
    required this.updatedAt,
    required this.publishedAt,
    required this.articleTemplate,
    required this.articleFontPreset,
  });

  final String postId;
  final String contentType;
  final String contentIdentity;
  final String displayName;
  final String avatarUrl;
  final String title;
  final String body;
  final String coverUrl;
  final int likeCount;
  final int commentCount;
  final int shareCount;
  final DateTime createdAt;
  final DateTime? updatedAt;
  final DateTime? publishedAt;
  final String articleTemplate;
  final String articleFontPreset;
}
