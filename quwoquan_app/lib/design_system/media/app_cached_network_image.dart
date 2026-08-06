import 'dart:developer' as developer;

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_cache_manager/flutter_cache_manager.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/transport/media/avatar_image_url.dart';
import 'package:quwoquan_app/runtime/platform/media/app_image_cache_controller.dart';
import 'package:quwoquan_app/runtime/transport/media/content_media_url.dart';
import 'package:quwoquan_app/runtime/transport/media/media_candidate_failure.dart';
import 'package:quwoquan_app/runtime/transport/media/media_load_failure_cache.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/runtime/observability/trackers/page_lifecycle_observability.dart';
import 'package:quwoquan_app/design_system/media/cdn_image_url_port.dart';
import 'package:quwoquan_app/runtime/di/content_image_delivery_dependencies.dart';

export 'package:quwoquan_app/runtime/platform/media/app_image_cache_controller.dart';

const int appImageDecodeMaxPhysicalExtent = 2048;

class AppAvatarImage extends ConsumerWidget {
  const AppAvatarImage({
    super.key,
    required this.imageUrl,
    this.size = AppSpacing.avatarSize,
    this.fit = BoxFit.cover,
    this.placeholder,
    this.errorWidget,
    this.onLoadSucceeded,
    this.onLoadFailed,
  });

  final String imageUrl;
  final double size;
  final BoxFit fit;
  final Widget? placeholder;
  final Widget? errorWidget;
  final VoidCallback? onLoadSucceeded;
  final void Function(Object error)? onLoadFailed;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return AppCachedNetworkImage(
      imageUrl: imageUrl,
      imageUrlCandidates: resolveAvatarImageUrlCandidates(
        imageUrl,
        endpointConfig: ref.watch(mediaEndpointConfigProvider),
      ),
      width: size,
      height: size,
      fit: fit,
      cdnPreset: CdnImagePreset.avatar,
      placeholder: placeholder,
      errorWidget: errorWidget,
      onLoadSucceeded: onLoadSucceeded,
      onLoadFailed: onLoadFailed,
    );
  }
}

/// 圆形头像统一入口：复用头像候选 URL、缓存分层、失败负缓存与加载观测。
class AppCircularAvatar extends StatelessWidget {
  const AppCircularAvatar({
    super.key,
    required this.imageUrl,
    required this.size,
    required this.backgroundColor,
    this.fallback,
  });

  final String? imageUrl;
  final double size;
  final Color backgroundColor;
  final Widget? fallback;

  @override
  Widget build(BuildContext context) {
    final normalizedUrl = imageUrl?.trim() ?? '';
    final fallbackSurface = ColoredBox(
      color: backgroundColor,
      child: Center(child: fallback ?? const SizedBox.shrink()),
    );
    return ClipOval(
      child: SizedBox.square(
        dimension: size,
        child: normalizedUrl.isEmpty
            ? fallbackSurface
            : AppAvatarImage(
                imageUrl: normalizedUrl,
                size: size,
                placeholder: fallbackSurface,
                errorWidget: fallbackSurface,
              ),
      ),
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
  final VoidCallback? onLoadSucceeded;
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
    this.onLoadSucceeded,
    this.onLoadFailed,
    this.cdnPreset = CdnImagePreset.none,
    this.imageBuilder,
  });

  List<String> _processedUrlCandidates(
    MediaEndpointConfig? endpointConfig,
    CdnImageUrlPort urlPort,
  ) {
    final rawCandidates =
        imageUrlCandidates ??
        _resolveImplicitCandidates(imageUrl, endpointConfig: endpointConfig);
    final processed = <String>[];
    for (final candidate in rawCandidates) {
      final normalized = candidate.trim();
      if (normalized.isEmpty || processed.contains(normalized)) {
        continue;
      }
      switch (cdnPreset) {
        case CdnImagePreset.thumbnail:
          processed.add(urlPort.thumbnail(normalized));
        case CdnImagePreset.cover:
          processed.add(urlPort.cover(normalized));
        case CdnImagePreset.inline:
          processed.add(urlPort.display(normalized));
        case CdnImagePreset.avatar:
          processed.add(
            urlPort.avatar(normalized, size: (width ?? 120).toInt()),
          );
        case CdnImagePreset.full:
          processed.add(urlPort.full(normalized));
        case CdnImagePreset.none:
          processed.add(normalized);
      }
    }
    return processed;
  }

  static List<String> _resolveImplicitCandidates(
    String raw, {
    MediaEndpointConfig? endpointConfig,
  }) {
    final normalized = raw.trim();
    if (normalized.isEmpty) {
      return const <String>[];
    }
    if (_looksLikeAvatarMedia(normalized)) {
      return resolveAvatarImageUrlCandidates(
        normalized,
        endpointConfig: endpointConfig,
      );
    }
    return resolveContentMediaUrlCandidates(
      normalized,
      endpointConfig: endpointConfig,
    );
  }

