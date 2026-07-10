import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/ui/content/models/article_document_models.dart';
import 'package:quwoquan_app/ui/content/article_render/services/article_flow_layout_engine.dart';
import 'package:quwoquan_app/ui/content/article_render/services/article_pagination_engine.dart';
import 'package:quwoquan_app/ui/content/models/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/models/publish_settings_models.dart';
import 'package:quwoquan_app/ui/content/article_render/markdown/article_markdown_codec.dart';
import 'package:quwoquan_app/ui/content/article_render/markdown/qwq_markdown_ast.dart';
part 'create_editor_models_article_blocks.dart';

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

enum CreateTextBlockType {
  paragraph,
  heading2,
  heading3,
  sectionTitle,
  orderedItem,
  bulletItem,
  image,
}

enum CreateTextImageLayout { fullWidth, wrapLeft, wrapRight }

@immutable
class CreateTextBlock {
  const CreateTextBlock({
    required this.id,
    required this.type,
    this.text = '',
    this.imagePath = '',
    this.imageLayout = CreateTextImageLayout.fullWidth,
  });

  factory CreateTextBlock.paragraph({required String id, String text = ''}) {
    return CreateTextBlock(
      id: id,
      type: CreateTextBlockType.paragraph,
      text: text,
    );
  }

  factory CreateTextBlock.orderedItem({required String id, String text = ''}) {
    return CreateTextBlock(
      id: id,
      type: CreateTextBlockType.orderedItem,
      text: text,
    );
  }

  factory CreateTextBlock.bulletItem({required String id, String text = ''}) {
    return CreateTextBlock(
      id: id,
      type: CreateTextBlockType.bulletItem,
      text: text,
    );
  }

  factory CreateTextBlock.heading2({required String id, String text = ''}) {
    return CreateTextBlock(
      id: id,
      type: CreateTextBlockType.heading2,
      text: text,
    );
  }

  factory CreateTextBlock.heading3({required String id, String text = ''}) {
    return CreateTextBlock(
      id: id,
      type: CreateTextBlockType.heading3,
      text: text,
    );
  }

  factory CreateTextBlock.sectionTitle({required String id, String text = ''}) {
    return CreateTextBlock(
      id: id,
      type: CreateTextBlockType.sectionTitle,
      text: text,
    );
  }

  factory CreateTextBlock.image({
    required String id,
    required String imagePath,
    CreateTextImageLayout imageLayout = CreateTextImageLayout.fullWidth,
  }) {
    return CreateTextBlock(
      id: id,
      type: CreateTextBlockType.image,
      imagePath: imagePath,
      imageLayout: imageLayout,
    );
  }

  factory CreateTextBlock.fromMap(Map<String, dynamic> map) {
    final typeName = (map['type'] ?? 'paragraph').toString().trim();
    final type = switch (typeName) {
      'heading2' => CreateTextBlockType.heading2,
      'heading3' => CreateTextBlockType.heading3,
      'sectionTitle' => CreateTextBlockType.sectionTitle,
      'orderedItem' => CreateTextBlockType.orderedItem,
      'bulletItem' => CreateTextBlockType.bulletItem,
      'image' => CreateTextBlockType.image,
      _ => CreateTextBlockType.paragraph,
    };
    final layoutName = (map['imageLayout'] ?? 'fullWidth').toString().trim();
    final imageLayout = switch (layoutName) {
      'wrapLeft' => CreateTextImageLayout.wrapLeft,
      'wrapRight' => CreateTextImageLayout.wrapRight,
      _ => CreateTextImageLayout.fullWidth,
    };
    return CreateTextBlock(
      id: (map['id'] ?? '').toString(),
      type: type,
      text: (map['text'] ?? '').toString(),
      imagePath: (map['imagePath'] ?? '').toString(),
      imageLayout: imageLayout,
    );
  }

  final String id;
  final CreateTextBlockType type;
  final String text;
  final String imagePath;
  final CreateTextImageLayout imageLayout;

  bool get isTextLike => type != CreateTextBlockType.image;
  bool get hasText => text.trim().isNotEmpty;
  bool get hasImage => imagePath.trim().isNotEmpty;
  bool get usesWrappedLayout =>
      imageLayout == CreateTextImageLayout.wrapLeft ||
      imageLayout == CreateTextImageLayout.wrapRight;

