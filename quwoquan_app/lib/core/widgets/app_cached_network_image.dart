import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_cache_manager/flutter_cache_manager.dart';
import 'package:quwoquan_app/cloud/media/cdn_image_url_builder.dart';
import 'package:quwoquan_app/core/media/avatar_image_url.dart';
import 'package:quwoquan_app/core/media/content_media_url.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';

final _appImageCacheManager = CacheManager(
  Config(
    'appImageCache',
    maxNrOfCacheObjects: 500,
    stalePeriod: const Duration(days: 7),
  ),
);

class AppImageCacheController {
  const AppImageCacheController._();

  static Future<void> clearTemporaryImages() {
    return _appImageCacheManager.emptyCache();
  }

  static Future<void> preloadAvatar(
    String imageUrl, {
    double size = 120,
  }) async {
    final normalized = imageUrl.trim();
    if (normalized.isEmpty) {
      return;
    }
    final processed = CdnImageUrlBuilder.avatar(normalized, size: size.toInt());
    await _appImageCacheManager.downloadFile(processed);
  }
}

/// CDN-aware image processing preset.
enum CdnImagePreset { thumbnail, cover, avatar, full, none }

class AppAvatarImage extends StatelessWidget {
  const AppAvatarImage({
    super.key,
    required this.imageUrl,
    this.size = AppSpacing.avatarSize,
    this.fit = BoxFit.cover,
    this.placeholder,
    this.errorWidget,
  });

  final String imageUrl;
  final double size;
  final BoxFit fit;
  final Widget? placeholder;
  final Widget? errorWidget;

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
    );
  }
}

class AppCachedNetworkImage extends StatelessWidget {
  final String imageUrl;
  final List<String>? imageUrlCandidates;
  final BoxFit? fit;
  final double? width;
  final double? height;
  final Widget? placeholder;
  final Widget? errorWidget;
  final CdnImagePreset cdnPreset;

  const AppCachedNetworkImage({
    super.key,
    required this.imageUrl,
    this.imageUrlCandidates,
    this.fit,
    this.width,
    this.height,
    this.placeholder,
    this.errorWidget,
    this.cdnPreset = CdnImagePreset.none,
  });

  List<String> get _processedUrlCandidates {
    final rawCandidates = imageUrlCandidates ?? _resolveImplicitCandidates(imageUrl);
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
            CdnImageUrlBuilder.cover(
              normalized,
              width: (width ?? 750).toInt(),
            ),
          );
        case CdnImagePreset.avatar:
          processed.add(
            CdnImageUrlBuilder.avatar(
              normalized,
              size: (width ?? 120).toInt(),
            ),
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
  Widget build(BuildContext context) {
    final candidates = _processedUrlCandidates;
    if (candidates.isEmpty) {
      return _buildErrorWidget();
    }
    return _buildCandidateImage(candidates, 0);
  }

  Widget _buildCandidateImage(List<String> candidates, int index) {
    return CachedNetworkImage(
      imageUrl: candidates[index],
      cacheManager: _appImageCacheManager,
      fit: fit,
      width: width,
      height: height,
      placeholder: (context, url) =>
          placeholder ?? Container(color: AppColors.light.backgroundSecondary),
      errorWidget: (context, url, error) {
        final nextIndex = index + 1;
        if (nextIndex < candidates.length) {
          return _buildCandidateImage(candidates, nextIndex);
        }
        return errorWidget ?? _buildErrorWidget();
      },
    );
  }

  Widget _buildErrorWidget() {
    return Container(
      color: AppColors.light.backgroundSecondary,
      child: const Center(
        child: Icon(
          Icons.image_not_supported_outlined,
          color: Colors.grey,
          size: AppSpacing.twenty,
        ),
      ),
    );
  }
}
