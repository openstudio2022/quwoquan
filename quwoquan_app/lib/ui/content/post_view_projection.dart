import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_detail_payload.dart';
import 'package:quwoquan_app/core/media/content_media_url.dart';
import 'package:quwoquan_app/ui/content/article_detail_view.dart';
import 'package:quwoquan_app/ui/content/article_document_models.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/markdown/article_markdown_codec.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view.dart';

/// 自 [ContentRepository.getPost] 返回的 [ContentPostDetailPayload] 投射出文章富渲染载荷。
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
/// [ContentSurfaceViewMapper.fromDto] 同源承载，本投影只负责文档/分页/块/卡片。
ContentArticleRender projectArticleDetailView(
  Map<String, dynamic> raw, {
  required String fallbackArticleId,
}) {
  final dto = postBaseDtoFromMap(raw);
  final read = PostReadPresentation.fromPostBase(dto, wire: raw);
  final postTitle = read.title;
  final body = read.body;
  var images = dto.hasImages
      ? dto.mediaImageUrls.where((e) => e.isNotEmpty).toList(growable: false)
      : const <String>[];
  if (dto.isArticleLike && dto.mediaCoverUrl.isNotEmpty && images.isEmpty) {
    images = <String>[dto.mediaCoverUrl];
  }
  final coverFromDto = dto.mediaCoverUrl.isNotEmpty
      ? dto.mediaCoverUrl
      : (dto.primaryImageUrl.isNotEmpty ? dto.primaryImageUrl : '');
  final thumbnailFromDto = dto.mediaThumbnailUrl.isNotEmpty
      ? dto.mediaThumbnailUrl
      : dto.primaryVisualUrl;
  final rawCards = (raw[ArticleDetailWireKeys.cards] is List)
      ? List<Object?>.from(raw[ArticleDetailWireKeys.cards] as List)
      : const <Object?>[];
  final cards = rawCards
      .whereType<Map<String, dynamic>>()
      .map(
        (card) => ArticleCardView(
          title: card[ArticleCardWireKeys.title]?.toString() ?? '',
          body: card[ArticleCardWireKeys.body]?.toString() ?? '',
          layout: card[ArticleCardWireKeys.layout]?.toString() ?? 'full',
          imageUrl: resolveContentMediaUrl(
            card[ArticleCardWireKeys.imageUrl]?.toString(),
          ),
          caption: card[ArticleCardWireKeys.caption]?.toString(),
        ),
      )
      .where(
        (card) =>
            card.title.isNotEmpty ||
            card.body.isNotEmpty ||
            (card.imageUrl?.isNotEmpty ?? false),
      )
      .toList(growable: false);
  final coverImage = coverFromDto.isNotEmpty
      ? coverFromDto
      : (images.isNotEmpty
            ? images.first
            : (thumbnailFromDto.isNotEmpty ? thumbnailFromDto : ''));
  final documentSource = _resolveArticleDocumentSource(
    raw: raw,
    cards: cards,
    body: body,
  );
  final hasMarkdownDocument =
      documentSource == ArticleDetailDocumentSource.markdown;
  final seedPages = _projectArticlePages(
    raw: raw,
    postTitle: postTitle,
    body: body,
    coverImage: coverImage,
    cards: cards,
  );
  final document = _projectArticleDocument(
    raw: raw,
    postTitle: postTitle,
    pages: seedPages,
  );
  final contentBlocks = _projectArticleContentBlocks(
    raw: raw,
    body: body,
    cards: cards,
    document: hasMarkdownDocument ? document : null,
  );
  final pages = _projectArticlePages(
    raw: raw,
    postTitle: postTitle.trim().isNotEmpty ? postTitle : document.title,
    body: body,
    coverImage: coverImage,
    cards: cards,
    document: hasMarkdownDocument ? document : null,
  );

  return ContentArticleRender(
    contentHtml: body,
    layoutMode: images.length > 1 ? 'carousel' : 'hero',
    images: images,
    contentBlocks: contentBlocks,
    cards: cards,
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

ArticleDetailDocumentSource _resolveArticleDocumentSource({
  required Map<String, dynamic> raw,
  required List<ArticleCardView> cards,
  required String body,
}) {
  final markdown = raw[ArticleDetailWireKeys.articleMarkdown]?.toString() ?? '';
  if (markdown.trim().isNotEmpty) {
    return ArticleDetailDocumentSource.markdown;
  }
  final rawBlocks = raw[ArticleDetailWireKeys.articleBlocks];
  if (rawBlocks is List && rawBlocks.isNotEmpty) {
    return ArticleDetailDocumentSource.articleBlocks;
  }
  if (cards.isNotEmpty) {
    return ArticleDetailDocumentSource.cards;
  }
  if (body.trim().isNotEmpty) {
    return ArticleDetailDocumentSource.body;
  }
  return ArticleDetailDocumentSource.empty;
}

ArticleDocumentData _projectArticleDocument({
  required Map<String, dynamic> raw,
  required String postTitle,
  required List<ArticlePageData> pages,
}) {
  final markdown = raw[ArticleDetailWireKeys.articleMarkdown]?.toString() ?? '';
  if (markdown.trim().isNotEmpty) {
    return ArticleMarkdownCodec.parseDocument(
      markdown,
      assetManifest: _articleAssetManifestMap(raw),
    );
  }
  final rawBlocks =
      (raw[ArticleDetailWireKeys.articleBlocks] as List?) ?? const <Object?>[];
  if (rawBlocks.isNotEmpty) {
    final buffer = StringBuffer();
    final assets = <ArticleDocumentAsset>[];
    final blocks = <ArticleDocumentBlock>[];
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

    for (final entry in rawBlocks.whereType<Map>()) {
      final block = Map<String, dynamic>.from(entry);
      final type = (block[ArticleBlockWireKeys.type] ?? 'paragraph')
          .toString()
          .trim();
      final text = (block[ArticleBlockWireKeys.text] ?? '').toString();
      final imageUrl = resolveContentMediaUrl(
        (block[ArticleBlockWireKeys.imagePath] ??
                block[ArticleBlockWireKeys.imageUrl] ??
                '')
            .toString()
            .trim(),
      );
      final imageLayout =
          (block[ArticleBlockWireKeys.imageLayout] ?? 'fullWidth')
              .toString()
              .trim();
      switch (type) {
        case 'heading2':
          orderedIndex = 0;
          blocks.add(
            ArticleDocumentBlock(
              id:
                  (block[ArticleBlockWireKeys.id] ??
                          'heading2_${blocks.length}')
                      .toString(),
              type: ArticleDocumentBlockType.heading2,
              offset: buffer.length,
              text: text,
            ),
          );
          break;
        case 'heading3':
          orderedIndex = 0;
          blocks.add(
            ArticleDocumentBlock(
              id:
                  (block[ArticleBlockWireKeys.id] ??
                          'heading3_${blocks.length}')
                      .toString(),
              type: ArticleDocumentBlockType.heading3,
              offset: buffer.length,
              text: text,
            ),
          );
          break;
        case 'sectionTitle':
          orderedIndex = 0;
          blocks.add(
            ArticleDocumentBlock(
              id: (block[ArticleBlockWireKeys.id] ?? 'section_${blocks.length}')
                  .toString(),
              type: ArticleDocumentBlockType.sectionTitle,
              offset: buffer.length,
              text: text,
            ),
          );
          break;
        case 'orderedItem':
          orderedIndex += 1;
          appendLine(
            text.trim().isEmpty ? '' : '$orderedIndex. ${text.trim()}',
          );
          break;
        case 'bulletItem':
          orderedIndex = 0;
          appendLine(text.trim().isEmpty ? '' : '• ${text.trim()}');
          break;
        case 'image':
          orderedIndex = 0;
          if (imageUrl.isNotEmpty) {
            assets.add(
              ArticleDocumentAsset(
                id: 'asset_${assetSeed++}',
                offset: buffer.length,
                imageUrl: imageUrl,
                imageLayout: imageLayout,
                caption: (block[ArticleBlockWireKeys.caption] ?? '').toString(),
              ),
            );
          }
          break;
        case 'paragraph':
        default:
          orderedIndex = 0;
          appendLine(text);
          break;
      }
    }
    return ArticleDocumentData(
      title: postTitle.trim(),
      body: buffer.toString(),
      assets: assets,
      blocks: blocks,
      template:
          raw[ArticleDetailWireKeys.articleTemplate]?.toString() ?? 'gentle',
      fontPreset:
          raw[ArticleDetailWireKeys.articleFontPreset]?.toString() ?? 'clean',
      coverImageUrl: resolveContentMediaUrl(
        raw[ArticleDetailWireKeys.coverUrl]?.toString(),
      ),
    );
  }
  final buffer = StringBuffer();
  final assets = <ArticleDocumentAsset>[];
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
    final body = page.body.trim();
    if (body.isEmpty) {
      continue;
    }
    if (buffer.isNotEmpty) {
      buffer.write('\n');
    }
    buffer.write(body);
  }
  return ArticleDocumentData(
    title: pages.isNotEmpty && pages.first.title.trim().isNotEmpty
        ? pages.first.title
        : postTitle.trim(),
    body: buffer.toString(),
    assets: assets,
    template:
        raw[ArticleDetailWireKeys.articleTemplate]?.toString() ?? 'gentle',
    fontPreset:
        raw[ArticleDetailWireKeys.articleFontPreset]?.toString() ?? 'clean',
    coverImageUrl: resolveContentMediaUrl(
      raw[ArticleDetailWireKeys.coverUrl]?.toString(),
    ),
  );
}

List<ArticlePageData> _projectArticlePages({
  required Map<String, dynamic> raw,
  required String postTitle,
  required String body,
  required String coverImage,
  required List<ArticleCardView> cards,
  ArticleDocumentData? document,
}) {
  final rawPages =
      (raw[ArticleDetailWireKeys.articlePages] as List?) ?? const <Object?>[];
  if (rawPages.isNotEmpty) {
    final pages = rawPages
        .whereType<Map>()
        .map((entry) {
          final pageMap = Map<String, dynamic>.from(entry);
          return ArticlePageData.fromMap(pageMap).copyWith(
            imageUrl: resolveContentMediaUrl(
              pageMap['imageUrl']?.toString() ??
                  pageMap['imagePath']?.toString(),
            ),
          );
        })
        .where((page) => page.id.trim().isNotEmpty)
        .toList(growable: false);
    if (pages.isNotEmpty) {
      return <ArticlePageData>[
        pages.first.copyWith(
          title: pages.first.title.trim().isEmpty
              ? postTitle
              : pages.first.title,
          imageUrl: pages.first.imageUrl.trim().isEmpty
              ? coverImage
              : pages.first.imageUrl,
        ),
        ...pages.skip(1),
      ];
    }
  }

  final canonicalDocument = document;
  if (canonicalDocument != null && !canonicalDocument.isEmpty) {
    if (canonicalDocument.blocks.isNotEmpty ||
        canonicalDocument.body.trim().isNotEmpty ||
        canonicalDocument.title.trim().isNotEmpty ||
        coverImage.trim().isNotEmpty) {
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
        projected.copyWith(
          fragments: _fragmentsFromDocument(canonicalDocument),
        ),
      ];
    }
  }

  final rawBlocks =
      (raw[ArticleDetailWireKeys.articleBlocks] as List?) ?? const <Object?>[];
  if (rawBlocks.isNotEmpty) {
    final pages = <ArticlePageData>[];
    var current = ArticlePageData(id: 'page_0', title: postTitle.trim());
    var pageIndex = 1;
    var orderedIndex = 0;

    void flushCurrent() {
      if (current.title.trim().isEmpty &&
          current.body.trim().isEmpty &&
          current.imageUrl.trim().isEmpty) {
        return;
      }
      pages.add(current);
      current = ArticlePageData(id: 'page_$pageIndex');
      pageIndex += 1;
    }

    String appendText(String existing, String addition) {
      if (addition.trim().isEmpty) {
        return existing;
      }
      if (existing.trim().isEmpty) {
        return addition.trim();
      }
      return '$existing\n${addition.trim()}';
    }

    for (final entry in rawBlocks.whereType<Map>()) {
      final block = Map<String, dynamic>.from(entry);
      final type = (block[ArticleBlockWireKeys.type] ?? 'paragraph')
          .toString()
          .trim();
      final text = (block[ArticleBlockWireKeys.text] ?? '').toString().trim();
      final imagePath = resolveContentMediaUrl(
        (block[ArticleBlockWireKeys.imagePath] ?? '').toString().trim(),
      );
      final imageLayout =
          (block[ArticleBlockWireKeys.imageLayout] ?? 'fullWidth')
              .toString()
              .trim();
      switch (type) {
        case 'image':
          if (current.body.trim().isNotEmpty ||
              current.imageUrl.trim().isNotEmpty) {
            flushCurrent();
          }
          current = current.copyWith(
            imageUrl: imagePath,
            imageLayout: imageLayout,
          );
          orderedIndex = 0;
          break;
        case 'orderedItem':
          orderedIndex += 1;
          current = current.copyWith(
            body: appendText(current.body, '$orderedIndex. $text'),
          );
          break;
        case 'paragraph':
        default:
          orderedIndex = 0;
          current = current.copyWith(body: appendText(current.body, text));
          break;
      }
    }
    flushCurrent();
    if (pages.isNotEmpty) {
      final hasInlineImage = pages.any(
        (page) => page.imageUrl.trim().isNotEmpty,
      );
      return <ArticlePageData>[
        pages.first.copyWith(
          title: pages.first.title.trim().isEmpty
              ? postTitle.trim()
              : pages.first.title,
          imageUrl: !hasInlineImage && coverImage.trim().isNotEmpty
              ? coverImage.trim()
              : pages.first.imageUrl,
        ),
        ...pages.skip(1),
      ];
    }
  }

  final pages = <ArticlePageData>[];
  if (postTitle.trim().isNotEmpty ||
      body.trim().isNotEmpty ||
      coverImage.trim().isNotEmpty) {
    pages.add(
      ArticlePageData(
        id: 'page_0',
        title: postTitle.trim(),
        body: body.trim(),
        imageUrl: coverImage.trim(),
      ),
    );
  }

  for (var index = 0; index < cards.length; index += 1) {
    final card = cards[index];
    final usesWrap = card.layout == 'half' || card.layout == 'third';
    pages.add(
      ArticlePageData(
        id: 'card_page_$index',
        title: card.title,
        body: card.body,
        imageUrl: card.imageUrl ?? '',
        imageLayout: usesWrap
            ? (index.isOdd ? 'wrapRight' : 'wrapLeft')
            : 'fullWidth',
        caption: card.caption ?? '',
      ),
    );
  }

  if (pages.isNotEmpty) {
    return pages;
  }

  return <ArticlePageData>[
    ArticlePageData(id: 'page_0', title: postTitle.trim(), body: body.trim()),
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
        final start = bodyCursor;
        final end = bodyCursor + node.text.length;
        fragments.add(
          ArticleLayoutFragment(
            kind: ArticleLayoutFragmentKind.body,
            text: text,
            textStyleKey: 'body',
            binding: ArticlePageBinding(
              bodyRange: ArticleTextRange(start: start, end: end),
              insertOffset: end,
            ),
          ),
        );
        bodyCursor = end + 1;
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
  required Map<String, dynamic> raw,
  required String body,
  required List<ArticleCardView> cards,
  ArticleDocumentData? document,
}) {
  final canonicalDocument = document;
  if (canonicalDocument != null && !canonicalDocument.isEmpty) {
    final blocks = _projectArticleContentBlocksFromDocument(canonicalDocument);
    if (blocks.isNotEmpty) {
      return blocks;
    }
  }

  final rawBlocks =
      (raw[ArticleDetailWireKeys.articleBlocks] as List?) ?? const <Object?>[];
  if (rawBlocks.isNotEmpty) {
    final blocks = <ArticleContentBlockView>[];
    var orderedIndex = 0;
    final normalized = rawBlocks
        .whereType<Map>()
        .map((entry) => Map<String, dynamic>.from(entry))
        .toList(growable: false);
    for (var index = 0; index < normalized.length; index++) {
      final block = normalized[index];
      final type = (block[ArticleBlockWireKeys.type] ?? 'paragraph')
          .toString()
          .trim();
      final text = (block[ArticleBlockWireKeys.text] ?? '').toString().trim();
      final imageUrl = resolveContentMediaUrl(
        (block[ArticleBlockWireKeys.imagePath] ?? '').toString().trim(),
      );
      final imageLayout =
          (block[ArticleBlockWireKeys.imageLayout] ?? 'fullWidth')
              .toString()
              .trim();
      switch (type) {
        case 'heading2':
          orderedIndex = 0;
          if (text.isEmpty) {
            continue;
          }
          blocks.add(ArticleContentBlockView(type: 'heading_2', body: text));
          break;
        case 'heading3':
          orderedIndex = 0;
          if (text.isEmpty) {
            continue;
          }
          blocks.add(ArticleContentBlockView(type: 'heading_3', body: text));
          break;
        case 'sectionTitle':
          orderedIndex = 0;
          if (text.isEmpty) {
            continue;
          }
          blocks.add(
            ArticleContentBlockView(type: 'section_heading', body: text),
          );
          break;
        case 'orderedItem':
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
        case 'bulletItem':
          orderedIndex = 0;
          if (text.isEmpty) {
            continue;
          }
          blocks.add(ArticleContentBlockView(type: 'bullet_item', body: text));
          break;
        case 'image':
          orderedIndex = 0;
          if (imageUrl.isEmpty) {
            continue;
          }
          if ((imageLayout == 'wrapLeft' || imageLayout == 'wrapRight') &&
              index + 1 < normalized.length) {
            final next = normalized[index + 1];
            final nextType = (next[ArticleBlockWireKeys.type] ?? 'paragraph')
                .toString()
                .trim();
            final nextText = (next[ArticleBlockWireKeys.text] ?? '')
                .toString()
                .trim();
            if (nextType == 'paragraph' && nextText.isNotEmpty) {
              blocks.add(
                ArticleContentBlockView(
                  type: 'wrapped_paragraph',
                  body: nextText,
                  imageUrl: imageUrl,
                  imageLayout: imageLayout,
                ),
              );
              index += 1;
              continue;
            }
          }
          blocks.add(
            ArticleContentBlockView(
              type: 'image',
              imageUrl: imageUrl,
              imageLayout: imageLayout,
            ),
          );
          break;
        case 'paragraph':
        default:
          orderedIndex = 0;
          if (text.isEmpty) {
            continue;
          }
          blocks.add(ArticleContentBlockView(type: 'paragraph', body: text));
          break;
      }
    }
    if (blocks.isNotEmpty) {
      return blocks;
    }
  }

  if (cards.isNotEmpty) {
    return cards
        .map(
          (card) => ArticleContentBlockView(
            type: 'section',
            title: card.title,
            body: card.body,
            imageUrl: card.imageUrl,
            caption: card.caption,
            imageLayout: 'fullWidth',
          ),
        )
        .toList(growable: false);
  }

  if (body.trim().isNotEmpty) {
    return <ArticleContentBlockView>[
      ArticleContentBlockView(type: 'paragraph', body: body.trim()),
    ];
  }

  return const <ArticleContentBlockView>[];
}
