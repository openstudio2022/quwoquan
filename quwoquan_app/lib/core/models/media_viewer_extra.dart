import 'package:quwoquan_app/ui/content/post_summary_view.dart';

/// 媒体查看器路由传参：列表、浏览器、作者详情共享同一 feed
class MediaViewerExtra {
  const MediaViewerExtra({
    required this.posts,
    required this.initialIndex,
    required this.category,
  });

  final List<PostSummaryView> posts;
  final int initialIndex;
  final String category; // 'photo' | 'video'
}
