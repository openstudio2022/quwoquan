import 'dart:async';
import 'dart:developer' as developer;
import 'dart:typed_data';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:file/file.dart';
import 'package:flutter/material.dart';
import 'package:flutter_cache_manager/flutter_cache_manager.dart';
import 'package:quwoquan_app/content/media/media_asset/adapters/cdn_image_url_builder.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/media/avatar_image_url.dart';
import 'package:quwoquan_app/core/media/media_delivery_reference.dart';
import 'package:quwoquan_app/core/platform/trusted_http_file_service.dart';

const double _compactFeedCacheExtentViewportMultiplier = 0.5;
const double _comfortableFeedCacheExtentViewportMultiplier = 1.0;

Config _imageCacheConfig(
  String key, {
  required int maxObjects,
  required Duration stale,
}) {
  return Config(
    key,
    maxNrOfCacheObjects: maxObjects,
    stalePeriod: stale,
    fileService: createTrustedHttpFileService(),
  );
}

final _avatarImageCacheManager = _AppImageCacheManager(
  _imageCacheConfig(
    'appImageAvatarCache',
    maxObjects: 800,
    stale: const Duration(days: 30),
  ),
  AppResourceCacheProfile.regular.avatarDiskCacheBytes,
);

final _previewImageCacheManager = _AppImageCacheManager(
  _imageCacheConfig(
    'appImagePreviewCache',
    maxObjects: 1000,
    stale: const Duration(days: 10),
  ),
  AppResourceCacheProfile.regular.previewDiskCacheBytes,
);

final _ephemeralImageCacheManager = _AppImageCacheManager(
  _imageCacheConfig(
    'appImageEphemeralCache',
    maxObjects: 250,
    stale: const Duration(days: 2),
  ),
  AppResourceCacheProfile.regular.ephemeralDiskCacheBytes,
);

class _AppImageCacheManager extends CacheManager with ImageCacheManager {
  _AppImageCacheManager(super.config, this._maxDiskCacheBytes)
    : assert(_maxDiskCacheBytes > 0);

  int _maxDiskCacheBytes;
  Future<void>? _trimInFlight;
  bool _trimRequested = false;
  final Map<String, DateTime> _recentAccess = <String, DateTime>{};

  int get maxDiskCacheBytes => _maxDiskCacheBytes;

  void updateDiskByteBudget(int value) {
    assert(value > 0);
    _maxDiskCacheBytes = value;
    _scheduleDiskByteBudgetEnforcement();
  }

  @override
  Stream<FileResponse> getFileStream(
    String url, {
    String? key,
    Map<String, String>? headers,
    bool withProgress = false,
  }) async* {
    final cacheKey = key ?? url;
    await for (final response in super.getFileStream(
      url,
      key: key,
      headers: headers,
      withProgress: withProgress,
    )) {
      if (response is FileInfo) {
        _recentAccess[cacheKey] = DateTime.now();
      }
      yield response;
      if (response is FileInfo) {
        _scheduleDiskByteBudgetEnforcement();
      }
    }
  }

  @override
  Future<FileInfo> downloadFile(
    String url, {
    String? key,
    Map<String, String>? authHeaders,
    bool force = false,
  }) async {
    final result = await super.downloadFile(
      url,
      key: key,
      authHeaders: authHeaders,
      force: force,
    );
    _recentAccess[key ?? url] = DateTime.now();
    _scheduleDiskByteBudgetEnforcement();
    return result;
  }

  @override
  Future<File> putFile(
    String url,
    Uint8List fileBytes, {
    String? key,
    String? eTag,
    Duration maxAge = const Duration(days: 30),
    String fileExtension = 'file',
  }) async {
    final result = await super.putFile(
      url,
      fileBytes,
      key: key,
      eTag: eTag,
      maxAge: maxAge,
      fileExtension: fileExtension,
    );
    _recentAccess[key ?? url] = DateTime.now();
    _scheduleDiskByteBudgetEnforcement();
    return result;
  }

  @override
  Future<File> putFileStream(
    String url,
    Stream<List<int>> source, {
    String? key,
    String? eTag,
    Duration maxAge = const Duration(days: 30),
    String fileExtension = 'file',
  }) async {
    final result = await super.putFileStream(
      url,
      source,
      key: key,
      eTag: eTag,
      maxAge: maxAge,
      fileExtension: fileExtension,
    );
    _recentAccess[key ?? url] = DateTime.now();
    _scheduleDiskByteBudgetEnforcement();
    return result;
  }

  Future<int> diskCacheSizeBytes() async {
    await config.repo.open();
    final objects = await config.repo.getAllObjects();
    var total = 0;
    for (final object in objects) {
      final file = await store.fileSystem.createFile(object.relativePath);
      if (await file.exists()) {
        total += await file.length();
      }
    }
    return total;
  }

