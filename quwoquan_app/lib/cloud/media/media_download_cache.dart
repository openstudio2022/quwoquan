import 'dart:async';
import 'dart:collection';
import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';

/// LRU download cache for media files (voice, images, etc.).
/// Manages local file cache with configurable size limit.
class MediaDownloadCache {
  MediaDownloadCache({
    http.Client? client,
    int maxCacheSizeMb = 200,
    int maxConcurrentDownloads = 4,
  })  : _client = client ?? http.Client(),
        _maxCacheSize = maxCacheSizeMb * 1024 * 1024,
        _maxConcurrent = maxConcurrentDownloads;

  final http.Client _client;
  final int _maxCacheSize;
  final int _maxConcurrent;

  final LinkedHashMap<String, _CacheEntry> _entries =
      LinkedHashMap<String, _CacheEntry>();
  int _currentSize = 0;
  int _activeDownloads = 0;
  final Queue<_DownloadRequest> _downloadQueue = Queue<_DownloadRequest>();

  String? _cacheDir;

  Future<String> get _cachePath async {
    if (_cacheDir != null) return _cacheDir!;
    final dir = await getTemporaryDirectory();
    final mediaDir = Directory('${dir.path}/qwq_media_cache');
    if (!mediaDir.existsSync()) {
      await mediaDir.create(recursive: true);
    }
    _cacheDir = mediaDir.path;
    return _cacheDir!;
  }

  /// Returns the local file path for a cached URL, downloading if needed.
  Future<String?> getFile(String url) async {
    final key = _keyFromUrl(url);
    final entry = _entries.remove(key);
    if (entry != null) {
      _entries[key] = entry..lastAccess = DateTime.now();
      if (File(entry.localPath).existsSync()) {
        return entry.localPath;
      }
      _currentSize -= entry.fileSize;
    }

    return _download(url);
  }

  /// Checks if a URL is already cached locally.
  bool isCached(String url) {
    final key = _keyFromUrl(url);
    final entry = _entries[key];
    if (entry == null) return false;
    return File(entry.localPath).existsSync();
  }

  /// Pre-downloads a file without waiting for the result.
  void prefetch(String url) {
    if (isCached(url)) return;
    _download(url);
  }

  Future<String?> _download(String url) async {
    final completer = Completer<String?>();
    _downloadQueue.add(_DownloadRequest(url: url, completer: completer));
    _processDownloadQueue();
    return completer.future;
  }

  void _processDownloadQueue() {
    while (_activeDownloads < _maxConcurrent && _downloadQueue.isNotEmpty) {
      final request = _downloadQueue.removeFirst();
      _activeDownloads++;
      _executeDownload(request);
    }
  }

  Future<void> _executeDownload(_DownloadRequest request) async {
    try {
      final response = await _client.get(Uri.parse(request.url));
      if (response.statusCode != 200) {
        request.completer.complete(null);
        return;
      }

      final basePath = await _cachePath;
      final key = _keyFromUrl(request.url);
      final ext = _extensionFromUrl(request.url);
      final localPath = '$basePath/$key$ext';

      await File(localPath).writeAsBytes(response.bodyBytes);

      final fileSize = response.bodyBytes.length;
      _entries[key] = _CacheEntry(
        localPath: localPath,
        fileSize: fileSize,
        lastAccess: DateTime.now(),
      );
      _currentSize += fileSize;

      _evictIfNeeded();
      request.completer.complete(localPath);
    } catch (_) {
      request.completer.complete(null);
    } finally {
      _activeDownloads--;
      _processDownloadQueue();
    }
  }

  void _evictIfNeeded() {
    while (_currentSize > _maxCacheSize && _entries.isNotEmpty) {
      final oldestKey = _entries.keys.first;
      final entry = _entries.remove(oldestKey);
      if (entry != null) {
        _currentSize -= entry.fileSize;
        try {
          File(entry.localPath).deleteSync();
        } catch (_) {}
      }
    }
  }

  /// Clears all cached files.
  Future<void> clear() async {
    for (final entry in _entries.values) {
      try {
        File(entry.localPath).deleteSync();
      } catch (_) {}
    }
    _entries.clear();
    _currentSize = 0;
  }

  int get cachedFileCount => _entries.length;
  int get currentCacheSizeBytes => _currentSize;

  String _keyFromUrl(String url) {
    return url.hashCode.toRadixString(36);
  }

  String _extensionFromUrl(String url) {
    final uri = Uri.tryParse(url);
    if (uri == null) return '';
    final path = uri.path;
    final dot = path.lastIndexOf('.');
    if (dot < 0 || dot == path.length - 1) return '';
    return path.substring(dot);
  }
}

class _CacheEntry {
  final String localPath;
  final int fileSize;
  DateTime lastAccess;

  _CacheEntry({
    required this.localPath,
    required this.fileSize,
    required this.lastAccess,
  });
}

class _DownloadRequest {
  final String url;
  final Completer<String?> completer;

  _DownloadRequest({required this.url, required this.completer});
}
