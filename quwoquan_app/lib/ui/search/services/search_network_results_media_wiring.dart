import 'package:quwoquan_app/cloud/runtime/generated/content/post_base_dto.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';

/// 全局搜索网络结果 → 媒体查看器单行 raw（非 `*_page.dart`）。
Map<String, MediaViewerPostWireRow> searchNetworkSinglePostMediaRaws({
  required PostBaseDto dto,
  required Map<String, dynamic> wire,
}) {
  return <String, MediaViewerPostWireRow>{
    dto.id: MediaViewerPostWireRow.fromDynamicMap(
      Map<String, dynamic>.from(wire),
    ),
  };
}
