import 'dart:developer' as developer;

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_cache_manager/flutter_cache_manager.dart';
import 'package:quwoquan_app/cloud/media/cdn_image_url_builder.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/media/avatar_image_url.dart';
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
);

final _previewImageCacheManager = _AppImageCacheManager(
  _imageCacheConfig(
    'appImagePreviewCache',
    maxObjects: 1000,
    stale: const Duration(days: 10),
  ),
);

final _ephemeralImageCacheManager = _AppImageCacheManager(
  _imageCacheConfig(
    'appImageEphemeralCache',
    maxObjects: 250,
    stale: const Duration(days: 2),
  ),
);

class _AppImageCacheManager extends CacheManager with ImageCacheManager {
  _AppImageCacheManager(super.config);
}

class AppImageCacheController {
  const AppImageCacheController._();

  static Future<void> evictAvatar(
    String imageUrl, {
    double size = AppSpacing.avatarSize,
  }) async {
    final candidates = resolveAvatarImageUrlCandidates(imageUrl);
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
  }) async {
    final candidates = resolveAvatarImageUrlCandidates(imageUrl);
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
}

/// CDN-aware image processing preset.
enum CdnImagePreset { avatar, thumbnail, cover, inline, full, none }

enum AppImageCacheTier { avatar, preview, ephemeral }

class AppResourceCacheProfile {
  const AppResourceCacheProfile({
    required this.name,
    required this.maxImageCacheObjects,
    required this.maxImageCacheBytes,
    required this.maxMediaDownloadCacheSizeMb,
    required this.maxConcurrentMediaDownloads,
    required this.maxPostObjectCacheEntries,
  });

  final String name;
  final int maxImageCacheObjects;
  final int maxImageCacheBytes;
  final int maxMediaDownloadCacheSizeMb;
  final int maxConcurrentMediaDownloads;
  final int maxPostObjectCacheEntries;

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
    maxMediaDownloadCacheSizeMb: 96,
    maxConcurrentMediaDownloads: 2,
    maxPostObjectCacheEntries: 120,
  );

  static const regular = AppResourceCacheProfile(
    name: 'regular',
    maxImageCacheObjects: 500,
    maxImageCacheBytes: 96 * 1024 * 1024,
    maxMediaDownloadCacheSizeMb: 200,
    maxConcurrentMediaDownloads: 3,
    maxPostObjectCacheEntries: 200,
  );

  static const expanded = AppResourceCacheProfile(
    name: 'expanded',
    maxImageCacheObjects: 900,
    maxImageCacheBytes: 192 * 1024 * 1024,
    maxMediaDownloadCacheSizeMb: 384,
    maxConcurrentMediaDownloads: 4,
    maxPostObjectCacheEntries: 320,
  );
}
