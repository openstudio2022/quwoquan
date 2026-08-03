import 'package:quwoquan_app/cloud/runtime/models/content_post_view_data.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';

/// 全局搜索网络结果 → 媒体查看器单行 raw（非 `*_page.dart`）。
Map<String, MediaViewerPostWireRow> searchNetworkSinglePostMediaRaws({
  required ContentPostViewData dto,
  required Map<String, Object?> wire,
}) {
  return <String, MediaViewerPostWireRow>{
    dto.id: MediaViewerPostWireRow.fromObjectEntries(wire),
  };
}
