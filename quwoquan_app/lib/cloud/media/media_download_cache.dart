// ignore_for_file: prefer_initializing_formals

import 'dart:async';
import 'dart:collection';
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:quwoquan_app/core/services/cache/cache_telemetry_sink.dart';

/// LRU download cache for media files (voice, images, etc.).
/// Manages local file cache with configurable size limit.
class MediaDownloadCache {
  MediaDownloadCache({
    http.Client? client,
    int maxCacheSizeMb = 200,
    int maxConcurrentDownloads = 4,
    Future<String> Function()? cacheDirectoryPathProvider,
    CacheTelemetrySink telemetrySink = const DeveloperLogCacheTelemetrySink(
      name: 'MediaDownloadCache',
    ),
  }) : _client = client ?? http.Client(),
       _maxCacheSize = maxCacheSizeMb * 1024 * 1024,
       _maxConcurrent = maxConcurrentDownloads,
       _cacheDirectoryPathProvider = cacheDirectoryPathProvider,
       _telemetrySink = telemetrySink;

  final http.Client _client;
  final int _maxCacheSize;
  final int _maxConcurrent;
  final Future<String> Function()? _cacheDirectoryPathProvider;
  final CacheTelemetrySink _telemetrySink;

  final LinkedHashMap<String, _CacheEntry> _entries =
      LinkedHashMap<String, _CacheEntry>();
  int _currentSize = 0;
  int _activeDownloads = 0;
  final Queue<_DownloadRequest> _downloadQueue = Queue<_DownloadRequest>();

  String? _cacheDir;

  Future<String> get _cachePath async {
    if (_cacheDir != null) return _cacheDir!;
    final overridePath = await _cacheDirectoryPathProvider?.call();
    final mediaDir = overridePath == null
        ? Directory('${(await getTemporaryDirectory()).path}/qwq_media_cache')
        : Directory(overridePath);
    if (!mediaDir.existsSync()) {
      await mediaDir.create(recursive: true);
    }
    _cacheDir = mediaDir.path;
    return _cacheDir!;
  }

  /// Returns the local file path for a cached URL, downloading if needed.
  Future<String?> getFile(String url) async {
    final normalized = url.trim();
    if (normalized.isEmpty) {
      return null;
    }
    final key = _keyFromUrl(normalized);
    final entry = _entries.remove(key);
    if (entry != null) {
      _entries[key] = entry..lastAccess = DateTime.now();
      if (File(entry.localPath).existsSync()) {
        return entry.localPath;
      }
      _currentSize -= entry.fileSize;
    }

    final cachedPath = await getCachedFilePath(normalized);
    if (cachedPath != null) {
      return cachedPath;
    }
    return _download(normalized);
  }

  /// Returns a cached local file path without triggering a network download.
  Future<String?> getCachedFilePath(String url) async {
    final normalized = url.trim();
    if (normalized.isEmpty) {
      return null;
    }
    final key = _keyFromUrl(normalized);
    final entry = _entries.remove(key);
    if (entry != null) {
      _entries[key] = entry..lastAccess = DateTime.now();
      if (File(entry.localPath).existsSync()) {
        return entry.localPath;
      }
      _currentSize -= entry.fileSize;
      return null;
    }

    final basePath = await _cachePath;
    final localPath = '$basePath/$key${_extensionFromUrl(normalized)}';
    final file = File(localPath);
    if (!file.existsSync()) {
      return null;
    }
    final fileSize = await file.length();
    _entries[key] = _CacheEntry(
      localPath: localPath,
      fileSize: fileSize,
      lastAccess: DateTime.now(),
    );
    _currentSize += fileSize;
    _evictIfNeeded();
    return localPath;
  }

  /// Returns a cached local file URI without triggering a network download.
  Future<Uri?> getCachedFileUri(String url) async {
    final path = await getCachedFilePath(url);
    return path == null ? null : Uri.file(path);
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
        } catch (_) {
          /* best-effort: LRU 淘汰时删除磁盘缓存文件，删除失败仅留下孤儿文件，后续 clear 会再清理 */
        }
      }
    }
  }

  /// Clears all cached files.
  Future<void> clear() async {
    var clearedBytes = 0;
    var clearedFiles = 0;
    try {
      final dir = Directory(await _cachePath);
      if (dir.existsSync()) {
        for (final entity in dir.listSync()) {
          if (entity is File) {
            try {
              if (entity.existsSync()) {
                clearedBytes += entity.lengthSync();
              }
              entity.deleteSync();
              clearedFiles += 1;
            } catch (_) {
              /* best-effort: 清空缓存时删除磁盘文件，个别删除失败不影响内存索引清零 */
            }
          }
        }
      }
    } catch (_) {
      return;
    } finally {
      _entries.clear();
      _currentSize = 0;
      _telemetrySink.record('resource.bytes_cleared', <String, Object?>{
        'bytes': clearedBytes,
        'files': clearedFiles,
      });
    }
  }

  int get cachedFileCount => _entries.length;
  int get currentCacheSizeBytes => _currentSize;

  String _keyFromUrl(String url) {
    return sha1.convert(utf8.encode(url.trim())).toString();
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
