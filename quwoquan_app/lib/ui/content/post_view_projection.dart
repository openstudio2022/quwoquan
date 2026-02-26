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
  );
}