  CreateTextBlock copyWith({
    String? id,
    CreateTextBlockType? type,
    String? text,
    String? imagePath,
    CreateTextImageLayout? imageLayout,
  }) {
    return CreateTextBlock(
      id: id ?? this.id,
      type: type ?? this.type,
      text: text ?? this.text,
      imagePath: imagePath ?? this.imagePath,
      imageLayout: imageLayout ?? this.imageLayout,
    );
  }

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      'id': id,
      'type': type.name,
      'text': text,
      'imagePath': imagePath,
      'imageLayout': imageLayout.name,
    };
  }
}

List<CreateTextBlock> createDefaultArticleBlocks({
  String body = '',
  List<String> imagePaths = const <String>[],
}) {
  final blocks =
      <CreateTextBlock>[
            CreateTextBlock.paragraph(id: 'paragraph_0', text: body),
            ...imagePaths.asMap().entries.map(
              (entry) => CreateTextBlock.image(
                id: 'image_${entry.key}',
                imagePath: entry.value,
              ),
            ),
          ]
          .where(
            (block) =>
                block.hasImage ||
                block.text.isNotEmpty ||
                block.type == CreateTextBlockType.paragraph,
          )
          .toList(growable: false);
  if (blocks.isEmpty) {
    return const <CreateTextBlock>[
      CreateTextBlock(id: 'paragraph_0', type: CreateTextBlockType.paragraph),
    ];
  }
  return blocks;
}

String buildArticlePlainText(List<CreateTextBlock> blocks) {
  final lines = <String>[];
  var orderedIndex = 0;
  for (final block in blocks.where(
    (block) => block.isTextLike && block.hasText,
  )) {
    final text = block.text.trim();
    final line = switch (block.type) {
      CreateTextBlockType.orderedItem =>
        text.isEmpty ? '' : '${++orderedIndex}. $text',
      CreateTextBlockType.bulletItem => text.isEmpty ? '' : '• $text',
      _ => (() {
        orderedIndex = 0;
        return text;
      })(),
    };
    if (line.isNotEmpty) {
      lines.add(line);
    }
    if (block.type != CreateTextBlockType.orderedItem) {
      orderedIndex = 0;
    }
  }
  return lines.join('\n');
}

List<String> extractArticleImagePaths(List<CreateTextBlock> blocks) {
  return blocks
      .where((block) => block.hasImage)
      .map((block) => block.imagePath.trim())
      .where((path) => path.isNotEmpty)
      .toList(growable: false);
}

ArticleDocumentBlock _documentBlockFromEditorBlock(
  CreateTextBlock block, {
  int offset = 0,
  int? orderedIndex,
}) {
  return ArticleDocumentBlock(
    id: block.id,
    type: switch (block.type) {
      CreateTextBlockType.heading2 => ArticleDocumentBlockType.heading2,
      CreateTextBlockType.heading3 => ArticleDocumentBlockType.heading3,
      CreateTextBlockType.sectionTitle => ArticleDocumentBlockType.sectionTitle,
      CreateTextBlockType.orderedItem => ArticleDocumentBlockType.orderedItem,
      CreateTextBlockType.bulletItem => ArticleDocumentBlockType.bulletItem,
      CreateTextBlockType.image => ArticleDocumentBlockType.image,
      CreateTextBlockType.paragraph => ArticleDocumentBlockType.paragraph,
    },
    offset: offset,
    text: block.text,
    imageUrl: block.imagePath,
    imageLayout: block.imageLayout.name,
    orderedIndex: orderedIndex,
  );
}

CreateTextBlock _editorBlockFromDocumentBlock(ArticleDocumentBlock block) {
  return switch (block.type) {
    ArticleDocumentBlockType.heading2 => CreateTextBlock.heading2(
      id: block.id,
      text: block.text,
    ),
    ArticleDocumentBlockType.heading3 => CreateTextBlock.heading3(
      id: block.id,
      text: block.text,
    ),
    ArticleDocumentBlockType.sectionTitle => CreateTextBlock.sectionTitle(
      id: block.id,
      text: block.text,
    ),
    ArticleDocumentBlockType.orderedItem => CreateTextBlock.orderedItem(
      id: block.id,
      text: block.text,
    ),
    ArticleDocumentBlockType.bulletItem => CreateTextBlock.bulletItem(
      id: block.id,
      text: block.text,
    ),
    ArticleDocumentBlockType.image => CreateTextBlock.image(
      id: block.id,
      imagePath: block.imageUrl,
      imageLayout: _imageLayoutFromPage(block.imageLayout),
    ),
    ArticleDocumentBlockType.paragraph => CreateTextBlock.paragraph(
      id: block.id,
      text: block.text,
    ),
  };
}

