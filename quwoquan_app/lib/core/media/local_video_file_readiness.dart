import 'dart:async';
import 'dart:io';

import 'package:video_player/video_player.dart';

typedef LocalVideoFileReadyProbe = Future<bool> Function(String path);
typedef LocalVideoControllerFactory =
    VideoPlayerController Function(String path);

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
  final file = File(normalized);
  final maxAttempts = _attemptCount(timeout, pollInterval);
  int? lastKnownLength;
  var stableCount = 0;
  for (var attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      if (await file.exists()) {
        final length = await file.length();
        if (length > 0) {
          if (lastKnownLength == length) {
            stableCount += 1;
          } else {
            stableCount = 0;
            lastKnownLength = length;
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
    return await file.exists() && await file.length() > 0;
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
  return VideoPlayerController.file(File(path));
}
