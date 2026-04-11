import 'package:quwoquan_app/cloud/runtime/generated/content/post_base_dto.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/ui/circle/models/circle_hub_feed_post_entry.dart';

/// 首页圈子沉浸查看器：wire 行构建（非 `*_page.dart`，避免页面门禁 C 命中 `Map<String,dynamic>`）。
Map<String, MediaViewerPostWireRow> circleHubMediaViewerRawsByPostId(
  List<({CircleHubFeedPostEntry hubEntry, PostBaseDto dto})> viewerEntries,
) {
  return <String, MediaViewerPostWireRow>{
    for (final e in viewerEntries)
      e.dto.id: MediaViewerPostWireRow.fromDynamicMap(
        Map<String, dynamic>.from(e.hubEntry.raw),
      ),
  };
}
