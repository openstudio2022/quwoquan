import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/post_publication_continuation_registry.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_document_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_flow_layout_engine.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_pagination_engine.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/article_presentation_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_presentation_values.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/publish_settings_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_markdown_codec.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/qwq_markdown_ast.dart';
part 'create_editor_models_draft.dart';

enum EditorStartAction { gallery, video, write, capture }

enum CreateContentIdentity { moment, work }

extension CreateContentIdentityX on CreateContentIdentity {
  String get value => name;

  String get label => this == CreateContentIdentity.moment ? '点滴' : '作品';
}

@immutable
class IdentitySuggestion {
  const IdentitySuggestion({required this.identity, required this.reason});

  final CreateContentIdentity identity;
  final String reason;
}

enum CreateEditorKind { media, text }

enum CreateMediaKind { none, images, video }

enum CreateDraftFlowKind { article, image, video }

extension CreateDraftFlowKindX on CreateDraftFlowKind {
  EditorStartAction get startAction => switch (this) {
    CreateDraftFlowKind.article => EditorStartAction.write,
    CreateDraftFlowKind.image => EditorStartAction.gallery,
    CreateDraftFlowKind.video => EditorStartAction.video,
  };
}

enum TitlePresentation { collapsed, expanded }

ArticleDocumentData createDefaultArticleDocument() {
  return ArticleDocumentData(
    nodes: const <ArticleDocumentNode>[
      ArticleDocumentNode(
        id: 'paragraph_0',
        type: ArticleDocumentNodeType.paragraph,
      ),
    ],
  );
}

String buildArticlePlainTextFromDocument(ArticleDocumentData document) {
  final lines = <String>[];
  var orderedIndex = 0;
  for (final node in document.nodes) {
    if (node.isDocumentTitle || node.isFigure || !node.hasText) {
      continue;
    }
    final text = node.text.trim();
    final line = switch (node.type) {
      ArticleDocumentNodeType.orderedItem => '${++orderedIndex}. $text',
      ArticleDocumentNodeType.bulletItem => '• $text',
      _ => (() {
        orderedIndex = 0;
        return text;
      })(),
    };
    if (line.isNotEmpty) {
      lines.add(line);
    }
    if (node.type != ArticleDocumentNodeType.orderedItem) {
      orderedIndex = 0;
    }
  }
  return lines.join('\n');
}

List<String> extractArticleImagePathsFromDocument(
  ArticleDocumentData document,
) {
  return document.assets
      .map((asset) {
        final path = asset.imageUrl.trim();
        if (path.isNotEmpty) {
          return path;
        }
        // 创作域 canonical 中间形态：尚未取得交付 URL 的资产以
        // asset://<assetId> 表达引用，由创作媒体投影映射到本地文件。
        final assetId = asset.id.trim();
        return assetId.isEmpty ? '' : 'asset://$assetId';
      })
      .where((path) => path.isNotEmpty)
      .toList(growable: false);
}

List<ArticlePageData> buildArticlePagesSnapshotFromDocument(
  ArticleDocumentData document, {
  ArticleFontPreset fontPreset = ArticleFontPreset.clean,
  double stageWidth = 390,
  double? contentHeightOverride,
  ArticleCanvasMetrics? metrics,
}) {
  final resolvedMetrics = metrics ?? ArticleCanvasMetrics.snapshot();
  final viewportSliceHeight =
      contentHeightOverride ??
      resolvedMetrics.contentSizeForStageWidth(stageWidth).height;
  return ArticleFlowLayoutEngine.buildPageSlicesForViewport(
    document: document,
    metrics: resolvedMetrics,
    stageWidth: stageWidth,
    titleStyle: ArticlePaginationEngine.snapshotTitleStyle(
      fontPreset: fontPreset,
    ),
    bodyStyle: ArticlePaginationEngine.snapshotBodyStyle(
      fontPreset: fontPreset,
    ),
    viewportSliceHeight: viewportSliceHeight,
  );
}

/// 创作发布草稿聚合；契约归属 metadata-driven-client-data-contract Story。
typedef ContentPublishDraftComposite = CreateEditorState;