  Future<void> enforceDiskByteBudget() {
    _trimRequested = true;
    final active = _trimInFlight;
    if (active != null) {
      return active;
    }
    late final Future<void> run;
    run = _drainDiskByteBudgetRequests().whenComplete(() {
      if (identical(_trimInFlight, run)) {
        _trimInFlight = null;
      }
    });
    _trimInFlight = run;
    return run;
  }

  Future<void> _drainDiskByteBudgetRequests() async {
    do {
      _trimRequested = false;
      await _trimToDiskByteBudget();
    } while (_trimRequested);
  }

  void _scheduleDiskByteBudgetEnforcement() {
    unawaited(
      enforceDiskByteBudget().catchError((Object error, StackTrace stackTrace) {
        developer.log(
          'image disk cache budget enforcement failed '
          '(${error.runtimeType})',
          name: 'AppImageCacheController',
          error: error,
          stackTrace: stackTrace,
        );
      }),
    );
  }

  Future<void> _trimToDiskByteBudget() async {
    await config.repo.open();
    final objects = await config.repo.getAllObjects();
    final resident = <({CacheObject object, int bytes, DateTime touched})>[];
    var total = 0;
    for (final object in objects) {
      final file = await store.fileSystem.createFile(object.relativePath);
      if (!await file.exists()) {
        if (object.id != null) {
          await store.removeCachedFile(object);
        }
        _recentAccess.remove(object.key);
        continue;
      }
      final bytes = await file.length();
      total += bytes;
      resident.add((
        object: object,
        bytes: bytes,
        touched:
            _recentAccess[object.key] ??
            object.touched ??
            DateTime.fromMillisecondsSinceEpoch(0),
      ));
    }
    if (total <= _maxDiskCacheBytes) {
      _pruneAccessIndex(resident.map((entry) => entry.object.key).toSet());
      return;
    }
    resident.sort((left, right) => left.touched.compareTo(right.touched));
    for (final entry in resident) {
      if (total <= _maxDiskCacheBytes) {
        break;
      }
      if (entry.object.id == null) {
        continue;
      }
      await store.removeCachedFile(entry.object);
      _recentAccess.remove(entry.object.key);
      total -= entry.bytes;
    }
    _pruneAccessIndex(
      resident
          .where((entry) => _recentAccess.containsKey(entry.object.key))
          .map((entry) => entry.object.key)
          .toSet(),
    );
  }

  void _pruneAccessIndex(Set<String> residentKeys) {
    _recentAccess.removeWhere((key, _) => !residentKeys.contains(key));
  }
}

class AppImageCacheController {
  const AppImageCacheController._();

  static Future<void> evictAvatar(
    String imageUrl, {
    double size = AppSpacing.avatarSize,
    MediaEndpointConfig? endpointConfig,
  }) async {
    final candidates = resolveAvatarImageUrlCandidates(
      imageUrl,
      endpointConfig: endpointConfig,
    );
    for (final candidate in candidates) {
      final processed = CdnImageUrlBuilder.avatar(
        candidate,
        size: size.toInt(),
      );
      try {
        await _avatarImageCacheManager.removeFile(processed);
      } catch (error) {
        developer.log(
          'avatar cache eviction failed (${error.runtimeType})',
          name: 'AppImageCacheController',
        );
      }
      PaintingBinding.instance.imageCache.evict(
        CachedNetworkImageProvider(
          processed,
          cacheManager: _avatarImageCacheManager,
        ),
      );
    }
  }

  static Future<void> clearTemporaryImages() {
    return _ephemeralImageCacheManager.emptyCache();
  }

  static Future<void> clearAllRebuildableImages() async {
    await _ephemeralImageCacheManager.emptyCache();
    await _previewImageCacheManager.emptyCache();
    await _avatarImageCacheManager.emptyCache();
  }

  static void applyResourceProfile(AppResourceCacheProfile profile) {
    final imageCache = PaintingBinding.instance.imageCache;
    imageCache.maximumSize = profile.maxImageCacheObjects;
    imageCache.maximumSizeBytes = profile.maxImageCacheBytes;
    _avatarImageCacheManager.updateDiskByteBudget(profile.avatarDiskCacheBytes);
    _previewImageCacheManager.updateDiskByteBudget(
      profile.previewDiskCacheBytes,
    );
    _ephemeralImageCacheManager.updateDiskByteBudget(
      profile.ephemeralDiskCacheBytes,
    );
  }

  static void trimForMemoryPressure() {
    applyResourceProfile(AppResourceCacheProfile.compact);
    final imageCache = PaintingBinding.instance.imageCache;
    imageCache.clear();
    imageCache.clearLiveImages();
  }

  static Future<void> preloadAvatar(
    String imageUrl, {
    double size = 120,
    MediaEndpointConfig? endpointConfig,
  }) async {
    final candidates = resolveAvatarImageUrlCandidates(
      imageUrl,
      endpointConfig: endpointConfig,
    );
    if (candidates.isEmpty) {
      return;
    }
    final processed = CdnImageUrlBuilder.avatar(
      candidates.first,
      size: size.toInt(),
    );
    await _avatarImageCacheManager.downloadFile(processed);
  }

