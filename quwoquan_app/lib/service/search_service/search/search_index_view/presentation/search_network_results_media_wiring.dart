import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/public/media_viewer_extra.dart';

/// 全局搜索网络结果 → 媒体查看器单行 raw（非 `*_page.dart`）。
Map<String, MediaViewerPostWireRow> searchNetworkSinglePostMediaRaws({
  required ContentPostViewData dto,
  required Map<String, Object?> wire,
}) {
  return <String, MediaViewerPostWireRow>{
    dto.id: MediaViewerPostWireRow.fromObjectEntries(wire),
  };
}
