import 'dart:async';
import 'dart:collection';
import 'dart:io';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/media/upload_policy.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';

/// Upload task state.
enum UploadStatus { pending, uploading, completed, failed }

/// Represents a single upload task in the queue.
class UploadTask {
  final String localPath;
  final MediaCategory category;
  final String contentType;
  final int fileSize;
  final String ownerId;
  final String fileName;
  final Map<String, dynamic>? completionMetadata;

  UploadStatus status;
  String? sessionId;
  String? presignUrl;
  String? cdnUrl;
  String? assetId;
  String? error;
  int retryCount;

  UploadTask({
    required this.localPath,
    required this.category,
    required this.contentType,
    required this.fileSize,
    required this.ownerId,
    required this.fileName,
    this.completionMetadata,
    this.status = UploadStatus.pending,
    this.retryCount = 0,
  });
}

/// Manages media upload queue with concurrency limits, retry, and offline support.
class MediaUploadManager {
  MediaUploadManager({
    CloudHttpClient? httpClient,
    http.Client? rawClient,
    int maxConcurrent = 3,
    int maxRetries = 3,
  })  : _httpClient =
            httpClient ?? CloudHttpClient(client: rawClient ?? http.Client()),
        _rawClient = rawClient ?? http.Client(),
        _maxConcurrent = maxConcurrent,
        _maxRetries = maxRetries;

  final CloudHttpClient _httpClient;
  final http.Client _rawClient;
  final int _maxConcurrent;
  final int _maxRetries;
  final Queue<UploadTask> _queue = Queue<UploadTask>();
  final List<UploadTask> _active = [];
  final _controller = StreamController<UploadTask>.broadcast();
  StreamSubscription<List<ConnectivityResult>>? _connectivitySub;

  String get _baseUrl => CloudRuntimeConfig.gatewayBaseUrl;

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
      final session = await _initUpload(task);
      task
        ..sessionId = session['sessionId'] as String?
        ..presignUrl = session['presignUrl'] as String?;

      await _uploadToOSS(task);

      final asset = await _completeUpload(task);
      task
        ..status = UploadStatus.completed
        ..cdnUrl = asset['cdnUrl'] as String?
        ..assetId = asset['assetId'] as String?;
      _controller.add(task);
    } catch (e) {
      task.retryCount++;
      if (task.retryCount <= _maxRetries) {
        task.status = UploadStatus.pending;
        _queue.add(task);
      } else {
        task
          ..status = UploadStatus.failed
          ..error = e.toString();
        _controller.add(task);
      }
    } finally {
      _active.remove(task);
      _processQueue();
    }
  }

  Future<Map<String, dynamic>> _initUpload(UploadTask task) async {
    final uri = Uri.parse('$_baseUrl${ContentApiMetadata.initMediaUploadPath}');
    return await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.initMediaUpload),
      body: {
        'category': task.category.name,
        'ownerId': task.ownerId,
        'fileName': task.fileName,
        'contentType': task.contentType,
        'fileSize': task.fileSize,
      },
    );
  }

  Future<void> _uploadToOSS(UploadTask task) async {
    final presignUrl = task.presignUrl;
    if (presignUrl == null || presignUrl.isEmpty) {
      throw StateError('No presign URL for upload');
    }

    final file = File(task.localPath);
    final bytes = await file.readAsBytes();

    final response = await _rawClient.put(
      Uri.parse(presignUrl),
      headers: {'Content-Type': task.contentType},
      body: bytes,
    );

    if (response.statusCode != 200 && response.statusCode != 201) {
      throw HttpException('OSS upload failed: ${response.statusCode}');
    }
  }

  Future<Map<String, dynamic>> _completeUpload(UploadTask task) async {
    final uri = Uri.parse(
      '$_baseUrl${ContentApiMetadata.completeMediaUploadPath(sessionId: task.sessionId ?? '')}',
    );
    return await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.completeMediaUpload,
      ),
      body: task.completionMetadata ?? {},
    );
  }

  /// Starts listening for network changes to retry failed uploads.
  void startOfflineMonitor() {
    _connectivitySub ??= Connectivity().onConnectivityChanged.listen((results) {
      final hasConnection =
          results.any((r) => r != ConnectivityResult.none);
      if (hasConnection) {
        _retryFailedTasks();
      }
    });
  }

  void _retryFailedTasks() {
    final failed = _queue.where((t) => t.status == UploadStatus.failed).toList();
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
