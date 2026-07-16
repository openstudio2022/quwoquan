import 'dart:async';
import 'dart:collection';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:quwoquan_app/application/content/media/content_media_upload_coordinator.dart';
import 'package:quwoquan_app/cloud/media/upload_policy.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

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
  final _controller = StreamController<UploadTask>.broadcast();
  StreamSubscription<List<ConnectivityResult>>? _connectivitySub;

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
        mediaType: _mediaTypeForCategory(task.category),
        contentType: task.contentType,
        uploadStream: uploadStream,
      );
      task
        ..status = UploadStatus.completed
        ..cdnUrl = asset.cdnUrl?.toString()
        ..assetId = asset.assetId;
      _controller.add(task);
    } catch (_) {
      task.retryCount++;
      if (task.retryCount <= _maxRetries) {
        task.status = UploadStatus.pending;
        _queue.add(task);
      } else {
        task
          ..status = UploadStatus.failed
          ..error = 'upload_failed';
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
    final failed = _queue
        .where((t) => t.status == UploadStatus.failed)
        .toList();
    for (final task in failed) {
      if (task.retryCount <= _maxRetries) {
        task
          ..status = UploadStatus.pending
          ..retryCount = 0;
      }
    }
    _processQueue();
  }

  void dispose() {
    _connectivitySub?.cancel();
    _controller.close();
  }

  int get pendingCount => _queue.length;
  int get activeCount => _active.length;
}

ContentMediaType _mediaTypeForCategory(MediaCategory category) {
  return switch (category) {
    MediaCategory.chatVoice => ContentMediaType.audio,
    MediaCategory.chatVideo => ContentMediaType.video,
    MediaCategory.chatFile => ContentMediaType.file,
    _ => ContentMediaType.image,
  };
}
