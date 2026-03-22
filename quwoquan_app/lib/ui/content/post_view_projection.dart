import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/ui/content/article_detail_view.dart';
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
  final contentBlocks = _projectArticleContentBlocks(
    raw: raw,
    body: body,
    cards: cards,
  );
  final pages = _projectArticlePages(
    raw: raw,
    postTitle: post.title ?? '',
    body: body,
    coverImage: post.coverUrl?.isNotEmpty == true
        ? post.coverUrl!
        : (post.thumbnailUrl?.isNotEmpty == true
            ? post.thumbnailUrl!
            : (images.isNotEmpty ? images.first : '')),
    cards: cards,
  );

  return ArticleDetailView(
    id: post.id.isNotEmpty ? post.id : fallbackArticleId,
    title: post.title ?? '',
    description: body,
    contentHtml: body,
    date: post.createdAt,
    author: ArticleAuthorView(
      name: post.displayName,
      avatar: post.avatarUrl,
      isOfficial: raw['isOfficial'] == true,
      badge: raw['badge']?.toString(),
    ),
    layoutMode: images.length > 1 ? 'carousel' : 'hero',
    coverImage: post.coverUrl?.isNotEmpty == true
        ? post.coverUrl!
        : (post.thumbnailUrl?.isNotEmpty == true
            ? post.thumbnailUrl!
            : (images.isNotEmpty ? images.first : '')),
    images: images,
    stats: ArticleStatsView(
      likes: post.likesCount,
      comments: post.commentsCount,
      bookmarks: post.savesCount,
    ),
    contentBlocks: contentBlocks,
    cards: cards,
    pages: pages,
    template: articleTemplatePresetFromString(raw['articleTemplate']?.toString()),
    fontPreset: articleFontPresetFromString(
      raw['articleFontPreset']?.toString(),
    ),
  );
}

List<ArticlePageData> _projectArticlePages({
  required Map<String, dynamic> raw,
  required String postTitle,
  required String body,
  required String coverImage,
  required List<ArticleCardView> cards,
}) {
  final rawPages = (raw['articlePages'] as List?) ?? const <dynamic>[];
  if (rawPages.isNotEmpty) {
    final pages = rawPages
        .whereType<Map>()
        .map((entry) => ArticlePageData.fromMap(Map<String, dynamic>.from(entry)))
        .where((page) => page.id.trim().isNotEmpty)
        .toList(growable: false);
    if (pages.isNotEmpty) {
      return <ArticlePageData>[
        pages.first.copyWith(
          title: pages.first.title.trim().isEmpty ? postTitle : pages.first.title,
          imageUrl: pages.first.imageUrl.trim().isEmpty
              ? coverImage
              : pages.first.imageUrl,
        ),
        ...pages.skip(1),
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
      final imageLayout = (block['imageLayout'] ?? 'fullWidth').toString().trim();
      switch (type) {
        case 'image':
          if (current.body.trim().isNotEmpty || current.imageUrl.trim().isNotEmpty) {
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
      final hasInlineImage = pages.any((page) => page.imageUrl.trim().isNotEmpty);
      return <ArticlePageData>[
        pages.first.copyWith(
          title: pages.first.title.trim().isEmpty ? postTitle.trim() : pages.first.title,
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

List<ArticleContentBlockView> _projectArticleContentBlocks({
  required Map<String, dynamic> raw,
  required String body,
  required List<ArticleCardView> cards,
}) {
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
          blocks.add(
            ArticleContentBlockView(
              type: 'paragraph',
              body: text,
            ),
          );
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
      ArticleContentBlockView(
        type: 'paragraph',
        body: body.trim(),
      ),
    ];
  }

  return const <ArticleContentBlockView>[];
}
