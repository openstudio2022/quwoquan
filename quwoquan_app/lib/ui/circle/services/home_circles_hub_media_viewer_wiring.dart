import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/ui/circle/models/circle_hub_feed_post_entry.dart';

/// 首页圈子沉浸查看器：从强类型页面模型构建旧沉浸器边界对象。
Map<String, MediaViewerPostWireRow> circleHubMediaViewerRowsByPostId(
  Iterable<CircleHubFeedPostEntry> viewerEntries,
) {
  return <String, MediaViewerPostWireRow>{
    for (final entry in viewerEntries)
      entry.postId: entry.toMediaViewerWireRow(),
  };
}
