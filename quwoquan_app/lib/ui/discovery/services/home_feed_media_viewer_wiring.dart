import 'package:quwoquan_app/cloud/runtime/models/content_post_view_data.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';

/// 关注 Tab 沉浸查看器：canonical [ContentPostViewData] 是唯一输入，不再向
/// Repository 查询 alpha-only 展示扩展。
Map<String, MediaViewerPostWireRow> homeFollowingMediaViewerRaws({
  required List<ContentPostViewData> viewerPosts,
}) {
  return <String, MediaViewerPostWireRow>{
    for (final item in viewerPosts)
      item.id: MediaViewerPostWireRow.fromDynamicMap(
        Map<String, dynamic>.from(item.toPresentationMap()),
      ),
  };
}
