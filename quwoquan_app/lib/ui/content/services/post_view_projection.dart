import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_detail_payload.dart';
import 'package:quwoquan_app/cloud/runtime/models/post_read_presentation_mapper.dart';
import 'package:quwoquan_app/cloud/services/content/content_read_model_projection.dart';
import 'package:quwoquan_app/core/media/content_media_url.dart';
import 'package:quwoquan_app/ui/content/models/article_detail_view.dart';
import 'package:quwoquan_app/ui/content/models/article_document_models.dart';
import 'package:quwoquan_app/ui/content/models/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/article_render/markdown/article_markdown_codec.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view.dart';

/// 自 [ContentReadRepository.getPost] 返回的 [ContentPostDetailPayload] 投射出文章富渲染载荷。
ContentArticleRender projectArticleDetailViewFromPayload(
  ContentPostDetailPayload payload, {
  required String fallbackArticleId,
}) {
  return projectArticleDetailView(
    payload.mergedArticleWireMap,
    fallbackArticleId: fallbackArticleId,
  );
}

/// 文章详情投射：raw post map → [ContentArticleRender]（富渲染载荷，挂载到
/// [ContentSurfaceView.article]）。公共字段（作者/统计/标题/封面）由
/// [ContentSurfaceViewMapper.fromDto] 同源承载，本投影只负责文档/分页/内容块。
///
/// 文章正文唯一真相源为 `articleMarkdown`（经 [ArticleMarkdownCodec] 解析为
/// [ArticleDocumentData]，再派生 pages / contentBlocks）。不存在 markdown 时
/// 视为空文档（仅以标题/封面降级展示），不再消费旧的 articleBlocks / cards /
/// articlePages / body 等竞争内容源。
ContentArticleRender projectArticleDetailView(
  Map<String, dynamic> raw, {
  required String fallbackArticleId,
}) {
  final dto = contentPostViewDataFromReadModelMap(raw);
  final read = PostReadPresentationMapper.fromViewData(dto, wire: raw);
  final postTitle = read.title;
  final body = read.body;
  final mediaCoverUrl = resolveContentMediaUrl(dto.mediaCoverUrl);
  final mediaThumbnailUrl = resolveContentMediaUrl(dto.mediaThumbnailUrl);
  final primaryImageUrl = resolveContentMediaUrl(dto.primaryImageUrl);
  final primaryVisualUrl = resolveContentMediaUrl(dto.primaryVisualUrl);
  var images = dto.hasImages
      ? dto.mediaImageUrls
            .map(resolveContentMediaUrl)
            .where((url) => url.isNotEmpty)
            .toList(growable: false)
      : const <String>[];
  if (dto.isArticleLike && mediaCoverUrl.isNotEmpty && images.isEmpty) {
    images = <String>[mediaCoverUrl];
  }
  final coverFromDto = mediaCoverUrl.isNotEmpty
      ? mediaCoverUrl
      : primaryImageUrl;
  final thumbnailFromDto = mediaThumbnailUrl.isNotEmpty
      ? mediaThumbnailUrl
      : primaryVisualUrl;
  final coverImage = coverFromDto.isNotEmpty
      ? coverFromDto
      : (images.isNotEmpty
            ? images.first
            : (thumbnailFromDto.isNotEmpty ? thumbnailFromDto : ''));
  final documentSource = _resolveArticleDocumentSource(raw);
  final hasMarkdownDocument =
      documentSource == ArticleDetailDocumentSource.markdown;
  final document = _projectArticleDocument(
    raw: raw,
    postTitle: postTitle,
    coverImage: coverImage,
  );
  final pages = _projectArticlePages(
    postTitle: postTitle.trim().isNotEmpty ? postTitle : document.title,
    body: body,
    coverImage: coverImage,
    document: hasMarkdownDocument ? document : null,
  );
  final contentBlocks = _projectArticleContentBlocks(
    document: hasMarkdownDocument ? document : null,
  );

  return ContentArticleRender(
    contentHtml: hasMarkdownDocument ? body : '',
    layoutMode: images.length > 1 ? 'carousel' : 'hero',
    images: images,
    contentBlocks: contentBlocks,
    document: document,
    pages: pages,
    template: articleTemplatePresetFromString(
      raw[ArticleDetailWireKeys.articleTemplate]?.toString(),
    ),
    fontPreset: articleFontPresetFromString(
      raw[ArticleDetailWireKeys.articleFontPreset]?.toString(),
    ),
    documentSource: documentSource,
    isOfficial: raw[ArticleDetailWireKeys.isOfficial] == true,
    badge: raw[ArticleDetailWireKeys.badge]?.toString(),
  );
}