String _normalizeArticleBody(String value) {
  return value.replaceAll('\r\n', '\n');
}

ArticleDocumentData createDefaultArticleDocument({
  String title = '',
  String body = '',
  List<String> imagePaths = const <String>[],
}) {
  final normalizedBody = _normalizeArticleBody(body);
  final sanitizedImages = imagePaths
      .map((path) => path.trim())
      .where((path) => path.isNotEmpty)
      .toList(growable: false);
  return ArticleDocumentData(
    title: title,
    body: normalizedBody,
    assets: [
      for (final entry in sanitizedImages.asMap().entries)
        ArticleDocumentAsset(
          id: 'asset_${entry.key}',
          offset: entry.key == 0 ? 0 : normalizedBody.length,
          imageUrl: entry.value,
        ),
    ],
  );
}

ArticleDocumentData buildArticleDocumentFromPages(
  List<ArticlePageData> pages, {
  String title = '',
}) {
  if (pages.isEmpty) {
    return createDefaultArticleDocument(title: title);
  }

  final structuredBlocks = pages
      .expand((page) => page.contentBlocks)
      .where((block) => block.id.trim().isNotEmpty)
      .toList(growable: false);
  if (structuredBlocks.isNotEmpty) {
    final buffer = StringBuffer();
    final assets = <ArticleDocumentAsset>[];
    final blocks = <ArticleDocumentBlock>[];
    var assetSeed = 0;
    for (final page in pages) {
      final imageUrl = page.imageUrl.trim();
      if (imageUrl.isNotEmpty) {
        assets.add(
          ArticleDocumentAsset(
            id: 'asset_${assetSeed++}',
            offset: buffer.length,
            imageUrl: imageUrl,
            imageLayout: page.imageLayout,
            caption: page.caption,
          ),
        );
      }
      for (final block in page.contentBlocks) {
        blocks.add(block.copyWith(offset: buffer.length));
      }
      final normalized = _normalizeArticleBody(page.body).trim();
      if (normalized.isEmpty) {
        continue;
      }
      if (buffer.isNotEmpty) {
        buffer.write('\n');
      }
      buffer.write(normalized);
    }
    return ArticleDocumentData(
      title: pages.first.title.trim().isNotEmpty ? pages.first.title : title,
      body: buffer.toString(),
      assets: assets,
      blocks: blocks,
    );
  }

  final buffer = StringBuffer();
  final assets = <ArticleDocumentAsset>[];
  final resolvedTitle = pages.first.title.trim().isNotEmpty
      ? pages.first.title
      : title;
  var assetSeed = 0;

  void appendBody(String value) {
    final normalized = _normalizeArticleBody(value).trim();
    if (normalized.isEmpty) {
      return;
    }
    if (buffer.isNotEmpty) {
      buffer.write('\n');
    }
    buffer.write(normalized);
  }

  for (final page in pages) {
    final imageUrl = page.imageUrl.trim();
    if (imageUrl.isNotEmpty) {
      assets.add(
        ArticleDocumentAsset(
          id: 'asset_${assetSeed++}',
          offset: buffer.length,
          imageUrl: imageUrl,
          imageLayout: page.imageLayout,
          caption: page.caption,
        ),
      );
    }
    appendBody(page.body);
  }

  return ArticleDocumentData(
    title: resolvedTitle,
    body: buffer.toString(),
    assets: assets,
  );
}

