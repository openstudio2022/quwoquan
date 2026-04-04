import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/ui/content/article_detail_view.dart';
import 'package:quwoquan_app/ui/content/article_document_models.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/post_summary_view.dart';

/// 统一投射入口：raw post map → [PostSummaryView]（DTO 驱动，无写死字段名）
///
/// 所有 mock / remote 数据均通过此函数归一化，下游 UI 消费 [PostSummaryView] 强类型字段。
PostSummaryView projectPostMap(Map<String, dynamic> raw) {
  final dto = postBaseDtoFromMap(raw);
  return PostSummaryView.fromDto(dto);
}

/// 文章详情投射：raw post map → [ArticleDetailView]（供 ArticleDetailPage 消费）
ArticleDetailView projectArticleDetailView(
  Map<String, dynamic> raw, {
  required String fallbackArticleId,
}) {
  final post = projectPostMap(raw);
  final images = (post.images ?? const <String>[])
      .where((e) => e.isNotEmpty)
      .toList(growable: false);
  final body = post.body ?? '';
  final rawCards = (raw['cards'] is List)
      ? (raw['cards'] as List<dynamic>)
      : const <dynamic>[];
  final cards = rawCards
      .whereType<Map<String, dynamic>>()
      .map(
        (card) => ArticleCardView(
          title: card['title']?.toString() ?? '',
          body: card['body']?.toString() ?? '',
          layout: card['layout']?.toString() ?? 'full',
          imageUrl: card['imageUrl']?.toString(),
          caption: card['caption']?.toString(),
        ),
      )
      .where(
        (card) =>
            card.title.isNotEmpty ||
            card.body.isNotEmpty ||
            (card.imageUrl?.isNotEmpty ?? false),
      )
      .toList(growable: false);
  final coverImage = post.coverUrl?.isNotEmpty == true
      ? post.coverUrl!
      : (images.isNotEmpty
            ? images.first
            : (post.thumbnailUrl?.isNotEmpty == true
                  ? post.thumbnailUrl!
                  : ''));
  final documentSource = _resolveArticleDocumentSource(
    raw: raw,
    cards: cards,
    body: body,
  );
  final hasExplicitArticleDocument =
      documentSource == ArticleDetailDocumentSource.articleDocument;
  final seedPages = _projectArticlePages(
    raw: raw,
    postTitle: post.title ?? '',
    body: body,
    coverImage: coverImage,
    cards: cards,
  );
  final document = _projectArticleDocument(
    raw: raw,
    postTitle: post.title ?? '',
    pages: seedPages,
  );
  final contentBlocks = _projectArticleContentBlocks(
    raw: raw,
    body: body,
    cards: cards,
    document: hasExplicitArticleDocument ? document : null,
  );
  final pages = _projectArticlePages(
    raw: raw,
    postTitle: (post.title ?? '').trim().isNotEmpty
        ? post.title ?? ''
        : document.title,
    body: body,
    coverImage: coverImage,
    cards: cards,
    document: hasExplicitArticleDocument ? document : null,
  );
  final preferDocumentText =
      documentSource != ArticleDetailDocumentSource.body &&
      documentSource != ArticleDetailDocumentSource.empty;
  final resolvedTitle = preferDocumentText
      ? (document.title.trim().isNotEmpty
            ? document.title.trim()
            : (post.title ?? '').trim())
      : ((post.title ?? '').trim().isNotEmpty
            ? (post.title ?? '').trim()
            : document.title.trim());
  final resolvedBody = preferDocumentText
      ? (document.body.trim().isNotEmpty ? document.body.trim() : body)
      : (body.trim().isNotEmpty ? body : document.body.trim());

  return ArticleDetailView(
    id: post.id.isNotEmpty ? post.id : fallbackArticleId,
    title: resolvedTitle,
    description: resolvedBody,
    contentHtml: resolvedBody,
    date: post.createdAt,
    author: ArticleAuthorView(
      name: post.displayName,
      avatar: post.avatarUrl,
      isOfficial: raw['isOfficial'] == true,
      badge: raw['badge']?.toString(),
    ),
    layoutMode: images.length > 1 ? 'carousel' : 'hero',
    coverImage: coverImage,
    images: images,
    stats: ArticleStatsView(
      likes: post.likesCount,
      comments: post.commentsCount,
      bookmarks: post.savesCount,
    ),
    contentBlocks: contentBlocks,
    cards: cards,
    document: document,
    pages: pages,
    template: articleTemplatePresetFromString(
      raw['articleTemplate']?.toString(),
    ),
    fontPreset: articleFontPresetFromString(
      raw['articleFontPreset']?.toString(),
    ),
    documentSource: documentSource,
  );
}

