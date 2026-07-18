import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/ui/content/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/services/create_page_remote_helpers.dart';
import 'package:quwoquan_app/ui/content/models/post_read_ui_bundle.dart';

/// 创作草稿 → 与 [projectArticleDetailView] 兼容的 wire Map（预览 / ReadPresentation 管道入口）。
///
/// SubmitPostPublication 可写字段以 `contracts/metadata/content/post/service.yaml` 为 SSOT；
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
    'contentIdentity': 'work',
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
        buildArticleAssetManifestForPayload(state),
    ArticleDetailWireKeys.articleRenderProfile:
        buildArticleRenderProfileForPayload(state),
    ArticleDetailWireKeys.articleTemplate: state.articleTemplate.name,
    ArticleDetailWireKeys.articleFontPreset: state.articleFontPreset.name,
  };
}

/// 长文草稿 → [PostReadUiBundle]（[PostReadSurfaceId.draftPreview]），与 [createEditorStateToArticlePreviewWire] 同源 wire。
PostReadUiBundle postReadPreviewBundleFromCreateEditorState(
  CreateEditorState state, {
  String previewPostId = 'draft_preview',
}) {
  final raw = createEditorStateToArticlePreviewWire(
    state,
    previewPostId: previewPostId,
  );
  return PostReadUiBundle.fromPost(
    postBaseDtoFromMap(raw),
    PostReadSurfaceId.draftPreview,
    wire: raw,
  );
}

/// 发布确认页摘要 → 与 SubmitPostPublication 可写字段形状对齐的预览 wire（无真实媒体 URL）。
Map<String, dynamic> createPublishConfirmPreviewWire({
  required CreateContentIdentity contentIdentity,
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
  final isMoment = contentIdentity == CreateContentIdentity.moment;
  final identityStr = isMoment ? 'moment' : 'work';
  final caption = body.trim().isNotEmpty ? body.trim() : title.trim();

  if (hasVideo) {
    final thumbnailUrl = videoThumbnailUrl.trim();
    return <String, dynamic>{
      ...base,
      'contentType': 'video',
      'type': 'video',
      'contentIdentity': identityStr,
      'identity': identityStr,
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
      'contentIdentity': identityStr,
      'identity': identityStr,
      if (caption.isNotEmpty) 'body': caption,
      'imageUrls': urls,
      'mediaUrls': urls,
      'coverUrl': urls.first,
    };
  }
  if (isMoment) {
    return <String, dynamic>{
      ...base,
      'contentType': 'micro',
      'type': 'micro',
      'contentIdentity': 'moment',
      'identity': 'moment',
      'body': caption,
      'mediaUrls': const <String>[],
    };
  }
  return <String, dynamic>{
    ...base,
    'contentType': 'article',
    'type': 'article',
    'contentIdentity': 'work',
    'identity': 'work',
    'title': title.trim(),
    'body': body.trim(),
    'coverUrl': '',
    ArticleDetailWireKeys.articleTemplate: 'gentle',
    ArticleDetailWireKeys.articleFontPreset: 'clean',
  };
}

/// 发布确认页 → [PostReadUiBundle.draftPreview]，供预览文案与 [PostReadPresentation] 单一路径。
PostReadUiBundle postReadPreviewBundleFromPublishConfirmSummary({
  required CreateContentIdentity contentIdentity,
  required String title,
  required String body,
  required bool hasVideo,
  required int imageCount,
  String videoThumbnailUrl = '',
  String previewPostId = 'draft_preview',
}) {
  final wire = createPublishConfirmPreviewWire(
    contentIdentity: contentIdentity,
    title: title,
    body: body,
    hasVideo: hasVideo,
    imageCount: imageCount,
    videoThumbnailUrl: videoThumbnailUrl,
    previewPostId: previewPostId,
  );
  return PostReadUiBundle.fromPost(
    postBaseDtoFromMap(wire),
    PostReadSurfaceId.draftPreview,
    wire: wire,
  );
}
