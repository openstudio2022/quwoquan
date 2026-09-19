import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/video_preview_track_query.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/adapters/video_preview_track_remote.dart';
import 'package:quwoquan_app/runtime/di/public_media_delivery_dependencies.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_app/runtime/di/ops_event_dependencies.dart';

VideoPreviewTrackQuery? _installedQuery;
String? _installedIdentity;

void installVideoPreviewTrackQuery(VideoPreviewTrackQuery query) {
  _installedQuery = query;
  _installedIdentity = CloudRuntimeConfig.runtimeConfigPackageDigest;
}

final videoPreviewTrackQueryProvider = Provider<VideoPreviewTrackQuery>((ref) {
  if (_installedQuery != null &&
      _installedIdentity == CloudRuntimeConfig.runtimeConfigPackageDigest) {
    return _installedQuery!;
  }
  final endpointConfig = ref.watch(mediaEndpointConfigProvider);
  if (endpointConfig == null) {
    throw StateError('视频预览轨缺少 package-bound media endpoint config');
  }
  return RemoteVideoPreviewTrackQuery(
    mediaDelivery: ref.watch(publicMediaDeliveryProvider),
    telemetry: ref.watch(appTelemetryReporterProvider),
  );
});
