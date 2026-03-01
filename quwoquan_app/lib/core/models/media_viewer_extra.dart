import 'package:quwoquan_app/ui/content/post_summary_view.dart';

/// 媒体查看器路由传参：列表、浏览器、作者详情共享同一 feed
class MediaViewerExtra {
  const MediaViewerExtra({
    required this.posts,
    required this.initialIndex,
    required this.category,
    this.initialImageIndex = 0,
  });

  final List<PostSummaryView> posts;
  final int initialIndex; // post index for moment, image index for photo
  final String category; // 'photo' | 'video' | 'moment'
  /// 同微趣内图片索引（nested 模式使用，默认为 0）
  final int initialImageIndex;
}
