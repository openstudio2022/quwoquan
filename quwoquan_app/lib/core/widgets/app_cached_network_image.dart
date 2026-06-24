import 'dart:developer' as developer;

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_cache_manager/flutter_cache_manager.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/media/cdn_image_url_builder.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/media/avatar_image_url.dart';
import 'package:quwoquan_app/core/media/content_media_url.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/trackers/page_lifecycle_observability.dart';

final _avatarImageCacheManager = _AppImageCacheManager(
  Config(
    'appImageAvatarCache',
    maxNrOfCacheObjects: 800,
    stalePeriod: const Duration(days: 30),
  ),
);

final _previewImageCacheManager = _AppImageCacheManager(
  Config(
    'appImagePreviewCache',
    maxNrOfCacheObjects: 1000,
    stalePeriod: const Duration(days: 10),
  ),
);

final _ephemeralImageCacheManager = _AppImageCacheManager(
  Config(
    'appImageEphemeralCache',
    maxNrOfCacheObjects: 250,
    stalePeriod: const Duration(days: 2),
  ),
);

class _AppImageCacheManager extends CacheManager with ImageCacheManager {
  _AppImageCacheManager(super.config);
}

class AppImageCacheController {
  const AppImageCacheController._();

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

class AppAvatarImage extends StatelessWidget {
  const AppAvatarImage({
    super.key,
    required this.imageUrl,
    this.size = AppSpacing.avatarSize,
    this.fit = BoxFit.cover,
    this.placeholder,
    this.errorWidget,
    this.onLoadFailed,
  });

  final String imageUrl;
  final double size;
  final BoxFit fit;
  final Widget? placeholder;
  final Widget? errorWidget;
  final void Function(Object error)? onLoadFailed;

  @override
  Widget build(BuildContext context) {
    return AppCachedNetworkImage(
      imageUrl: imageUrl,
      width: size,
      height: size,
      fit: fit,
      cdnPreset: CdnImagePreset.avatar,
      placeholder: placeholder,
      errorWidget: errorWidget,
      onLoadFailed: onLoadFailed,
    );
  }
}

class AppCachedNetworkImage extends ConsumerWidget {
  final String imageUrl;
  final List<String>? imageUrlCandidates;
  final BoxFit? fit;
  final double? width;
  final double? height;
  final Widget? placeholder;
  final Widget? errorWidget;
  final void Function(Object error)? onLoadFailed;
  final CdnImagePreset cdnPreset;
  final Widget Function(BuildContext context, ImageProvider imageProvider)?
  imageBuilder;

  const AppCachedNetworkImage({
    super.key,
    required this.imageUrl,
    this.imageUrlCandidates,
    this.fit,
    this.width,
    this.height,
    this.placeholder,
    this.errorWidget,
    this.onLoadFailed,
    this.cdnPreset = CdnImagePreset.none,
    this.imageBuilder,
  });

  List<String> get _processedUrlCandidates {
    final rawCandidates =
        imageUrlCandidates ?? _resolveImplicitCandidates(imageUrl);
    final processed = <String>[];
    for (final candidate in rawCandidates) {
      final normalized = candidate.trim();
      if (normalized.isEmpty || processed.contains(normalized)) {
        continue;
      }
      switch (cdnPreset) {
        case CdnImagePreset.thumbnail:
          processed.add(
            CdnImageUrlBuilder.thumbnail(
              normalized,
              width: (width ?? 400).toInt(),
            ),
          );
        case CdnImagePreset.cover:
          processed.add(
            CdnImageUrlBuilder.cover(normalized, width: (width ?? 750).toInt()),
          );
        case CdnImagePreset.inline:
          processed.add(
            CdnImageUrlBuilder.cover(normalized, width: (width ?? 900).toInt()),
          );
        case CdnImagePreset.avatar:
          processed.add(
            CdnImageUrlBuilder.avatar(normalized, size: (width ?? 120).toInt()),
          );
        case CdnImagePreset.full:
          processed.add(CdnImageUrlBuilder.full(normalized));
        case CdnImagePreset.none:
          processed.add(normalized);
      }
    }
    return processed;
  }

  static List<String> _resolveImplicitCandidates(String raw) {
    final normalized = raw.trim();
    if (normalized.isEmpty) {
      return const <String>[];
    }
    if (_looksLikeAvatarMedia(normalized)) {
      return resolveAvatarImageUrlCandidates(normalized);
    }
    return resolveContentMediaUrlCandidates(normalized);
  }

  static bool _looksLikeAvatarMedia(String raw) {
    final normalized = raw.replaceFirst(RegExp(r'^/+'), '').toLowerCase();
    return normalized.startsWith('media/avatar/') ||
        normalized.startsWith('avatar/') ||
        normalized.contains('/media/avatar/');
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final candidates = _processedUrlCandidates;
    if (candidates.isEmpty) {
      return _ImageLoadFailureReporter(
        onReport: () =>
            onLoadFailed?.call(StateError('image url candidates empty')),
        child: _buildErrorWidget(context),
      );
    }
    return _buildCandidateImage(context, ref, candidates, 0);
  }

