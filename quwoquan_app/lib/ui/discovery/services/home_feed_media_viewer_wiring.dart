import 'package:quwoquan_app/cloud/runtime/generated/content/post_base_dto.dart';
import 'package:quwoquan_app/cloud/services/content/discovery_wire_lookup.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';

/// 关注 Tab 沉浸查看器：发现区 mock wire + DTO 合并（非 `*_page.dart`）。
Map<String, MediaViewerPostWireRow> homeFollowingMediaViewerRaws({
  required bool isMock,
  required List<PostBaseDto> viewerPosts,
}) {
  return <String, MediaViewerPostWireRow>{
    for (final item in viewerPosts)
      item.id: MediaViewerPostWireRow.fromDynamicMap(
        Map<String, dynamic>.from(
          prototypeDiscoveryWireRowForMock(isMock, item.id) ?? item.toMap(),
        ),
      ),
  };
}