Map<String, dynamic>? _articleAssetManifestMap(Map<String, dynamic> raw) {
  final manifest = raw[ArticleDetailWireKeys.articleAssetManifest];
  if (manifest is Map) {
    return Map<String, dynamic>.from(manifest);
  }
  return null;
}

ArticleDetailDocumentSource _resolveArticleDocumentSource(
  Map<String, dynamic> raw,
) {
  final markdown = raw[ArticleDetailWireKeys.articleMarkdown]?.toString() ?? '';
  if (markdown.trim().isNotEmpty) {
    return ArticleDetailDocumentSource.markdown;
  }
  return ArticleDetailDocumentSource.empty;
}

ArticleDocumentData _projectArticleDocument({
  required Map<String, dynamic> raw,
  required String postTitle,
  required String coverImage,
}) {
  final markdown = raw[ArticleDetailWireKeys.articleMarkdown]?.toString() ?? '';
  if (markdown.trim().isNotEmpty) {
    return ArticleMarkdownCodec.parseDocument(
      markdown,
      assetManifest: _articleAssetManifestMap(raw),
    );
  }
  final normalizedTitle = postTitle.trim();
  return ArticleDocumentData(
    nodes: normalizedTitle.isEmpty
        ? const <ArticleDocumentNode>[]
        : <ArticleDocumentNode>[
            ArticleDocumentNode(
              id: 'document_title',
              type: ArticleDocumentNodeType.documentTitle,
              text: normalizedTitle,
            ),
          ],
    template:
        raw[ArticleDetailWireKeys.articleTemplate]?.toString() ?? 'gentle',
    fontPreset:
        raw[ArticleDetailWireKeys.articleFontPreset]?.toString() ?? 'clean',
    coverImageUrl: coverImage.trim(),
  );
}

List<ArticlePageData> _projectArticlePages({
  required String postTitle,
  required String body,
  required String coverImage,
  ArticleDocumentData? document,
}) {
  final canonicalDocument = document;
  if (canonicalDocument != null && !canonicalDocument.isEmpty) {
    final projected = ArticlePageData(
      id: 'page_0',
      title: canonicalDocument.title.trim().isNotEmpty
          ? canonicalDocument.title.trim()
          : postTitle.trim(),
      body: canonicalDocument.body.trim(),
      imageUrl: coverImage.trim(),
      contentBlocks: canonicalDocument.contentBlocks,
    );
    return <ArticlePageData>[
      projected.copyWith(fragments: _fragmentsFromDocument(canonicalDocument)),
    ];
  }

  return <ArticlePageData>[
    ArticlePageData(
      id: 'page_0',
      title: postTitle.trim(),
      imageUrl: coverImage.trim(),
    ),
  ];
}

