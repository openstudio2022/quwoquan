import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/ui/content/article_detail_view.dart';
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
  );
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