  Widget _buildCandidateImage(
    BuildContext context,
    WidgetRef ref,
    List<String> candidates,
    int index,
  ) {
    final cacheManager = AppImageCacheController.cacheManagerForPreset(
      cdnPreset,
    );
    return CachedNetworkImage(
      imageUrl: candidates[index],
      cacheManager: cacheManager,
      fit: fit,
      width: width,
      height: height,
      memCacheWidth: _decodeExtentFor(width, context),
      memCacheHeight: _decodeExtentFor(height, context),
      maxWidthDiskCache: _diskCacheExtentFor(cacheManager, width, context),
      maxHeightDiskCache: _diskCacheExtentFor(cacheManager, height, context),
      imageBuilder: (context, imageProvider) {
        ref
            .read(pageLifecycleObservabilityProvider)
            .recordMediaLoad(
              mediaType: 'image',
              result: 'success',
              candidatesTried: index + 1,
            );
        final builder = imageBuilder;
        if (builder != null) {
          return builder(context, imageProvider);
        }
        return Image(
          image: imageProvider,
          fit: fit,
          width: width,
          height: height,
        );
      },
      placeholder: (context, url) =>
          placeholder ?? Container(color: AppColors.light.backgroundSecondary),
      errorWidget: (context, url, error) {
        final nextIndex = index + 1;
        if (nextIndex < candidates.length) {
          return _buildCandidateImage(context, ref, candidates, nextIndex);
        }
        developer.log(
          'image load failed after ${candidates.length} candidate(s): $url',
          name: 'AppCachedNetworkImage',
          error: error,
        );
        debugPrint(
          '[AppCachedNetworkImage] image load failed after '
          '${candidates.length} candidate(s); '
          'last=${_summarizeImageUrl(url)}; '
          'errorType=${error.runtimeType}',
        );
        ref
            .read(pageLifecycleObservabilityProvider)
            .recordMediaLoad(
              mediaType: 'image',
              result: 'failure',
              copyKey: 'imageLoadFailed',
              error: error,
              candidatesTried: candidates.length,
            );
        onLoadFailed?.call(error);
        return errorWidget ?? _buildErrorWidget(context);
      },
    );
  }

  int? _decodeExtentFor(double? logicalExtent, BuildContext context) {
    if (logicalExtent == null ||
        logicalExtent <= 0 ||
        logicalExtent == double.infinity) {
      return null;
    }
    final devicePixelRatio = MediaQuery.devicePixelRatioOf(context);
    final value = (logicalExtent * devicePixelRatio).round();
    if (value < 1) {
      return 1;
    }
    if (value > 4096) {
      return 4096;
    }
    return value;
  }

  int? _diskCacheExtentFor(
    BaseCacheManager cacheManager,
    double? logicalExtent,
    BuildContext context,
  ) {
    if (cacheManager is! ImageCacheManager) {
      return null;
    }
    final decoded = _decodeExtentFor(logicalExtent, context);
    if (decoded == null) {
      return null;
    }
    return decoded > 2048 ? 2048 : decoded;
  }

  String _summarizeImageUrl(String raw) {
    final uri = Uri.tryParse(raw);
    if (uri == null || uri.host.isEmpty) {
      return 'unparseable';
    }
    return '${uri.host}${uri.path}';
  }

  Widget _buildErrorWidget(BuildContext context) {
    return Container(
      color: AppColors.light.backgroundSecondary,
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.image_not_supported_outlined,
              color: AppColors.iosSecondaryLabel(context),
              size: AppSpacing.twenty,
            ),
            SizedBox(height: AppSpacing.xs),
            Text(
              UITextConstants.imageLoadFailed,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: AppColors.iosSecondaryLabel(context),
                fontSize: AppTypography.iosCaption1,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ImageLoadFailureReporter extends ConsumerStatefulWidget {
  const _ImageLoadFailureReporter({required this.child, this.onReport});

  final Widget child;
  final VoidCallback? onReport;

  @override
  ConsumerState<_ImageLoadFailureReporter> createState() =>
      _ImageLoadFailureReporterState();
}

class _ImageLoadFailureReporterState
    extends ConsumerState<_ImageLoadFailureReporter> {
  bool _reported = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || _reported) {
        return;
      }
      _reported = true;
      ref
          .read(pageLifecycleObservabilityProvider)
          .recordMediaLoad(
            mediaType: 'image',
            result: 'failure',
            copyKey: 'imageLoadFailed',
            candidatesTried: 0,
          );
      widget.onReport?.call();
    });
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
