/// 文章富渲染辅助类型：文档来源枚举 + 内容块视图。
///
/// 文章详情 / 沉浸阅读的富渲染载荷由 [ContentArticleRender]（content_surface_view.dart）
/// 承载，并经 `projectArticleDetailView` 投影；本文件只保留其依赖的结构化子类型，
/// 不再持有作者 / 统计 / 标题等公共字段（统一由 ContentSurfaceView 承载）。
///
/// 文章正文唯一真相源为 markdown：命中 markdown 即 [markdown]，否则 [empty]。
enum ArticleDetailDocumentSource { markdown, empty }

class ArticleContentBlockView {
  const ArticleContentBlockView({
    required this.type,
    this.title = '',
    this.body = '',
    this.leadingText = '',
    this.trailingText = '',
    this.imageUrl,
    this.caption,
    this.orderedIndex,
    this.imageLayout = 'fullWidth',
  });

  final String type; // paragraph | ordered_item | image | section
  final String title;
  final String body;
  final String leadingText;
  final String trailingText;
  final String? imageUrl;
  final String? caption;
  final int? orderedIndex;
  final String imageLayout; // fullWidth | wrapLeft | wrapRight
}