@immutable
class CreateEditorState {
  const CreateEditorState({
    required this.editorKind,
    required this.draftFlowKind,
    required this.mediaKind,
    required this.imagePaths,
    required this.videoPath,
    required this.originalVideoPath,
    required this.videoThumbnail,
    required this.videoDurationMs,
    required this.videoTrimStartMs,
    required this.videoTrimEndMs,
    required this.videoCoverTimeMs,
    required this.videoCoverStrategy,
    required this.videoWidth,
    required this.videoHeight,
    required this.videoMuted,
    required this.currentMediaIndex,
    required this.title,
    required this.body,
    required this.articleDocument,
    required this.articlePages,
    required this.activeArticlePageId,
    required this.activeArticleBlockId,
    required this.articleTemplate,
    required this.articlePaperTexture,
    required this.articleFontPreset,
    required this.articleCoverImagePath,
    required this.titlePresentation,
    required this.titleHintDismissed,
    required this.settings,
    this.isOneTapMovie = false,
    this.oneTapMoviePath = '',
    this.oneTapMovieEffectId = '',
    this.draftId,
  });

  factory CreateEditorState.initial({
    CreateEditorKind editorKind = CreateEditorKind.text,
    CreateDraftFlowKind draftFlowKind = CreateDraftFlowKind.article,
  }) {
    final initialDocument = createDefaultArticleDocument();
    final initialPages = buildArticlePagesSnapshotFromDocument(initialDocument);
    return CreateEditorState(
      editorKind: editorKind,
      draftFlowKind: draftFlowKind,
      mediaKind: CreateMediaKind.none,
      imagePaths: const <String>[],
      videoPath: '',
      originalVideoPath: '',
      videoThumbnail: '',
      videoDurationMs: 0,
      videoTrimStartMs: 0,
      videoTrimEndMs: 0,
      videoCoverTimeMs: 0,
      videoCoverStrategy: 'first_frame',
      videoWidth: 0,
      videoHeight: 0,
      videoMuted: false,
      isOneTapMovie: false,
      oneTapMoviePath: '',
      oneTapMovieEffectId: '',
      currentMediaIndex: 0,
      title: '',
      body: initialDocument.body,
      articleDocument: initialDocument,
      articlePages: initialPages,
      activeArticlePageId: initialPages.first.id,
      activeArticleBlockId: initialDocument.nodes.first.id,
      articleTemplate: ArticleTemplatePreset.gentle,
      articlePaperTexture: ArticlePaperTexture.darkPaper,
      articleFontPreset: ArticleFontPreset.clean,
      articleCoverImagePath: '',
      titlePresentation: TitlePresentation.collapsed,
      titleHintDismissed: false,
      settings: const PublishSettings(),
    );
  }

  final CreateEditorKind editorKind;
  final CreateDraftFlowKind draftFlowKind;
  final CreateMediaKind mediaKind;
  final List<String> imagePaths;
  final String videoPath;
  final String originalVideoPath;
  final String videoThumbnail;
  final int videoDurationMs;
  final int videoTrimStartMs;
  final int videoTrimEndMs;
  final int videoCoverTimeMs;
  final String videoCoverStrategy;
  final int videoWidth;
  final int videoHeight;
  final bool videoMuted;
  final bool isOneTapMovie;
  final String oneTapMoviePath;
  final String oneTapMovieEffectId;
  final int currentMediaIndex;
  final String title;
  final String body;
  final ArticleDocumentData articleDocument;
  final List<ArticlePageData> articlePages;
  final String? activeArticlePageId;
  final String? activeArticleBlockId;
  final ArticleTemplatePreset articleTemplate;
  final ArticlePaperTexture articlePaperTexture;
  final ArticleFontPreset articleFontPreset;
  final String articleCoverImagePath;
  final TitlePresentation titlePresentation;
  final bool titleHintDismissed;
  final PublishSettings settings;
  final String? draftId;

  bool get hasImages => imagePaths.isNotEmpty;
  bool get hasVideo => videoPath.trim().isNotEmpty;
  bool get hasTitle => title.trim().isNotEmpty;
  bool get hasBody => body.trim().isNotEmpty;
  bool get hasContent => hasTitle || hasBody || hasImages || hasVideo;
  bool get hasArticleImages => articleDocument.hasAssets;
  bool get shouldSuggestTitle {
    if (hasTitle) {
      return false;
    }
    if (editorKind == CreateEditorKind.media) {
      return mediaKind == CreateMediaKind.video ||
          imagePaths.length >= 4 ||
          body.trim().length >= 80;
    }
    final paragraphCount = body
        .split('\n')
        .map((line) => line.trim())
        .where((line) => line.isNotEmpty)
        .length;
    return body.trim().length >= 140 ||
        paragraphCount >= 2 ||
        imagePaths.isNotEmpty;
  }

