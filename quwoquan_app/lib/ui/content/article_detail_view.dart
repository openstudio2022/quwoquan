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
