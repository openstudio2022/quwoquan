import 'package:quwoquan_app/cloud/runtime/generated/content/post_base_dto.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';

/// 关注 Tab 沉浸查看器：由 [ContentRepository] 提供可选 wire 扩展并与 DTO 合并。
Map<String, MediaViewerPostWireRow> homeFollowingMediaViewerRaws({
  required ContentRepository content,
  required List<PostBaseDto> viewerPosts,
}) {
  return <String, MediaViewerPostWireRow>{
    for (final item in viewerPosts)
      item.id: MediaViewerPostWireRow.fromDynamicMap(
        Map<String, dynamic>.from(
          content.discoveryPresentationWireForPost(item.id) ?? item.toMap(),
        ),
      ),
  };
}
