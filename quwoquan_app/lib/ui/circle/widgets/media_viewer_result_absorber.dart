import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/ui/circle/models/circle_hub_feed_post_entry.dart';

/// 兼容仍持有 `List<Map>` 的夹具 / 旧调用方：内部经 [CircleHubFeedPostEntry] 写回，与 UI 路径一致。
List<Map<String, dynamic>> applyMediaViewerResultToFeedItems(
  List<Map<String, dynamic>> items,
  MediaViewerResult result,
) {
  final entries =
      items.map(CircleHubFeedPostEntry.fromMap).toList(growable: false);
  CircleHubFeedPostEntry.applyResultToList(entries, result);
  return entries.map((e) => e.raw).toList(growable: false);
}
