import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/models/post_read_presentation_mapper.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Typed App projection of the canonical `GetPost` response.
final class ContentPostDetailPayload {
  ContentPostDetailPayload._(this.post, this.detailWire);

  factory ContentPostDetailPayload.fromWire(ContentPostDetailSlice wire) {
    return ContentPostDetailPayload._(
      ContentPostViewData.fromWire(
        ContentPostProjection(
          postId: wire.postId,
          contentType: wire.contentType,
          contentIdentity: wire.contentIdentity,
          assistantUsePolicy: wire.assistantUsePolicy,
          authorId: wire.authorId,
          authorDisplayName: wire.authorDisplayName,
          authorAvatarUrl: wire.authorAvatarUrl,
          title: wire.title,
          body: wire.body,
          summary: wire.summary,
          coverUrl: wire.coverUrl,
          articleTemplate: wire.articleTemplate,
          articleFontPreset: wire.articleFontPreset,
          mediaUrls: wire.mediaUrls,
          videoUrl: wire.videoUrl,
          thumbnailUrl: wire.thumbnailUrl,
          width: wire.width,
          height: wire.height,
          durationMs: wire.durationMs,
          likeCount: wire.likeCount,
          commentCount: wire.commentCount,
          shareCount: wire.shareCount,
          createdAt: wire.createdAt,
          updatedAt: wire.updatedAt,
          publishedAt: wire.publishedAt,
          contentVertical: wire.contentVertical,
        ),
        sourceAttribution: wire.sourceAttribution,
      ),
      wire,
    );
  }

  final ContentPostViewData post;
  final ContentPostDetailSlice detailWire;

  /// App presentation data derived from the already-decoded canonical wire.
  Map<String, dynamic> get mergedArticleWireMap => <String, dynamic>{
    ...post.toPresentationMap(),
    if (detailWire.articleMarkdown != null)
      ArticleDetailWireKeys.articleMarkdown: detailWire.articleMarkdown,
    if (detailWire.markdownDialect != null)
      ArticleDetailWireKeys.markdownDialect: detailWire.markdownDialect,
    if (detailWire.articleAssetManifest != null)
      ArticleDetailWireKeys.articleAssetManifest: detailWire
          .articleAssetManifest!
          .toWire(),
    if (detailWire.articleRenderProfile != null)
      ArticleDetailWireKeys.articleRenderProfile: detailWire
          .articleRenderProfile!
          .toWire(),
    if (detailWire.articleTemplate != null)
      ArticleDetailWireKeys.articleTemplate: detailWire.articleTemplate,
    if (detailWire.articleFontPreset != null)
      ArticleDetailWireKeys.articleFontPreset: detailWire.articleFontPreset,
  };

  PostReadPresentation get readPresentation =>
      PostReadPresentationMapper.fromViewData(post, wire: mergedArticleWireMap);
}
