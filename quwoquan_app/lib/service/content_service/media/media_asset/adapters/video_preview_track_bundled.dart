import 'package:quwoquan_app/runtime/errors/content_capability_unavailable.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/video_preview_track_query.dart';

/// 当前制品快照提供完整视频，但不包含服务端 storyboard 预览轨。
/// 显式拒绝增强能力；不请求网络，也不影响播放器与 seek 主链。
final class BundledVideoPreviewTrackQuery implements VideoPreviewTrackQuery {
  const BundledVideoPreviewTrackQuery();

  @override
  Future<VideoPreviewTrackManifest> loadManifest(
    VideoPreviewTrackDescriptor descriptor,
  ) async {
    throw contentCapabilityUnavailable('video_preview_track');
  }
}
