import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show ContentType;
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_detail_view.dart';

/// 沉浸式浏览器观测属性的稳定命名。
final class WorksImmersiveViewerObservability {
  const WorksImmersiveViewerObservability._();

  static String documentSourceName(ArticleDetailDocumentSource source) {
    return switch (source) {
      ArticleDetailDocumentSource.markdown => 'markdown',
      ArticleDetailDocumentSource.empty => 'empty',
    };
  }

  static String immersiveChannelId(String source) {
    final normalized = source.trim().toLowerCase();
    return switch (normalized) {
      'featured' ||
      'premium' ||
      'premium_stream' ||
      'immersive' => 'premium_stream',
      _ => normalized.isEmpty ? 'premium_stream' : normalized,
    };
  }

  static String fallbackReasonName(String reason) => reason;

  static ContentType contentTypeForPost(ContentPostViewData post) {
    final format = post.displayFormat;
    if (format == 'video') return ContentType.video;
    if (format == 'article') return ContentType.article;
    if (post.type == 'micro') return ContentType.micro;
    return ContentType.image;
  }
}