  static AppImageCacheTier cacheTierForPreset(CdnImagePreset preset) {
    switch (preset) {
      case CdnImagePreset.avatar:
        return AppImageCacheTier.avatar;
      case CdnImagePreset.thumbnail:
      case CdnImagePreset.cover:
        return AppImageCacheTier.preview;
      case CdnImagePreset.inline:
      case CdnImagePreset.full:
      case CdnImagePreset.none:
        return AppImageCacheTier.ephemeral;
    }
  }

  static BaseCacheManager cacheManagerForPreset(CdnImagePreset preset) {
    switch (cacheTierForPreset(preset)) {
      case AppImageCacheTier.avatar:
        return _avatarImageCacheManager;
      case AppImageCacheTier.preview:
        return _previewImageCacheManager;
      case AppImageCacheTier.ephemeral:
        return _ephemeralImageCacheManager;
    }
  }

  static int diskByteBudgetForTier(AppImageCacheTier tier) {
    return _managerForTier(tier).maxDiskCacheBytes;
  }

  static Future<int> diskCacheSizeBytesForTier(AppImageCacheTier tier) {
    return _managerForTier(tier).diskCacheSizeBytes();
  }

  static Future<void> enforceDiskByteBudgetForTier(AppImageCacheTier tier) {
    return _managerForTier(tier).enforceDiskByteBudget();
  }

  static void debugOverrideDiskByteBudgetForTier(
    AppImageCacheTier tier,
    int bytes,
  ) {
    assert(bytes > 0);
    _managerForTier(tier).updateDiskByteBudget(bytes);
  }

  static _AppImageCacheManager _managerForTier(AppImageCacheTier tier) {
    switch (tier) {
      case AppImageCacheTier.avatar:
        return _avatarImageCacheManager;
      case AppImageCacheTier.preview:
        return _previewImageCacheManager;
      case AppImageCacheTier.ephemeral:
        return _ephemeralImageCacheManager;
    }
  }
}

/// CDN-aware image processing preset.
enum CdnImagePreset { avatar, thumbnail, cover, inline, full, none }

enum AppImageCacheTier { avatar, preview, ephemeral }

class AppResourceCacheProfile {
  const AppResourceCacheProfile({
    required this.name,
    required this.maxImageCacheObjects,
    required this.maxImageCacheBytes,
    required this.maxImageDiskCacheBytes,
    required this.maxMediaDownloadCacheSizeMb,
    required this.maxConcurrentMediaDownloads,
    required this.maxPostObjectCacheEntries,
  });

  final String name;
  final int maxImageCacheObjects;
  final int maxImageCacheBytes;
  final int maxImageDiskCacheBytes;
  final int maxMediaDownloadCacheSizeMb;
  final int maxConcurrentMediaDownloads;
  final int maxPostObjectCacheEntries;

  int get avatarDiskCacheBytes => maxImageDiskCacheBytes ~/ 8;

  int get previewDiskCacheBytes => maxImageDiskCacheBytes * 5 ~/ 8;

  int get ephemeralDiskCacheBytes =>
      maxImageDiskCacheBytes - avatarDiskCacheBytes - previewDiskCacheBytes;

  bool get usesCompactScrollMediaPolicy => name == compact.name;

  double get feedCacheExtentViewportMultiplier => usesCompactScrollMediaPolicy
      ? _compactFeedCacheExtentViewportMultiplier
      : _comfortableFeedCacheExtentViewportMultiplier;

  double feedCacheExtentForViewport(double viewportDimension) {
    if (viewportDimension <= 0 || viewportDimension == double.infinity) {
      return 0;
    }
    return viewportDimension * feedCacheExtentViewportMultiplier;
  }

  static const compact = AppResourceCacheProfile(
    name: 'compact',
    maxImageCacheObjects: 300,
    maxImageCacheBytes: 64 * 1024 * 1024,
    maxImageDiskCacheBytes: 96 * 1024 * 1024,
    maxMediaDownloadCacheSizeMb: 96,
    maxConcurrentMediaDownloads: 2,
    maxPostObjectCacheEntries: 120,
  );

  static const regular = AppResourceCacheProfile(
    name: 'regular',
    maxImageCacheObjects: 500,
    maxImageCacheBytes: 96 * 1024 * 1024,
    maxImageDiskCacheBytes: 192 * 1024 * 1024,
    maxMediaDownloadCacheSizeMb: 200,
    maxConcurrentMediaDownloads: 3,
    maxPostObjectCacheEntries: 200,
  );

  static const expanded = AppResourceCacheProfile(
    name: 'expanded',
    maxImageCacheObjects: 900,
    maxImageCacheBytes: 192 * 1024 * 1024,
    maxImageDiskCacheBytes: 384 * 1024 * 1024,
    maxMediaDownloadCacheSizeMb: 384,
    maxConcurrentMediaDownloads: 4,
    maxPostObjectCacheEntries: 320,
  );
}
