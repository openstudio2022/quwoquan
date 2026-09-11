import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/video_preview_track_query.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/adapters/video_preview_track_remote.dart';
import 'package:quwoquan_app/runtime/di/public_media_delivery_dependencies.dart';
import 'package:quwoquan_app/runtime/di/ops_event_dependencies.dart';

final videoPreviewTrackQueryProvider = Provider<VideoPreviewTrackQuery>((ref) {
  return RemoteVideoPreviewTrackQuery(
    mediaDelivery: ref.watch(publicMediaDeliveryProvider),
    telemetry: ref.watch(appTelemetryReporterProvider),
  );
});
