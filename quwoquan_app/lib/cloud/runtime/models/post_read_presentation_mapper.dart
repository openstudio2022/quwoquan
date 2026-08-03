import 'package:quwoquan_app/cloud/runtime/generated/content/article_detail_wire_keys.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/post_read_presentation.g.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_view_data.dart';

/// App-owned mapping from the decoded Post view to its canonical read
/// presentation. Generated artifacts stay independent from App-owned models.
abstract final class PostReadPresentationMapper {
  static PostReadPresentation fromViewData(
    ContentPostViewData post, {
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
      updatedAt: post.updatedAt,
      publishedAt: post.publishedAt,
      articleTemplate:
          (wire?[ArticleDetailWireKeys.articleTemplate] ?? '').toString(),
      articleFontPreset:
          (wire?[ArticleDetailWireKeys.articleFontPreset] ?? '').toString(),
    );
  }
}