  CreateEditorState copyWith({
    CreateEditorKind? editorKind,
    CreateDraftFlowKind? draftFlowKind,
    CreateMediaKind? mediaKind,
    List<String>? imagePaths,
    String? videoPath,
    String? originalVideoPath,
    String? videoThumbnail,
    int? videoDurationMs,
    int? videoTrimStartMs,
    int? videoTrimEndMs,
    int? videoCoverTimeMs,
    String? videoCoverStrategy,
    int? videoWidth,
    int? videoHeight,
    bool? videoMuted,
    bool? isOneTapMovie,
    String? oneTapMoviePath,
    String? oneTapMovieEffectId,
    int? currentMediaIndex,
    String? title,
    String? body,
    ArticleDocumentData? articleDocument,
    List<ArticlePageData>? articlePages,
    String? activeArticlePageId,
    String? activeArticleBlockId,
    ArticleTemplatePreset? articleTemplate,
    ArticlePaperTexture? articlePaperTexture,
    ArticleFontPreset? articleFontPreset,
    String? articleCoverImagePath,
    TitlePresentation? titlePresentation,
    bool? titleHintDismissed,
    PublishSettings? settings,
    String? draftId,
    bool clearDraftId = false,
    bool clearActiveArticlePageId = false,
    bool clearActiveArticleBlockId = false,
  }) {
    return CreateEditorState(
      editorKind: editorKind ?? this.editorKind,
      draftFlowKind: draftFlowKind ?? this.draftFlowKind,
      mediaKind: mediaKind ?? this.mediaKind,
      imagePaths: imagePaths ?? this.imagePaths,
      videoPath: videoPath ?? this.videoPath,
      originalVideoPath: originalVideoPath ?? this.originalVideoPath,
      videoThumbnail: videoThumbnail ?? this.videoThumbnail,
      videoDurationMs: videoDurationMs ?? this.videoDurationMs,
      videoTrimStartMs: videoTrimStartMs ?? this.videoTrimStartMs,
      videoTrimEndMs: videoTrimEndMs ?? this.videoTrimEndMs,
      videoCoverTimeMs: videoCoverTimeMs ?? this.videoCoverTimeMs,
      videoCoverStrategy: videoCoverStrategy ?? this.videoCoverStrategy,
      videoWidth: videoWidth ?? this.videoWidth,
      videoHeight: videoHeight ?? this.videoHeight,
      videoMuted: videoMuted ?? this.videoMuted,
      isOneTapMovie: isOneTapMovie ?? this.isOneTapMovie,
      oneTapMoviePath: oneTapMoviePath ?? this.oneTapMoviePath,
      oneTapMovieEffectId: oneTapMovieEffectId ?? this.oneTapMovieEffectId,
      currentMediaIndex: currentMediaIndex ?? this.currentMediaIndex,
      title: title ?? this.title,
      body: body ?? this.body,
      articleDocument: articleDocument ?? this.articleDocument,
      articlePages: articlePages ?? this.articlePages,
      activeArticlePageId: clearActiveArticlePageId
          ? null
          : (activeArticlePageId ?? this.activeArticlePageId),
      activeArticleBlockId: clearActiveArticleBlockId
          ? null
          : (activeArticleBlockId ?? this.activeArticleBlockId),
      articleTemplate: articleTemplate ?? this.articleTemplate,
      articlePaperTexture: articlePaperTexture ?? this.articlePaperTexture,
      articleFontPreset: articleFontPreset ?? this.articleFontPreset,
      articleCoverImagePath:
          articleCoverImagePath ?? this.articleCoverImagePath,
      titlePresentation: titlePresentation ?? this.titlePresentation,
      titleHintDismissed: titleHintDismissed ?? this.titleHintDismissed,
      settings: settings ?? this.settings,
      draftId: clearDraftId ? null : (draftId ?? this.draftId),
    );
  }
}
