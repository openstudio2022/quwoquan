import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:quwoquan_app/application/content/media/video_preview_track_query.dart';
import 'package:quwoquan_app/cloud/remote/content/media/video_preview_track_remote.dart';
import 'package:quwoquan_app/core/di/cloud_http_client_provider.dart';
import 'package:quwoquan_app/core/media/media_delivery_reference.dart';

final videoPreviewTrackQueryProvider = Provider<VideoPreviewTrackQuery>((ref) {
  return RemoteVideoPreviewTrackQuery(
    httpClient: ref.watch(unauthenticatedCloudHttpClientProvider),
    mediaDeliveryResolver: MediaDeliveryResolver.fromRuntimeConfig(),
  );
});