ArticleDocumentData buildArticleDocumentFromBlocks(
  List<CreateTextBlock> blocks, {
  String title = '',
}) {
  if (blocks.isEmpty) {
    return createDefaultArticleDocument(title: title);
  }

  final buffer = StringBuffer();
  final assets = <ArticleDocumentAsset>[];
  final documentBlocks = <ArticleDocumentBlock>[];
  var assetSeed = 0;
  var orderedIndex = 0;

  void appendLine(String line) {
    final normalized = line.trim();
    if (normalized.isEmpty) {
      return;
    }
    if (buffer.isNotEmpty) {
      buffer.write('\n');
    }
    buffer.write(normalized);
  }

  for (final block in blocks) {
    switch (block.type) {
      case CreateTextBlockType.image:
        final imagePath = block.imagePath.trim();
        if (imagePath.isEmpty) {
          continue;
        }
        assets.add(
          ArticleDocumentAsset(
            id: block.id.isNotEmpty ? block.id : 'asset_${assetSeed++}',
            offset: buffer.length,
            imageUrl: imagePath,
            imageLayout: block.imageLayout.name,
          ),
        );
        orderedIndex = 0;
        break;
      case CreateTextBlockType.heading2:
        orderedIndex = 0;
        documentBlocks.add(
          _documentBlockFromEditorBlock(block, offset: buffer.length),
        );
        break;
      case CreateTextBlockType.heading3:
        orderedIndex = 0;
        documentBlocks.add(
          _documentBlockFromEditorBlock(block, offset: buffer.length),
        );
        break;
      case CreateTextBlockType.sectionTitle:
        orderedIndex = 0;
        documentBlocks.add(
          _documentBlockFromEditorBlock(block, offset: buffer.length),
        );
        break;
      case CreateTextBlockType.orderedItem:
        orderedIndex += 1;
        appendLine('$orderedIndex. ${block.text.trim()}');
        break;
      case CreateTextBlockType.bulletItem:
        orderedIndex = 0;
        appendLine(block.text.trim().isEmpty ? '' : '• ${block.text.trim()}');
        break;
      case CreateTextBlockType.paragraph:
        orderedIndex = 0;
        appendLine(block.text);
        break;
    }
  }

  return ArticleDocumentData(
    title: title,
    body: buffer.toString(),
    assets: assets,
    blocks: documentBlocks,
  );
}

String buildArticlePlainTextFromDocument(ArticleDocumentData document) {
  if (document.blocks.isNotEmpty) {
    return buildArticlePlainText(buildArticleBlocksFromDocument(document));
  }
  return _normalizeArticleBody(document.body).trim();
}

