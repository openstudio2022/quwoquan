// ignore_for_file: prefer_initializing_formals

import 'dart:async';
import 'dart:collection';
import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/runtime/platform/file_storage_gateway.dart';
import 'package:quwoquan_app/runtime/platform/storage/cache/cache_telemetry_sink.dart';
import 'package:quwoquan_app/runtime/platform/storage/media_cache_file_storage_gateway.dart';

/// LRU download cache for media files (voice, images, etc.).
/// Manages local file cache with configurable size limit.
///
/// 网络出站走 `mediaDataPlaneHttpClientProvider` 注入的 [CloudHttpClient]，
/// 与 Gateway 调用共享超时预算、传输失败分类与 API 延迟观测；媒体 CDN 的
/// 授权由 URL 承载，因此该 client 不附带 bearer。
class MediaDownloadCache {
  MediaDownloadCache({
    required CloudHttpClient client,
    int maxCacheSizeMb = 200,
    int maxConcurrentDownloads = 4,
    Future<String> Function()? cacheDirectoryPathProvider,
    MediaCacheFileStorageGateway? fileStorageGateway,
    CacheTelemetrySink telemetrySink = const DeveloperLogCacheTelemetrySink(
      name: 'MediaDownloadCache',
    ),
  }) : _client = client,
       _maxCacheSize = maxCacheSizeMb * 1024 * 1024,
       _maxConcurrent = maxConcurrentDownloads,
       _cacheDirectoryPathProvider = cacheDirectoryPathProvider,
       _fileStorageGateway =
           fileStorageGateway ??
           requireMediaCacheFileStorageGateway(createFileStorageGateway()),
       _telemetrySink = telemetrySink;

  final CloudHttpClient _client;
  final int _maxCacheSize;
  final int _maxConcurrent;
  final Future<String> Function()? _cacheDirectoryPathProvider;
  final MediaCacheFileStorageGateway _fileStorageGateway;
  final CacheTelemetrySink _telemetrySink;

  final LinkedHashMap<String, _CacheEntry> _entries =
      LinkedHashMap<String, _CacheEntry>();
  int _currentSize = 0;
  int _activeDownloads = 0;
  final Queue<_DownloadRequest> _downloadQueue = Queue<_DownloadRequest>();
  final Map<String, Completer<String?>> _inflightByKey =
      <String, Completer<String?>>{};

  String? _cacheDir;

  Future<String> get _cachePath async {
    if (_cacheDir != null) return _cacheDir!;
    final overridePath = await _cacheDirectoryPathProvider?.call();
    final mediaDirectoryPath =
        overridePath ??
        _fileStorageGateway.joinPath(
          await _fileStorageGateway.temporaryPath(),
          'qwq_media_cache',
        );
    if (!await _fileStorageGateway.directoryExists(mediaDirectoryPath)) {
      await _fileStorageGateway.ensureDirectory(mediaDirectoryPath);
    }
    _cacheDir = mediaDirectoryPath;
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
      if (_fileStorageGateway.fileExistsSync(entry.localPath)) {
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
      if (_fileStorageGateway.fileExistsSync(entry.localPath)) {
        return entry.localPath;
      }
      _currentSize -= entry.fileSize;
      return null;
    }

    final basePath = await _cachePath;
    final localPath = _fileStorageGateway.joinPath(
      basePath,
      '$key${_extensionFromUrl(normalized)}',
    );
    if (!_fileStorageGateway.fileExistsSync(localPath)) {
      return null;
    }
    final fileSize = _fileStorageGateway.fileLengthSync(localPath);
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
    return _fileStorageGateway.fileExistsSync(entry.localPath);
  }

  /// Pre-downloads a file without waiting for the result.
  void prefetch(String url) {
    if (isCached(url)) return;
    unawaited(_download(url, isPrefetch: true));
  }

  int get activeDownloadCount => _activeDownloads;

  int get queuedDownloadCount => _downloadQueue.length;

  int get inflightDownloadCount => _inflightByKey.length;

  void cancelQueuedPrefetches({String? url}) {
    final normalized = url?.trim();
    final retained = Queue<_DownloadRequest>();
    while (_downloadQueue.isNotEmpty) {
      final request = _downloadQueue.removeFirst();
      final matchesUrl = normalized == null || request.url == normalized;
      if (request.isPrefetch && matchesUrl) {
        _inflightByKey.remove(request.key);
        if (!request.completer.isCompleted) {
          request.completer.complete(null);
        }
        continue;
      }
      retained.add(request);
    }
    _downloadQueue.addAll(retained);
  }

  Future<String?> _download(String url, {bool isPrefetch = false}) async {
    final key = _keyFromUrl(url);
    final existing = _inflightByKey[key];
    if (existing != null) {
      return existing.future;
    }
    final completer = Completer<String?>();
    _inflightByKey[key] = completer;
    _downloadQueue.add(
      _DownloadRequest(
        key: key,
        url: url,
        completer: completer,
        isPrefetch: isPrefetch,
      ),
    );
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
      if (!_inflightByKey.containsKey(request.key)) {
        return;
      }
      final response = await _client.get(Uri.parse(request.url));
      if (response.statusCode != 200) {
        _completeRequest(request, null);
        return;
      }

      final basePath = await _cachePath;
      final key = _keyFromUrl(request.url);
      final ext = _extensionFromUrl(request.url);
      final localPath = _fileStorageGateway.joinPath(basePath, '$key$ext');

      await _fileStorageGateway.writeAsBytes(localPath, response.bodyBytes);

      final fileSize = response.bodyBytes.length;
      _entries[key] = _CacheEntry(
        localPath: localPath,
        fileSize: fileSize,
        lastAccess: DateTime.now(),
      );
      _currentSize += fileSize;

      _evictIfNeeded();
      _completeRequest(request, localPath);
    } catch (_) {
      _completeRequest(request, null);
    } finally {
      _inflightByKey.remove(request.key);
      _activeDownloads--;
      _processDownloadQueue();
    }
  }

  void _completeRequest(_DownloadRequest request, String? value) {
    if (!request.completer.isCompleted) {
      request.completer.complete(value);
    }
  }

  void _evictIfNeeded() {
    while (_currentSize > _maxCacheSize && _entries.isNotEmpty) {
      final oldestKey = _entries.keys.first;
      final entry = _entries.remove(oldestKey);
      if (entry != null) {
        _currentSize -= entry.fileSize;
        try {
          _fileStorageGateway.deleteFileSync(entry.localPath);
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
      final cachePath = await _cachePath;
      if (await _fileStorageGateway.directoryExists(cachePath)) {
        for (final entry in await _fileStorageGateway.listDirectory(
          cachePath,
        )) {
          if (!entry.isDirectory) {
            try {
              if (_fileStorageGateway.fileExistsSync(entry.path)) {
                clearedBytes += _fileStorageGateway.fileLengthSync(entry.path);
              }
              _fileStorageGateway.deleteFileSync(entry.path);
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
      _downloadQueue.clear();
      for (final completer in _inflightByKey.values) {
        if (!completer.isCompleted) {
          completer.complete(null);
        }
      }
      _inflightByKey.clear();
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
  final String key;
  final String url;
  final Completer<String?> completer;
  final bool isPrefetch;

  _DownloadRequest({
    required this.key,
    required this.url,
    required this.completer,
    required this.isPrefetch,
  });
}
