import 'package:quwoquan_app/ui/content/article_presentation_models.dart';

/// 文章详情投射视图 — 由 projectArticleDetailView 生成，供 ArticleDetailPage 消费。
///
/// 取代原来从 `Map<String, dynamic>` 中 article['stats']['likes']、
/// article['author']['name'] 等写死字符串访问。
class ArticleDetailView {
  const ArticleDetailView({
    required this.id,
    required this.title,
    required this.description,
    required this.contentHtml,
    required this.date,
    required this.author,
    required this.layoutMode,
    required this.coverImage,
    required this.images,
    required this.stats,
    required this.contentBlocks,
    required this.cards,
    required this.pages,
    required this.template,
    required this.fontPreset,
  });

  final String id;
  final String title;
  final String description;
  final String contentHtml;
  final String date;
  final ArticleAuthorView author;

  /// 'hero'（单图）或 'carousel'（多图）
  final String layoutMode;
  final String coverImage;
  final List<String> images;
  final ArticleStatsView stats;
  final List<ArticleContentBlockView> contentBlocks;
  final List<ArticleCardView> cards;
  final List<ArticlePageData> pages;
  final ArticleTemplatePreset template;
  final ArticleFontPreset fontPreset;
}

class ArticleAuthorView {
  const ArticleAuthorView({
    required this.name,
    required this.avatar,
    required this.isOfficial,
    this.badge,
  });

  final String name;
  final String avatar;
  final bool isOfficial;
  final String? badge;
}

class ArticleStatsView {
  const ArticleStatsView({
    required this.likes,
    required this.comments,
    required this.bookmarks,
  });

  final int likes;
  final int comments;
  final int bookmarks;
}

class ArticleCardView {
  const ArticleCardView({
    required this.title,
    required this.body,
    required this.layout,
    this.imageUrl,
    this.caption,
  });

  final String title;
  final String body;
  final String layout; // full | half | third
  final String? imageUrl;
  final String? caption;
}

class ArticleContentBlockView {
  const ArticleContentBlockView({
    required this.type,
    this.title = '',
    this.body = '',
    this.imageUrl,
    this.caption,
    this.orderedIndex,
    this.imageLayout = 'fullWidth',
  });

  final String type; // paragraph | ordered_item | image | section
  final String title;
  final String body;
  final String? imageUrl;
  final String? caption;
  final int? orderedIndex;
  final String imageLayout; // fullWidth | wrapLeft | wrapRight
}
