import 'package:quwoquan_app/runtime/config/offline_content_failure.dart';
import 'package:quwoquan_app/runtime/platform/media/bundled_media_asset.dart';

Future<String> materializeBundledVideo(BundledMediaAsset asset) async {
  throw const OfflineContentFailure('bundled_video_platform_unsupported', unavailable: true);
}
