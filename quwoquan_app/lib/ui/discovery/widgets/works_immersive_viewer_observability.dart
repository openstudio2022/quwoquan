import 'package:quwoquan_app/cloud/runtime/models/content_post_view_data.dart';
import 'package:quwoquan_app/core/trackers/content_engagement_tracker.dart'
    show ContentType;
import 'package:quwoquan_app/ui/content/models/article_detail_view.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/host/article_read_only_book_deck.dart'
    show ArticleReaderFallbackReason;

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

  static String fallbackReasonName(ArticleReaderFallbackReason reason) {
    return switch (reason) {
      ArticleReaderFallbackReason.forcedDegradedPager =>
        'forced_degraded_pager',
      ArticleReaderFallbackReason.pageCurlDisabled => 'page_curl_disabled',
      ArticleReaderFallbackReason.accessibilityDisableAnimations =>
        'accessibility_disable_animations',
      ArticleReaderFallbackReason.longDocument => 'long_document',
    };
  }

  static ContentType contentTypeForPost(ContentPostViewData post) {
    final format = post.displayFormat;
    if (format == 'video') return ContentType.video;
    if (format == 'article') return ContentType.article;
    if (post.type == 'micro') return ContentType.micro;
    return ContentType.image;
  }
}
