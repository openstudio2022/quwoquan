import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:quwoquan_app/service/content_service/media/media_asset/application/video_preview_track_query.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/adapters/video_preview_track_remote.dart';
import 'package:quwoquan_app/runtime/di/cloud_http_client_provider.dart';
import 'package:quwoquan_app/runtime/di/ops_event_dependencies.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';

final videoPreviewTrackQueryProvider = Provider<VideoPreviewTrackQuery>((ref) {
  final endpointConfig = ref.watch(mediaEndpointConfigProvider);
  if (endpointConfig == null) {
    throw StateError('视频预览轨缺少 package-bound media endpoint config');
  }
  return RemoteVideoPreviewTrackQuery(
    httpClient: ref.watch(unauthenticatedCloudHttpClientProvider),
    mediaDeliveryResolver: MediaDeliveryResolver(endpointConfig),
    telemetry: ref.watch(appTelemetryReporterProvider),
  );
});
