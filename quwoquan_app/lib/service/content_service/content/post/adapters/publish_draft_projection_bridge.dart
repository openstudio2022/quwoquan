import 'package:quwoquan_app/service/content_service/content/post/adapters/generated/article_detail_wire_keys.g.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/content_read_model_projection.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/create_editor_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/create_page_remote_helpers.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';

/// 创作草稿 → 与 [projectArticleDetailView] 兼容的 wire Map（预览 / ReadPresentation 管道入口）。
///
/// SubmitPostPublication 可写字段以 `quwoquan_service/services/content-service/contracts/content/post/operations.yaml` 为 SSOT；
/// 实际上传仍走 [buildPostPublicationPayloadMap] + [attachActivePersonaToCreatePayload]。
Map<String, dynamic> createEditorStateToArticlePreviewWire(
  CreateEditorState state, {
  String previewPostId = 'draft_preview',
}) {
  final cover = coverAssetPathForPayload(state);
  final markdown = buildArticleMarkdownForPayload(state);
  return <String, dynamic>{
    'postId': previewPostId,
    'id': previewPostId,
    'contentType': 'article',
    'type': 'article',
    'title': state.title.trim(),
    'body': state.body.trim(),
    'displayName': '',
    'authorId': 'preview',
    'authorAvatarUrl': '',
    'avatarUrl': '',
    'createdAt': DateTime.now().toUtc().toIso8601String(),
    'likeCount': 0,
    'commentCount': 0,
    'shareCount': 0,
    'coverUrl': cover,
    ArticleDetailWireKeys.articleMarkdown: markdown,
    ArticleDetailWireKeys.markdownDialect: 'qwq-rich-md',
    ArticleDetailWireKeys.articleAssetManifest:
        buildArticleAssetManifestForPayload(state).toWire(),
    ArticleDetailWireKeys.articleRenderProfile:
        buildArticleRenderProfileForPayload(state).toWire(),
    ArticleDetailWireKeys.articleTemplate: state.articleTemplate.name,
    ArticleDetailWireKeys.articleFontPreset: state.articleFontPreset.name,
  };
}

/// 长文草稿 → canonical App read view，与 [createEditorStateToArticlePreviewWire]
/// 同源 wire，不再复制第二套 presentation DTO。
ContentPostViewData postReadPreviewFromCreateEditorState(
  CreateEditorState state, {
  String previewPostId = 'draft_preview',
}) {
  final raw = createEditorStateToArticlePreviewWire(
    state,
    previewPostId: previewPostId,
  );
  return contentPostViewDataFromReadModelMap(raw);
}

/// 发布确认页摘要 → 与 SubmitPostPublication 可写字段形状对齐的预览 wire（无真实媒体 URL）。
Map<String, dynamic> createPublishConfirmPreviewWire({
  required String title,
  required String body,
  required bool hasVideo,
  required int imageCount,
  String videoThumbnailUrl = '',
  String previewPostId = 'draft_preview',
}) {
  final base = <String, dynamic>{
    'postId': previewPostId,
    'id': previewPostId,
    'authorId': 'preview',
    'displayName': '',
    'avatarUrl': '',
    'createdAt': DateTime.now().toUtc().toIso8601String(),
    'likeCount': 0,
    'commentCount': 0,
    'shareCount': 0,
  };
  final caption = body.trim().isNotEmpty ? body.trim() : title.trim();

  if (hasVideo) {
    final thumbnailUrl = videoThumbnailUrl.trim();
    return <String, dynamic>{
      ...base,
      'contentType': 'video',
      'type': 'video',
      'body': caption,
      'videoUrl': 'draft-preview://local',
      'thumbnailUrl': thumbnailUrl,
      if (thumbnailUrl.isNotEmpty) 'coverUrl': thumbnailUrl,
    };
  }
  if (imageCount > 0) {
    final urls = List<String>.generate(
      imageCount,
      (i) => 'draft-preview-image-$i',
      growable: false,
    );
    return <String, dynamic>{
      ...base,
      'contentType': 'image',
      'type': 'image',
      if (caption.isNotEmpty) 'body': caption,
      'imageUrls': urls,
      'mediaUrls': urls,
      'coverUrl': urls.first,
    };
  }
  return <String, dynamic>{
    ...base,
    'contentType': 'article',
    'type': 'article',
    'title': title.trim(),
    'body': body.trim(),
    'coverUrl': '',
    ArticleDetailWireKeys.articleTemplate: 'gentle',
    ArticleDetailWireKeys.articleFontPreset: 'clean',
  };
}

/// 发布确认页 → canonical App read view，供预览文案单轨消费。
ContentPostViewData postReadPreviewFromPublishConfirmSummary({
  required String title,
  required String body,
  required bool hasVideo,
  required int imageCount,
  String videoThumbnailUrl = '',
  String previewPostId = 'draft_preview',
}) {
  final wire = createPublishConfirmPreviewWire(
    title: title,
    body: body,
    hasVideo: hasVideo,
    imageCount: imageCount,
    videoThumbnailUrl: videoThumbnailUrl,
    previewPostId: previewPostId,
  );
  return contentPostViewDataFromReadModelMap(wire);
}