ArticleDetailDocumentSource _resolveArticleDocumentSource({
  required Map<String, dynamic> raw,
  required List<ArticleCardView> cards,
  required String body,
}) {
  final rawDocument = raw['articleDocument'];
  if (rawDocument is Map && rawDocument.isNotEmpty) {
    return ArticleDetailDocumentSource.articleDocument;
  }
  final rawBlocks = raw['articleBlocks'];
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
  final rawDocument = Map<String, dynamic>.from(
    raw['articleDocument'] as Map? ?? const <String, dynamic>{},
  );
  if (rawDocument.isNotEmpty) {
    return ArticleDocumentData.fromMap(rawDocument);
  }
  final rawBlocks = (raw['articleBlocks'] as List?) ?? const <dynamic>[];
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
      final type = (block['type'] ?? 'paragraph').toString().trim();
      final text = (block['text'] ?? '').toString();
      final imageUrl = (block['imagePath'] ?? block['imageUrl'] ?? '')
          .toString()
          .trim();
      final imageLayout = (block['imageLayout'] ?? 'fullWidth')
          .toString()
          .trim();
      switch (type) {
        case 'heading2':
          orderedIndex = 0;
          blocks.add(
            ArticleDocumentBlock(
              id: (block['id'] ?? 'heading2_${blocks.length}').toString(),
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
              id: (block['id'] ?? 'heading3_${blocks.length}').toString(),
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
              id: (block['id'] ?? 'section_${blocks.length}').toString(),
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
                caption: (block['caption'] ?? '').toString(),
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
      template: raw['articleTemplate']?.toString() ?? 'gentle',
      fontPreset: raw['articleFontPreset']?.toString() ?? 'clean',
      coverImageUrl: raw['coverUrl']?.toString() ?? '',
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
    template: raw['articleTemplate']?.toString() ?? 'gentle',
    fontPreset: raw['articleFontPreset']?.toString() ?? 'clean',
    coverImageUrl: raw['coverUrl']?.toString() ?? '',
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
  final rawPages = (raw['articlePages'] as List?) ?? const <dynamic>[];
  if (rawPages.isNotEmpty) {
    final pages = rawPages
        .whereType<Map>()
        .map(
          (entry) => ArticlePageData.fromMap(Map<String, dynamic>.from(entry)),
        )
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
      return <ArticlePageData>[
        ArticlePageData(
          id: 'page_0',
          title: canonicalDocument.title.trim().isNotEmpty
              ? canonicalDocument.title.trim()
              : postTitle.trim(),
          body: canonicalDocument.body.trim(),
          imageUrl: coverImage.trim(),
          contentBlocks: canonicalDocument.blocks,
        ),
      ];
    }
  }

  final rawBlocks = (raw['articleBlocks'] as List?) ?? const <dynamic>[];
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
      final type = (block['type'] ?? 'paragraph').toString().trim();
      final text = (block['text'] ?? '').toString().trim();
      final imagePath = (block['imagePath'] ?? '').toString().trim();
      final imageLayout = (block['imageLayout'] ?? 'fullWidth')
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

List<ArticleContentBlockView> _projectArticleContentBlocksFromDocument(
  ArticleDocumentData document,
) {
  if (document.contentBlocks.isNotEmpty) {
    final blocks = <ArticleContentBlockView>[];
    var orderedIndex = 0;
    final normalized = document.contentBlocks;
    for (var index = 0; index < normalized.length; index++) {
      final block = normalized[index];
      final text = block.text.trim();
      switch (block.type) {
        case ArticleDocumentBlockType.heading2:
          orderedIndex = 0;
          if (text.isEmpty) {
            continue;
          }
          blocks.add(ArticleContentBlockView(type: 'heading_2', body: text));
          break;
        case ArticleDocumentBlockType.heading3:
          orderedIndex = 0;
          if (text.isEmpty) {
            continue;
          }
          blocks.add(ArticleContentBlockView(type: 'heading_3', body: text));
          break;
        case ArticleDocumentBlockType.sectionTitle:
          orderedIndex = 0;
          if (text.isEmpty) {
            continue;
          }
          blocks.add(
            ArticleContentBlockView(type: 'section_heading', body: text),
          );
          break;
        case ArticleDocumentBlockType.orderedItem:
          if (text.isEmpty) {
            continue;
          }
          orderedIndex = block.orderedIndex ?? (orderedIndex + 1);
          blocks.add(
            ArticleContentBlockView(
              type: 'ordered_item',
              body: text,
              orderedIndex: orderedIndex,
            ),
          );
          break;
        case ArticleDocumentBlockType.bulletItem:
          orderedIndex = 0;
          if (text.isEmpty) {
            continue;
          }
          blocks.add(ArticleContentBlockView(type: 'bullet_item', body: text));
          break;
        case ArticleDocumentBlockType.image:
          orderedIndex = 0;
          if (!block.hasImage) {
            continue;
          }
          if (block.usesWrappedLayout && index + 1 < normalized.length) {
            final next = normalized[index + 1];
            if (next.type == ArticleDocumentBlockType.paragraph &&
                next.text.trim().isNotEmpty) {
              blocks.add(
                ArticleContentBlockView(
                  type: 'wrapped_paragraph',
                  body: next.text.trim(),
                  imageUrl: block.imageUrl,
                  imageLayout: block.imageLayout,
                ),
              );
              index += 1;
              continue;
            }
          }
          blocks.add(
            ArticleContentBlockView(
              type: 'image',
              imageUrl: block.imageUrl,
              imageLayout: block.imageLayout,
              caption: block.caption,
            ),
          );
          break;
        case ArticleDocumentBlockType.paragraph:
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

  final rawBlocks = (raw['articleBlocks'] as List?) ?? const <dynamic>[];
  if (rawBlocks.isNotEmpty) {
    final blocks = <ArticleContentBlockView>[];
    var orderedIndex = 0;
    final normalized = rawBlocks
        .whereType<Map>()
        .map((entry) => Map<String, dynamic>.from(entry))
        .toList(growable: false);
    for (var index = 0; index < normalized.length; index++) {
      final block = normalized[index];
      final type = (block['type'] ?? 'paragraph').toString().trim();
      final text = (block['text'] ?? '').toString().trim();
      final imageUrl = (block['imagePath'] ?? '').toString().trim();
      final imageLayout = (block['imageLayout'] ?? 'fullWidth')
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
            final nextType = (next['type'] ?? 'paragraph').toString().trim();
            final nextText = (next['text'] ?? '').toString().trim();
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
