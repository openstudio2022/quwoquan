import 'dart:async';

import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/content_media_upload_service.dart';
import 'package:quwoquan_app/runtime/errors/generated/content/content_errors.g.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ContentMediaCoverCommand = Future<MediaCoverSelectionResult> Function();

/// Retries one idempotent cover command while processing is pending or its
/// completion races the cover write. The caller persists one command context.
Future<MediaCoverSelectionResult> selectContentMediaCoverWhenReady({
  required ContentMediaCoverCommand command,
  ContentMediaUploadCancellationSignal? cancellationSignal,
  Duration retryDelay = const Duration(seconds: 3),
  int maxAttempts = 100,
  Future<void> Function(Duration delay)? wait,
}) async {
  if (maxAttempts <= 0) {
    throw ArgumentError.value(maxAttempts, 'maxAttempts', 'must be positive');
  }
  final sleeper = wait ?? Future<void>.delayed;
  for (var attempt = 1; attempt <= maxAttempts; attempt++) {
    cancellationSignal?.throwIfCancelled();
    try {
      return await command();
    } on CloudException catch (error) {
      final retryableWorkerRace =
          error.code == ContentErrorCode.mediaNotReady.code ||
          error.code == ContentErrorCode.versionConflict.code;
      if (!retryableWorkerRace || attempt == maxAttempts) {
        rethrow;
      }
      if (cancellationSignal == null) {
        await sleeper(error.retryAfter ?? retryDelay);
      } else {
        await cancellationSignal.waitOrCancel(error.retryAfter ?? retryDelay);
      }
    }
  }
  throw StateError('unreachable media cover retry state');
}