  static bool _looksLikeAvatarMedia(String raw) {
    final normalized = raw.replaceFirst(RegExp(r'^/+'), '').toLowerCase();
    return normalized.startsWith('media/avatar/') ||
        normalized.startsWith('avatar/') ||
        normalized.contains('/media/avatar/');
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final candidates = _processedUrlCandidates(
      ref.watch(mediaEndpointConfigProvider),
      ref.watch(cdnImageUrlPortProvider),
    );
    if (candidates.isEmpty) {
      return _ImageLoadFailureReporter(
        onReport: () =>
            onLoadFailed?.call(StateError('image url candidates empty')),
        child: errorWidget ?? _buildErrorWidget(context),
      );
    }
    final primaryIdentity = candidates.first;
    if (MediaLoadFailureCache.instance.shouldSkipNetwork(primaryIdentity)) {
      final record = MediaLoadFailureCache.instance.activeFailure(
        primaryIdentity,
      );
      final error = StateError(
        'media negative cache active '
        '(kind=${record?.kind.name ?? 'other'}; '
        'status=${record?.statusCode ?? 'n/a'})',
      );
      return _ImageLoadFailureReporter(
        onReport: () => onLoadFailed?.call(error),
        child: errorWidget ?? _buildErrorWidget(context),
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
    return LayoutBuilder(
      builder: (context, constraints) {
        final logicalWidth = _effectiveLogicalExtent(
          width,
          constraints.maxWidth,
        );
        final logicalHeight = _effectiveLogicalExtent(
          height,
          constraints.maxHeight,
        );
        return CachedNetworkImage(
          imageUrl: candidates[index],
          cacheManager: cacheManager,
          fit: fit,
          width: width,
          height: height,
          memCacheWidth: _decodeExtentFor(logicalWidth, context),
          memCacheHeight: _decodeExtentFor(logicalHeight, context),
          maxWidthDiskCache: _diskCacheExtentFor(
            cacheManager,
            logicalWidth,
            context,
          ),
          maxHeightDiskCache: _diskCacheExtentFor(
            cacheManager,
            logicalHeight,
            context,
          ),
          imageBuilder: (context, imageProvider) {
            MediaLoadFailureCache.instance.clearIdentity(candidates[index]);
            ref
                .read(pageLifecycleObservabilityProvider)
                .recordMediaLoad(
                  mediaType: 'image',
                  result: 'success',
                  candidatesTried: index + 1,
                );
            final builder = imageBuilder;
            final child = builder != null
                ? builder(context, imageProvider)
                : Image(
                    image: imageProvider,
                    fit: fit,
                    width: width,
                    height: height,
                  );
            final onSucceeded = onLoadSucceeded;
            if (onSucceeded == null) {
              return child;
            }
            return _ImageLoadSuccessReporter(
              reportKey: candidates[index],
              onReport: onSucceeded,
              child: child,
            );
          },
          placeholder: (context, url) =>
              placeholder ??
              Container(color: AppColors.light.backgroundSecondary),
          errorWidget: (context, url, error) {
            final nextIndex = index + 1;
            if (nextIndex < candidates.length) {
              return _buildCandidateImage(context, ref, candidates, nextIndex);
            }
            final failureIdentity = candidates.first;
            MediaLoadFailureCache.instance.recordFailure(
              failureIdentity,
              error: error,
              candidateUrl: url,
            );
            final kind = classifyMediaCandidateLoadFailure(
              error,
              candidateUrl: url,
            );
            if (MediaLoadFailureCache.instance.shouldLogFailure(
              failureIdentity,
            )) {
              developer.log(
                'image load failed after ${candidates.length} candidate(s); '
                'last=${_summarizeImageUrl(url)}; '
                '(kind=${kind.name})',
                name: 'AppCachedNetworkImage',
                error: error.runtimeType,
              );
              debugPrint(
                '[AppCachedNetworkImage] image load failed after '
                '${candidates.length} candidate(s); '
                'last=${_summarizeImageUrl(url)}; '
                'kind=${kind.name}; '
                'errorType=${error.runtimeType}',
              );
            }
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
      },
    );
  }

  double? _effectiveLogicalExtent(double? explicit, double constrained) {
    if (explicit != null && explicit > 0 && explicit != double.infinity) {
      return explicit;
    }
    if (constrained > 0 && constrained != double.infinity) {
      return constrained;
    }
    return null;
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
    if (value > appImageDecodeMaxPhysicalExtent) {
      return appImageDecodeMaxPhysicalExtent;
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
    return decoded;
  }

  String _summarizeImageUrl(String raw) {
    final uri = Uri.tryParse(raw);
    if (uri == null || uri.host.isEmpty) {
      return 'unparseable';
    }
    return uri.host;
  }

  Widget _buildErrorWidget(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final isCompact =
            constraints.maxHeight.isFinite &&
            constraints.maxHeight < AppSpacing.forty;
        final iconSize = isCompact ? AppSpacing.iconSmall : AppSpacing.twenty;
        return Container(
          color: AppColors.light.backgroundSecondary,
          child: Center(
            child: isCompact
                ? Icon(
                    Icons.image_not_supported_outlined,
                    color: AppColors.iosSecondaryLabel(context),
                    size: iconSize,
                  )
                : Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(
                        Icons.image_not_supported_outlined,
                        color: AppColors.iosSecondaryLabel(context),
                        size: iconSize,
                      ),
                      SizedBox(height: AppSpacing.xs),
                      Text(
                        ContentText.imageLoadFailed,
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
      },
    );
  }
}

class _ImageLoadSuccessReporter extends StatefulWidget {
  const _ImageLoadSuccessReporter({
    required this.reportKey,
    required this.child,
    required this.onReport,
  });

  final String reportKey;
  final Widget child;
  final VoidCallback onReport;

  @override
  State<_ImageLoadSuccessReporter> createState() =>
      _ImageLoadSuccessReporterState();
}

class _ImageLoadSuccessReporterState extends State<_ImageLoadSuccessReporter> {
  bool _reported = false;
  int _reportGeneration = 0;

  @override
  void initState() {
    super.initState();
    _scheduleReport();
  }

  @override
  void didUpdateWidget(covariant _ImageLoadSuccessReporter oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.reportKey != widget.reportKey) {
      _reported = false;
      _scheduleReport();
    }
  }

  void _scheduleReport() {
    final generation = ++_reportGeneration;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || generation != _reportGeneration || _reported) {
        return;
      }
      _reported = true;
      widget.onReport();
    });
  }

  @override
  void dispose() {
    _reportGeneration += 1;
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => widget.child;
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
