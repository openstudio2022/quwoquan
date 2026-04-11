// GENERATED FILE — DO NOT EDIT BY HAND.
// Source: contracts/metadata/content/post/projections/post_read_presentation.yaml
// Regenerate: make codegen-app

import 'package:quwoquan_app/cloud/runtime/generated/content/article_detail_wire_keys.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/post_base_dto.dart';

/// 帖子只读投影（字段来自 metadata + PostBaseDto；扩展项可走 wire）。
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
  final String articleTemplate;
  final String articleFontPreset;

  factory PostReadPresentation.fromPostBase(
    PostBaseDto post, {
    Map<String, dynamic>? wire,
  }) {
    return PostReadPresentation(
      postId: post.id,
      contentType: post.type,
      contentIdentity: post.identity,
      displayName: post.displayName,
      avatarUrl: post.avatarUrl,
      title: post.normalizedTitle,
      body: post.normalizedBody,
      coverUrl: post.mediaCoverUrl,
      likeCount: post.likeCount,
      commentCount: post.commentCount,
      shareCount: post.shareCount,
      createdAt: post.createdAt,
      articleTemplate: (wire?[ArticleDetailWireKeys.articleTemplate] ?? '').toString(),
      articleFontPreset: (wire?[ArticleDetailWireKeys.articleFontPreset] ?? '').toString(),
    );
  }
}
