import 'dart:async';

import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/local_video_playability.dart';
import 'package:quwoquan_app/runtime/platform/local_file_stat.dart';
import 'package:quwoquan_app/runtime/platform/video_player_controller_factory.dart';
import 'package:video_player/video_player.dart';

typedef LocalVideoControllerFactory =
    VideoPlayerController Function(String path);
typedef LocalVideoPlayableWaiter = Future<void> Function(String path);

final class DefaultLocalVideoPlayability implements LocalVideoPlayability {
  const DefaultLocalVideoPlayability({this.waiter = waitForLocalVideoPlayable});

  final LocalVideoPlayableWaiter waiter;

  @override
  Future<void> waitUntilPlayable(String path) => waiter(path);
}

int _attemptCount(Duration timeout, Duration interval) {
  final intervalMs = interval.inMilliseconds <= 0 ? 1 : interval.inMilliseconds;
  if (timeout.inMilliseconds <= 0) {
    return 1;
  }
  return ((timeout.inMilliseconds + intervalMs - 1) ~/ intervalMs).clamp(
    1,
    9999,
  );
}

Future<bool> waitForLocalVideoFileReady(
  String path, {
  Duration timeout = const Duration(seconds: 5),
  Duration pollInterval = const Duration(milliseconds: 120),
  int stablePolls = 1,
}) async {
  final normalized = path.trim();
  if (normalized.isEmpty) {
    return false;
  }
  final maxAttempts = _attemptCount(timeout, pollInterval);
  int? lastKnownLength;
  var stableCount = 0;
  for (var attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      final stat = await readLocalFileStat(normalized);
      if (stat.exists) {
        if (stat.length > 0) {
          if (lastKnownLength == stat.length) {
            stableCount += 1;
          } else {
            stableCount = 0;
            lastKnownLength = stat.length;
          }
          if (stableCount >= stablePolls) {
            return true;
          }
        }
      }
    } catch (_) {
      // 文件仍在落盘或系统尚未释放句柄时，继续轮询直到超时。
    }
    if (attempt < maxAttempts - 1) {
      await Future<void>.delayed(pollInterval);
    }
  }
  try {
    final stat = await readLocalFileStat(normalized);
    return stat.exists && stat.length > 0;
  } catch (_) {
    return false;
  }
}

Future<VideoPlayerController> createInitializedLocalVideoController(
  String path, {
  LocalVideoFileReadyProbe readyProbe = waitForLocalVideoFileReady,
  LocalVideoControllerFactory controllerFactory = _defaultLocalVideoController,
  Duration initializeRetryWindow = const Duration(seconds: 3),
  Duration perAttemptInitializeTimeout = const Duration(milliseconds: 1400),
  Duration retryInterval = const Duration(milliseconds: 250),
}) async {
  final normalized = path.trim();
  if (normalized.isEmpty) {
    throw StateError('local video path is empty');
  }
  final ready = await readyProbe(normalized);
  if (!ready) {
    throw StateError('local video file is not ready');
  }
  final attemptWindow = perAttemptInitializeTimeout + retryInterval;
  final maxAttempts = _attemptCount(initializeRetryWindow, attemptWindow);
  Object? lastError;
  StackTrace? lastStackTrace;
  for (var attempt = 0; attempt < maxAttempts; attempt++) {
    final controller = controllerFactory(normalized);
    try {
      await controller.initialize().timeout(perAttemptInitializeTimeout);
      return controller;
    } catch (error, stackTrace) {
      lastError = error;
      lastStackTrace = stackTrace;
      await controller.dispose();
      if (attempt < maxAttempts - 1) {
        await Future<void>.delayed(retryInterval);
      }
    }
  }
  final error = lastError;
  final stackTrace = lastStackTrace;
  if (error != null && stackTrace != null) {
    Error.throwWithStackTrace(error, stackTrace);
  }
  throw StateError('local video file is not playable');
}

Future<void> waitForLocalVideoPlayable(
  String path, {
  LocalVideoFileReadyProbe readyProbe = waitForLocalVideoFileReady,
  Duration initializeRetryWindow = const Duration(seconds: 3),
  Duration perAttemptInitializeTimeout = const Duration(milliseconds: 1400),
  Duration retryInterval = const Duration(milliseconds: 250),
}) async {
  final controller = await createInitializedLocalVideoController(
    path,
    readyProbe: readyProbe,
    initializeRetryWindow: initializeRetryWindow,
    perAttemptInitializeTimeout: perAttemptInitializeTimeout,
    retryInterval: retryInterval,
  );
  await controller.dispose();
}

VideoPlayerController _defaultLocalVideoController(String path) {
  return AppVideoPlayerControllerFactory.localFileReadinessProbe(path);
}