List<ArticleLayoutFragment> _fragmentsFromDocument(
  ArticleDocumentData document,
) {
  final fragments = <ArticleLayoutFragment>[];
  if (document.titleStyle != ArticleDocumentTitleStyle.none &&
      document.title.trim().isNotEmpty) {
    fragments.add(
      ArticleLayoutFragment(
        kind: ArticleLayoutFragmentKind.title,
        text: document.title.trim(),
        textStyleKey: 'title',
        binding: ArticlePageBinding(
          titleRange: ArticleTextRange(start: 0, end: document.title.length),
          insertOffset: 0,
        ),
      ),
    );
  }
  var bodyCursor = 0;
  for (final node in document.nodes) {
    if (node.isDocumentTitle) {
      continue;
    }
    switch (node.type) {
      case ArticleDocumentNodeType.documentTitle:
        break;
      case ArticleDocumentNodeType.headingMajor:
      case ArticleDocumentNodeType.headingMinor:
      case ArticleDocumentNodeType.orderedItem:
      case ArticleDocumentNodeType.bulletItem:
        fragments.add(
          ArticleLayoutFragment(
            kind: ArticleLayoutFragmentKind.semanticBlock,
            block: _blockFromNode(node, bodyCursor),
            text: node.text.trim(),
            textStyleKey: node.type == ArticleDocumentNodeType.headingMinor
                ? 'heading3'
                : node.type == ArticleDocumentNodeType.headingMajor
                ? 'heading2'
                : node.type == ArticleDocumentNodeType.orderedItem
                ? 'orderedItem'
                : 'bulletItem',
            textAlign: node.textAlign,
          ),
        );
        bodyCursor += node.text.length + 1;
        break;
      case ArticleDocumentNodeType.figure:
        final asset = ArticleDocumentAsset(
          id: node.assetId.trim().isNotEmpty ? node.assetId.trim() : node.id,
          offset: bodyCursor,
          imageUrl: node.imageUrl,
          imageLayout: node.imageLayout,
          caption: node.caption,
        );
        fragments.add(
          ArticleLayoutFragment(
            kind: asset.usesWrappedLayout
                ? ArticleLayoutFragmentKind.wrapContent
                : ArticleLayoutFragmentKind.fullWidthImage,
            asset: asset,
            textStyleKey: 'body',
          ),
        );
        break;
      case ArticleDocumentNodeType.paragraph:
        final text = node.text.trimRight();
        if (text.trim().isEmpty) {
          break;
        }
        fragments.add(
          ArticleLayoutFragment(
            kind: ArticleLayoutFragmentKind.semanticBlock,
            block: _blockFromNode(node, bodyCursor),
            text: text,
            textStyleKey: 'body',
            textAlign: node.textAlign,
          ),
        );
        bodyCursor += node.text.length + 1;
        break;
    }
  }
  return fragments;
}

ArticleDocumentBlock _blockFromNode(ArticleDocumentNode node, int offset) {
  return ArticleDocumentBlock(
    id: node.id,
    type: switch (node.type) {
      ArticleDocumentNodeType.headingMajor => ArticleDocumentBlockType.heading2,
      ArticleDocumentNodeType.headingMinor => ArticleDocumentBlockType.heading3,
      ArticleDocumentNodeType.orderedItem =>
        ArticleDocumentBlockType.orderedItem,
      ArticleDocumentNodeType.bulletItem => ArticleDocumentBlockType.bulletItem,
      _ => ArticleDocumentBlockType.paragraph,
    },
    offset: offset,
    text: node.text,
    textAlign: node.textAlign,
    listDepth: node.listDepth,
  );
}