List<String> extractArticleImagePathsFromDocument(
  ArticleDocumentData document,
) {
  if (document.assets.isEmpty && document.blocks.isNotEmpty) {
    return document.blocks
        .where((block) => block.hasImage)
        .map((block) => block.imageUrl.trim())
        .where((path) => path.isNotEmpty)
        .toList(growable: false);
  }
  return document.assets
      .map((asset) => asset.imageUrl.trim())
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

const int kArticlePageSoftCharacterLimit = 150;

final RegExp _orderedArticleLinePattern = RegExp(r'^\s*(\d+)[\.\u3001]\s+');
final RegExp _bulletArticleLinePattern = RegExp(r'^\s*[•\-]\s+');

List<ArticlePageData> createDefaultArticlePages({
  String title = '',
  String body = '',
  List<String> imagePaths = const <String>[],
}) {
  final document = createDefaultArticleDocument(
    title: title,
    body: body,
    imagePaths: imagePaths,
  );
  return buildArticlePagesSnapshotFromDocument(document);
}

List<ArticlePageData> buildArticlePagesFromBlocks(
  List<CreateTextBlock> blocks, {
  String title = '',
}) {
  final document = buildArticleDocumentFromBlocks(blocks, title: title);
  return buildArticlePagesSnapshotFromDocument(document);
}

CreateTextImageLayout _imageLayoutFromPage(String layout) {
  return switch (layout.trim()) {
    'wrapLeft' => CreateTextImageLayout.wrapLeft,
    'wrapRight' => CreateTextImageLayout.wrapRight,
    _ => CreateTextImageLayout.fullWidth,
  };
}

List<CreateTextBlock> buildArticleBlocksFromPages(List<ArticlePageData> pages) {
  final structuredBlocks = pages
      .expand((page) => page.contentBlocks)
      .where((block) => block.id.trim().isNotEmpty)
      .toList(growable: false);
  if (structuredBlocks.isNotEmpty) {
    return structuredBlocks
        .map(_editorBlockFromDocumentBlock)
        .toList(growable: false);
  }
  final document = buildArticleDocumentFromPages(pages);
  return buildArticleBlocksFromDocument(document);
}

String buildArticlePlainTextFromPages(List<ArticlePageData> pages) {
  return buildArticlePlainTextFromDocument(
    buildArticleDocumentFromPages(pages),
  );
}

List<String> extractArticleImagePathsFromPages(List<ArticlePageData> pages) {
  return extractArticleImagePathsFromDocument(
    buildArticleDocumentFromPages(pages),
  );
}

List<Map<String, dynamic>> buildArticleCardsFromPages(
  List<ArticlePageData> pages,
) {
  return pages
      .where((page) => !page.isEmpty)
      .map(
        (page) => <String, dynamic>{
          'title': page.title.trim(),
          'body': page.body.trim(),
          'layout': page.hasImage
              ? (page.usesWrappedLayout ? 'half' : 'full')
              : 'full',
          if (page.imageUrl.trim().isNotEmpty) 'imageUrl': page.imageUrl.trim(),
          if (page.caption.trim().isNotEmpty) 'caption': page.caption.trim(),
          'imageLayout': page.imageLayout,
        },
      )
      .toList(growable: false);
}

int resolveArticlePageSplitIndex(
  String text, {
  int softLimit = kArticlePageSoftCharacterLimit,
}) {
  final normalized = text.trimRight();
  if (normalized.length <= softLimit) {
    return normalized.length;
  }

  const breakTokens = <String>['\n', '。', '！', '？', '；', '，', '、', '.', ' '];
  for (var index = softLimit; index >= softLimit ~/ 2; index -= 1) {
    final token = normalized[index - 1];
    if (breakTokens.contains(token)) {
      return index;
    }
  }
  return softLimit.clamp(1, normalized.length);
}

/// 创作发布草稿聚合（`metadata_driven_ui_gap_inventory`：`ContentPublishDraftComposite`）。
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
    required this.articleBlocks,
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
    final initialBlocks = buildArticleBlocksFromDocument(initialDocument);
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
      articleBlocks: initialBlocks,
      activeArticlePageId: initialPages.first.id,
      activeArticleBlockId: initialBlocks.first.id,
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
  final List<CreateTextBlock> articleBlocks;
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
  bool get hasArticleImages =>
      extractArticleImagePaths(articleBlocks).isNotEmpty;
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
    List<CreateTextBlock>? articleBlocks,
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
      articleBlocks: articleBlocks ?? this.articleBlocks,
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

@immutable
class CreateDraft {
  const CreateDraft({
    required this.id,
    required this.updatedAtMs,
    required this.state,
    this.sourceType,
  });

  final String id;
  final int updatedAtMs;
  final CreateEditorState state;
  final String? sourceType;

  factory CreateDraft.fromStorageMap(Map<String, dynamic> map) {
    final editorKind = (map['editorKind']?.toString() ?? 'text') == 'media'
        ? CreateEditorKind.media
        : CreateEditorKind.text;
    final mediaKindName = (map['mediaKind']?.toString() ?? 'none').trim();
    final mediaKind = switch (mediaKindName) {
      'images' => CreateMediaKind.images,
      'video' => CreateMediaKind.video,
      _ => CreateMediaKind.none,
    };
    final settingsMap = Map<String, dynamic>.from(
      map['settings'] as Map? ?? const <String, dynamic>{},
    );
    final storedBody = (map['body'] ?? '').toString();
    final storedImagePaths = List<String>.from(
      map['imagePaths'] as List? ?? const <String>[],
    );
    final storedMarkdown = (map['articleMarkdown'] ?? '').toString();
    final storedAssetManifest = Map<String, dynamic>.from(
      map['articleAssetManifest'] as Map? ?? const <String, dynamic>{},
    );
    // 本地草稿唯一正文真相源为 articleMarkdown；不再从 articleDocument /
    // articlePages / articleBlocks 等旧存储键恢复（未上线，不做兼容读取）。
    final articleDocument = storedMarkdown.trim().isNotEmpty
        ? ArticleMarkdownCodec.parseDocument(
            storedMarkdown,
            assetManifest: storedAssetManifest,
          )
        : buildArticleDocumentFromBlocks(
            createDefaultArticleBlocks(
              body: storedBody,
              imagePaths: storedImagePaths,
            ),
            title: (map['title'] ?? '').toString(),
          );
    final normalizedBlocks = buildArticleBlocksFromDocument(articleDocument);
    final normalizedPages = buildArticlePagesSnapshotFromDocument(
      articleDocument,
      fontPreset: articleFontPresetFromString(
        map['articleFontPreset']?.toString(),
      ),
    );
    final storedCover = (map['articleCoverImagePath'] ?? map['coverUrl'] ?? '')
        .toString()
        .trim();
    final draftType = (map['type'] ?? editorKind.name).toString().trim();
    final draftFlowKind = _draftFlowKindFromStorage(
      rawDraftFlowKind: map['draftFlowKind']?.toString(),
      sourceType: draftType,
      editorKind: editorKind,
      mediaKind: mediaKind,
    );
    return CreateDraft(
      id: (map['id'] ?? '').toString(),
      updatedAtMs: (map['updatedAt'] as num?)?.toInt() ?? 0,
      state: CreateEditorState(
        editorKind: editorKind,
        draftFlowKind: draftFlowKind,
        mediaKind: mediaKind,
        imagePaths: editorKind == CreateEditorKind.text
            ? extractArticleImagePaths(normalizedBlocks)
            : storedImagePaths,
        videoPath: (map['videoPath'] ?? '').toString(),
        originalVideoPath:
            ((map['originalVideoPath'] ?? map['videoPath']) ?? '').toString(),
        videoThumbnail: (map['videoThumbnail'] ?? '').toString(),
        videoDurationMs: (map['videoDurationMs'] as num?)?.toInt() ?? 0,
        videoTrimStartMs: (map['videoTrimStartMs'] as num?)?.toInt() ?? 0,
        videoTrimEndMs: (map['videoTrimEndMs'] as num?)?.toInt() ?? 0,
        videoCoverTimeMs: (map['videoCoverTimeMs'] as num?)?.toInt() ?? 0,
        videoCoverStrategy:
            (map['videoCoverStrategy'] ?? '').toString().trim().isNotEmpty
            ? (map['videoCoverStrategy'] ?? '').toString().trim()
            : (((map['videoCoverTimeMs'] as num?)?.toInt() ?? 0) > 0
                  ? 'manual'
                  : 'first_frame'),
        videoWidth: (map['videoWidth'] as num?)?.toInt() ?? 0,
        videoHeight: (map['videoHeight'] as num?)?.toInt() ?? 0,
        videoMuted: map['videoMuted'] == true,
        isOneTapMovie: map['isOneTapMovie'] == true,
        oneTapMoviePath: (map['oneTapMoviePath'] ?? '').toString(),
        oneTapMovieEffectId: (map['oneTapMovieEffectId'] ?? '').toString(),
        currentMediaIndex:
            (map['currentMediaIndex'] as num?)?.toInt().clamp(0, 9999) ?? 0,
        title: (map['title'] ?? '').toString(),
        body: editorKind == CreateEditorKind.text
            ? buildArticlePlainTextFromDocument(articleDocument)
            : storedBody,
        articleDocument: articleDocument,
        articlePages: normalizedPages,
        articleBlocks: normalizedBlocks,
        activeArticlePageId:
            (map['activeArticlePageId'] ?? '').toString().trim().isEmpty
            ? normalizedPages.first.id
            : (map['activeArticlePageId'] ?? '').toString().trim(),
        activeArticleBlockId:
            (map['activeArticleBlockId'] ?? '').toString().trim().isEmpty
            ? normalizedBlocks.first.id
            : (map['activeArticleBlockId'] ?? '').toString().trim(),
        articleTemplate: articleTemplatePresetFromString(
          map['articleTemplate']?.toString(),
        ),
        articlePaperTexture: articlePaperTextureFromString(
          map['articlePaperTexture']?.toString(),
        ),
        articleFontPreset: articleFontPresetFromString(
          map['articleFontPreset']?.toString(),
        ),
        articleCoverImagePath: storedCover,
        titlePresentation:
            (map['titlePresentation']?.toString() ?? 'collapsed') == 'expanded'
            ? TitlePresentation.expanded
            : TitlePresentation.collapsed,
        titleHintDismissed: map['titleHintDismissed'] == true,
        settings: PublishSettings.fromMap(settingsMap),
        draftId: (map['id'] ?? '').toString(),
      ),
      sourceType: draftType,
    );
  }

  Map<String, dynamic> toStorageMap() {
    final articleMarkdown = _articleMarkdownForStorage();
    final articleAssetManifest = _articleAssetManifestForStorage();
    final articleRenderProfile = _articleRenderProfileForStorage();
    return <String, dynamic>{
      'id': id,
      'type': storageType,
      'updatedAt': updatedAtMs,
      'identity': identity.value,
      'editorKind': state.editorKind.name,
      'draftFlowKind': state.draftFlowKind.name,
      'mediaKind': state.mediaKind.name,
      'imagePaths': state.imagePaths,
      'videoPath': state.videoPath,
      'originalVideoPath': state.originalVideoPath,
      'videoThumbnail': state.videoThumbnail,
      'videoDurationMs': state.videoDurationMs,
      'videoTrimStartMs': state.videoTrimStartMs,
      'videoTrimEndMs': state.videoTrimEndMs,
      'videoCoverTimeMs': state.videoCoverTimeMs,
      'videoCoverStrategy': state.videoCoverStrategy,
      'videoWidth': state.videoWidth,
      'videoHeight': state.videoHeight,
      'videoMuted': state.videoMuted,
      'isOneTapMovie': state.isOneTapMovie,
      'oneTapMoviePath': state.oneTapMoviePath,
      'oneTapMovieEffectId': state.oneTapMovieEffectId,
      'currentMediaIndex': state.currentMediaIndex,
      'title': state.title,
      'body': state.body,
      'articleMarkdown': articleMarkdown,
      'articleMarkdownVersion': qwqRichMarkdownVersion,
      'articleAssetManifest': articleAssetManifest,
      'articleRenderProfile': articleRenderProfile,
      'activeArticlePageId': state.activeArticlePageId,
      'activeArticleBlockId': state.activeArticleBlockId,
      'articleTemplate': state.articleTemplate.name,
      'articlePaperTexture': state.articlePaperTexture.name,
      'articleFontPreset': state.articleFontPreset.name,
      'articleCoverImagePath': state.articleCoverImagePath,
      'coverUrl': state.articleCoverImagePath,
      'titlePresentation': state.titlePresentation.name,
      'titleHintDismissed': state.titleHintDismissed,
      'settings': state.settings.toMap(),
      'data': data,
    };
  }

  String get storageType {
    if (state.editorKind == CreateEditorKind.media) {
      return state.mediaKind == CreateMediaKind.video ? 'video' : 'media';
    }
    return 'text';
  }

  CreateDraftFlowKind get flowKind => state.draftFlowKind;

  String get tabKey {
    if (sourceType != null && sourceType!.isNotEmpty) {
      return sourceType!;
    }
    return storageType;
  }

  CreateContentIdentity get identity {
    switch (tabKey) {
      case 'media':
      case 'photo':
      case 'video':
      case 'article':
        return CreateContentIdentity.work;
      default:
        return CreateContentIdentity.moment;
    }
  }

  Map<String, dynamic> get data {
    final articleMarkdown = _articleMarkdownForStorage();
    final articleAssetManifest = _articleAssetManifestForStorage();
    final articleRenderProfile = _articleRenderProfileForStorage();
    return <String, dynamic>{
      ...state.settings.toMap(),
      'title': state.title,
      'body': state.body,
      'articleMarkdown': articleMarkdown,
      'articleMarkdownVersion': qwqRichMarkdownVersion,
      'articleAssetManifest': articleAssetManifest,
      'articleRenderProfile': articleRenderProfile,
      'articleTemplate': state.articleTemplate.name,
      'articlePaperTexture': state.articlePaperTexture.name,
      'articleFontPreset': state.articleFontPreset.name,
      'articleCoverImagePath': state.articleCoverImagePath,
      'coverUrl': state.articleCoverImagePath,
      'imagePaths': state.imagePaths,
      'videoPath': state.videoPath,
      'originalVideoPath': state.originalVideoPath,
      'videoThumbnail': state.videoThumbnail,
      'videoDurationMs': state.videoDurationMs,
      'videoTrimStartMs': state.videoTrimStartMs,
      'videoTrimEndMs': state.videoTrimEndMs,
      'videoCoverTimeMs': state.videoCoverTimeMs,
      'videoCoverStrategy': state.videoCoverStrategy,
      'videoWidth': state.videoWidth,
      'videoHeight': state.videoHeight,
      'videoMuted': state.videoMuted,
      'isOneTapMovie': state.isOneTapMovie,
      'oneTapMoviePath': state.oneTapMoviePath,
      'oneTapMovieEffectId': state.oneTapMovieEffectId,
    };
  }

  String _articleMarkdownForStorage() {
    return ArticleMarkdownCodec.serializeDocument(
      state.articleDocument,
      summary: state.settings.summary,
      tagRefs: state.settings.tagRefs,
      entityRefs: state.settings.entityRefs,
      visibility: state.settings.isPublic ? 'public' : 'private',
      assistantUsePolicy: state.settings.assistantUsePolicy,
      coverAssetId: state.articleCoverImagePath.trim().isNotEmpty
          ? 'cover'
          : '',
      coverImageUrl: state.articleCoverImagePath,
    );
  }

  Map<String, dynamic> _articleAssetManifestForStorage() {
    final assets = <Map<String, Object?>>[];
    final cover = state.articleCoverImagePath.trim();
    if (cover.isNotEmpty) {
      assets.add(_articleDraftManifestRow('cover', cover, role: 'cover'));
    }
    for (final asset in state.articleDocument.assets) {
      final imageUrl = asset.imageUrl.trim();
      if (imageUrl.isEmpty) {
        continue;
      }
      final assetId = asset.id.trim().isNotEmpty ? asset.id.trim() : imageUrl;
      assets.add(_articleDraftManifestRow(assetId, imageUrl, role: 'figure'));
    }
    return <String, dynamic>{
      'schemaVersion': 1,
      'markdownVersion': qwqRichMarkdownVersion,
      'assets': assets,
    };
  }

  Map<String, dynamic> _articleRenderProfileForStorage() {
    return <String, dynamic>{
      'template': state.articleTemplate.name,
      'paperTexture': state.articlePaperTexture.name,
      'fontPreset': state.articleFontPreset.name,
      'titleStyle': state.articleDocument.titleStyle.name,
    };
  }

  String get previewText {
    final primary = state.title.trim();
    if (primary.isNotEmpty) {
      return primary;
    }
    return state.body.trim();
  }

  String get draftLabel {
    return switch (flowKind) {
      CreateDraftFlowKind.image => '图片草稿',
      CreateDraftFlowKind.video => '视频草稿',
      CreateDraftFlowKind.article => '文章草稿',
    };
  }

  bool get shouldSuggestTitle {
    if (state.title.trim().isNotEmpty) {
      return false;
    }
    if (state.editorKind == CreateEditorKind.media) {
      return state.mediaKind == CreateMediaKind.video ||
          state.imagePaths.length >= 4 ||
          state.body.trim().length >= 80;
    }
    final body = state.body.trim();
    final paragraphCount = body
        .split('\n')
        .map((line) => line.trim())
        .where((line) => line.isNotEmpty)
        .length;
    return body.length >= 140 ||
        paragraphCount >= 2 ||
        state.imagePaths.isNotEmpty;
  }
}

CreateDraftFlowKind _draftFlowKindFromStorage({
  required String? rawDraftFlowKind,
  required String? sourceType,
  required CreateEditorKind editorKind,
  required CreateMediaKind mediaKind,
}) {
  final normalizedFlow = (rawDraftFlowKind ?? '').trim();
  switch (normalizedFlow) {
    case 'image':
      return CreateDraftFlowKind.image;
    case 'video':
      return CreateDraftFlowKind.video;
    case 'article':
      return CreateDraftFlowKind.article;
  }

  final normalizedSource = (sourceType ?? '').trim();
  switch (normalizedSource) {
    case 'media':
    case 'photo':
    case 'gallery':
    case 'image':
      return CreateDraftFlowKind.image;
    case 'video':
    case 'capture':
      return CreateDraftFlowKind.video;
    case 'text':
    case 'article':
    case 'write':
      return CreateDraftFlowKind.article;
  }

  if (mediaKind == CreateMediaKind.video) {
    return CreateDraftFlowKind.video;
  }
  if (editorKind == CreateEditorKind.media) {
    return CreateDraftFlowKind.image;
  }
  return CreateDraftFlowKind.article;
}

Map<String, Object?> _articleDraftManifestRow(
  String assetId,
  String path, {
  required String role,
}) {
  return <String, Object?>{
    'assetId': assetId,
    'kind': 'image',
    'role': role,
    'scope': 'draft',
    'localPath': path,
    'objectKey': path.startsWith('asset://')
        ? path.substring('asset://'.length)
        : path,
    'sha256': '',
  };
}
