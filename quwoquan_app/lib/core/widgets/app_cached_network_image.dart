import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_cache_manager/flutter_cache_manager.dart';
import 'package:quwoquan_app/cloud/media/cdn_image_url_builder.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';

final _appImageCacheManager = CacheManager(
  Config(
    'appImageCache',
    maxNrOfCacheObjects: 500,
    stalePeriod: const Duration(days: 7),
  ),
);

/// CDN-aware image processing preset.
enum CdnImagePreset { thumbnail, cover, avatar, full, none }

class AppCachedNetworkImage extends StatelessWidget {
  final String imageUrl;
  final BoxFit? fit;
  final double? width;
  final double? height;
  final Widget? placeholder;
  final Widget? errorWidget;
  final CdnImagePreset cdnPreset;

  const AppCachedNetworkImage({
    super.key,
    required this.imageUrl,
    this.fit,
    this.width,
    this.height,
    this.placeholder,
    this.errorWidget,
    this.cdnPreset = CdnImagePreset.none,
  });

  String get _processedUrl {
    switch (cdnPreset) {
      case CdnImagePreset.thumbnail:
        return CdnImageUrlBuilder.thumbnail(imageUrl, width: (width ?? 400).toInt());
      case CdnImagePreset.cover:
        return CdnImageUrlBuilder.cover(imageUrl, width: (width ?? 750).toInt());
      case CdnImagePreset.avatar:
        return CdnImageUrlBuilder.avatar(imageUrl, size: (width ?? 120).toInt());
      case CdnImagePreset.full:
        return CdnImageUrlBuilder.full(imageUrl);
      case CdnImagePreset.none:
        return imageUrl;
    }
  }

  @override
  Widget build(BuildContext context) {
    if (imageUrl.isEmpty) {
      return _buildErrorWidget();
    }

    return CachedNetworkImage(
      imageUrl: _processedUrl,
      cacheManager: _appImageCacheManager,
      fit: fit,
      width: width,
      height: height,
      placeholder: (context, url) =>
          placeholder ??
          Container(
            color: AppColors.light.backgroundSecondary,
          ),
      errorWidget: (context, url, error) => errorWidget ?? _buildErrorWidget(),
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
