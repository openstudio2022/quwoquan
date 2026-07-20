import 'dart:async';
import 'dart:collection';
import 'dart:developer' as developer;

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:quwoquan_app/application/content/media/content_media_upload_coordinator.dart';
import 'package:quwoquan_app/cloud/media/upload_policy.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

/// Upload task state.
enum UploadStatus { pending, uploading, completed, failed }

/// Represents a single upload task in the queue.
class UploadTask {
  final String localPath;
  final MediaCategory category;
  final String contentType;
  final int fileSize;

  UploadStatus status;
  String? cdnUrl;
  String? assetId;
  String? error;
  int retryCount;

  UploadTask({
    required this.localPath,
    required this.category,
    required this.contentType,
    required this.fileSize,
    this.status = UploadStatus.pending,
    this.retryCount = 0,
  });
}

/// Manages media upload queue with concurrency limits, retry, and offline support.
class MediaUploadManager {
  MediaUploadManager({
    required this.coordinator,
    required this.sourceReader,
    required this.uploadStream,
    this._maxConcurrent = 3,
    this._maxRetries = 3,
  });

  final ContentMediaUploadCoordinator coordinator;
  final ContentMediaSourceReader sourceReader;
  final ContentMediaStreamObjectUpload uploadStream;
  final int _maxConcurrent;
  final int _maxRetries;
  final Queue<UploadTask> _queue = Queue<UploadTask>();
  final List<UploadTask> _active = [];
  final Set<UploadTask> _failedRetryable = <UploadTask>{};
  final Set<Timer> _retryTimers = <Timer>{};
  final _controller = StreamController<UploadTask>.broadcast();
  StreamSubscription<List<ConnectivityResult>>? _connectivitySub;
  bool _disposed = false;

  Stream<UploadTask> get onTaskUpdate => _controller.stream;

  /// Enqueues an upload task, validates policy, and starts processing.
  Future<UploadTask> enqueue(UploadTask task) async {
    final policyError = validateUpload(
      category: task.category,
      fileSize: task.fileSize,
      contentType: task.contentType,
    );
    if (policyError != null) {
      task
        ..status = UploadStatus.failed
        ..error = policyError;
      _controller.add(task);
      return task;
    }

    _queue.add(task);
    _processQueue();
    return task;
  }

  void _processQueue() {
    while (_active.length < _maxConcurrent && _queue.isNotEmpty) {
      final task = _queue.removeFirst();
      _active.add(task);
      _executeUpload(task);
    }
  }

  Future<void> _executeUpload(UploadTask task) async {
    task.status = UploadStatus.uploading;
    _controller.add(task);

    try {
      final source = await sourceReader.prepare(task.localPath);
      if (source.fileSize != task.fileSize) {
        throw StateError('upload source size changed');
      }
      final asset = await coordinator.uploadPreparedSource(
        source: source,
        mediaType: contentMediaTypeForCategory(task.category),
        contentType: task.contentType,
        uploadStream: uploadStream,
      );
      task
        ..status = UploadStatus.completed
        ..cdnUrl = asset.cdnUrl?.toString()
        ..assetId = asset.assetId;
      _controller.add(task);
    } catch (error, stackTrace) {
      developer.log(
        'Media upload task failed',
        name: 'MediaUploadManager',
        error: error,
        stackTrace: stackTrace,
      );
      task.retryCount++;
      final retryable = _isRetryableUploadError(error);
      if (retryable && task.retryCount <= _maxRetries) {
        task.status = UploadStatus.pending;
        _scheduleRetry(task);
      } else {
        task
          ..status = UploadStatus.failed
          ..error = _uploadFailureCode(error);
        if (retryable) {
          _failedRetryable.add(task);
        }
        _controller.add(task);
      }
    } finally {
      _active.remove(task);
      _processQueue();
    }
  }

  /// Starts listening for network changes to retry failed uploads.
  void startOfflineMonitor() {
    _connectivitySub ??= Connectivity().onConnectivityChanged.listen((results) {
      final hasConnection = results.any((r) => r != ConnectivityResult.none);
      if (hasConnection) {
        _retryFailedTasks();
      }
    });
  }

  void _retryFailedTasks() {
    final failed = _failedRetryable.toList(growable: false);
    _failedRetryable.clear();
    for (final task in failed) {
      task
        ..status = UploadStatus.pending
        ..retryCount = 0
        ..error = null;
      _queue.add(task);
    }
    _processQueue();
  }

  void dispose() {
    _disposed = true;
    for (final timer in _retryTimers) {
      timer.cancel();
    }
    _retryTimers.clear();
    unawaited(_connectivitySub?.cancel());
    unawaited(_controller.close());
  }

  int get pendingCount => _queue.length;
  int get activeCount => _active.length;

  void _scheduleRetry(UploadTask task) {
    final exponent = (task.retryCount - 1).clamp(0, 5);
    final delay = Duration(seconds: 1 << exponent);
    late final Timer timer;
    timer = Timer(delay, () {
      _retryTimers.remove(timer);
      if (_disposed) return;
      _queue.add(task);
      _processQueue();
    });
    _retryTimers.add(timer);
  }
}

bool _isRetryableUploadError(Object error) {
  if (error is ContentMediaObjectUploadException) {
    return error.retryable;
  }
  final failure = error is CloudException
      ? error.runtimeFailure
      : error is RuntimeFailureBase
      ? error
      : null;
  if (failure == null) return false;
  return failure.recovery.action.trim().toLowerCase() == 'retry' ||
      failure.nature == RuntimeFailureNature.transient;
}

String _uploadFailureCode(Object error) {
  final failure = error is CloudException
      ? error.runtimeFailure
      : error is RuntimeFailureBase
      ? error
      : null;
  return failure?.code ?? RuntimeFailureCodes.cloudSystemUnavailable;
}