List<ArticleContentBlockView> _projectArticleContentBlocksFromDocument(
  ArticleDocumentData document,
) {
  final bodyNodes = document.nodes
      .where((node) => !node.isDocumentTitle)
      .toList(growable: false);
  if (bodyNodes.isNotEmpty) {
    final blocks = <ArticleContentBlockView>[];
    var orderedIndex = 0;
    for (var index = 0; index < bodyNodes.length; index += 1) {
      final node = bodyNodes[index];
      final text = node.text.trim();
      switch (node.type) {
        case ArticleDocumentNodeType.headingMajor:
          orderedIndex = 0;
          if (text.isEmpty) {
            continue;
          }
          blocks.add(ArticleContentBlockView(type: 'heading_2', body: text));
          break;
        case ArticleDocumentNodeType.headingMinor:
          orderedIndex = 0;
          if (text.isEmpty) {
            continue;
          }
          blocks.add(ArticleContentBlockView(type: 'heading_3', body: text));
          break;
        case ArticleDocumentNodeType.orderedItem:
          if (text.isEmpty) {
            continue;
          }
          orderedIndex += 1;
          blocks.add(
            ArticleContentBlockView(
              type: 'ordered_item',
              body: text,
              orderedIndex: orderedIndex,
            ),
          );
          break;
        case ArticleDocumentNodeType.bulletItem:
          orderedIndex = 0;
          if (text.isEmpty) {
            continue;
          }
          blocks.add(ArticleContentBlockView(type: 'bullet_item', body: text));
          break;
        case ArticleDocumentNodeType.figure:
          orderedIndex = 0;
          if (!node.hasImage) {
            continue;
          }
          if (node.usesWrappedLayout) {
            ArticleDocumentNode? narrowParagraph;
            ArticleDocumentNode? belowParagraph;
            if (index + 1 < bodyNodes.length &&
                bodyNodes[index + 1].type ==
                    ArticleDocumentNodeType.paragraph) {
              narrowParagraph = bodyNodes[index + 1];
              index += 1;
              if (index + 1 < bodyNodes.length &&
                  bodyNodes[index + 1].type ==
                      ArticleDocumentNodeType.paragraph) {
                belowParagraph = bodyNodes[index + 1];
                index += 1;
              }
            }
            blocks.add(
              ArticleContentBlockView(
                type: 'wrapped_paragraph',
                body:
                    '${narrowParagraph?.text ?? ''}${belowParagraph?.text ?? ''}'
                        .trimRight(),
                leadingText: narrowParagraph?.text ?? '',
                trailingText: belowParagraph?.text ?? '',
                imageUrl: node.imageUrl,
                imageLayout: node.imageLayout,
                caption: node.caption,
              ),
            );
            continue;
          }
          blocks.add(
            ArticleContentBlockView(
              type: 'image',
              imageUrl: node.imageUrl,
              imageLayout: node.imageLayout,
              caption: node.caption,
            ),
          );
          break;
        case ArticleDocumentNodeType.paragraph:
          orderedIndex = 0;
          if (text.isEmpty) {
            continue;
          }
          blocks.add(ArticleContentBlockView(type: 'paragraph', body: text));
          break;
        case ArticleDocumentNodeType.documentTitle:
          break;
      }
    }
    if (blocks.isNotEmpty) {
      return blocks;
    }
  }

  final paragraphs = document.body
      .split('\n')
      .map((segment) => segment.trim())
      .where((segment) => segment.isNotEmpty)
      .map(
        (segment) => ArticleContentBlockView(type: 'paragraph', body: segment),
      )
      .toList(growable: false);
  if (paragraphs.isNotEmpty) {
    return paragraphs;
  }

  if (document.assets.isNotEmpty) {
    return document.assets
        .where((asset) => asset.hasImage)
        .map(
          (asset) => ArticleContentBlockView(
            type: 'image',
            imageUrl: asset.imageUrl,
            imageLayout: asset.imageLayout,
            caption: asset.caption,
          ),
        )
        .toList(growable: false);
  }

  return const <ArticleContentBlockView>[];
}

List<ArticleContentBlockView> _projectArticleContentBlocks({
  ArticleDocumentData? document,
}) {
  final canonicalDocument = document;
  if (canonicalDocument != null && !canonicalDocument.isEmpty) {
    final blocks = _projectArticleContentBlocksFromDocument(canonicalDocument);
    if (blocks.isNotEmpty) {
      return blocks;
    }
  }
  return const <ArticleContentBlockView>[];
}
