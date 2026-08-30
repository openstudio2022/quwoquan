import 'dart:developer' as developer;

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/foundation.dart';
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

/// 三态语义 key：加载成功 / 加载中占位 / 显式失败。
/// Widget 测试与设备 UAT 用它们区分「真解码成功」与「灰块占位/错误」，
/// 防止「图片全灰也算通过」的假阳性（自定义 placeholder/errorWidget 同样生效）。
const ValueKey<String> appImageLoadSuccessKey = ValueKey<String>(
  'app-image-load-success',
);
const ValueKey<String> appImageLoadPlaceholderKey = ValueKey<String>(
  'app-image-load-placeholder',
);
const ValueKey<String> appImageLoadErrorKey = ValueKey<String>(
  'app-image-load-error',
);

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

class _ImageLoadTelemetryCycle {
  _ImageLoadTelemetryCycle(DateTime Function()? now)
    : _now = now,
      _startedAt = now?.call(),
      _stopwatch = now == null ? (Stopwatch()..start()) : null;

  final DateTime Function()? _now;
  final DateTime? _startedAt;
  final Stopwatch? _stopwatch;
  bool _completed = false;
  late int durationMs;

  bool markTerminal() {
    if (_completed) {
      return false;
    }
    _completed = true;
    final stopwatch = _stopwatch;
    if (stopwatch != null) {
      stopwatch.stop();
      durationMs = stopwatch.elapsedMilliseconds;
    } else {
      durationMs = _now!().difference(_startedAt!).inMilliseconds;
    }
    return true;
  }
}

class _ImageLoadCycleScope extends StatefulWidget {
  const _ImageLoadCycleScope({
    required this.sourceIdentity,
    required this.candidates,
    required this.now,
    required this.builder,
  });

  final String sourceIdentity;
  final List<String> candidates;
  final DateTime Function()? now;
  final Widget Function(_ImageLoadTelemetryCycle cycle) builder;

  @override
  State<_ImageLoadCycleScope> createState() => _ImageLoadCycleScopeState();
}

class _ImageLoadCycleScopeState extends State<_ImageLoadCycleScope> {
  late _ImageLoadTelemetryCycle _cycle;

  @override
  void initState() {
    super.initState();
    _cycle = _ImageLoadTelemetryCycle(widget.now);
  }

  @override
  void didUpdateWidget(covariant _ImageLoadCycleScope oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.sourceIdentity != widget.sourceIdentity ||
        !listEquals(oldWidget.candidates, widget.candidates)) {
      _cycle = _ImageLoadTelemetryCycle(widget.now);
    }
  }

  @override
  Widget build(BuildContext context) => widget.builder(_cycle);
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
  final DateTime Function()? now;

  /// 稳定缓存键（可选）。默认 null 时沿用完整 URL 作缓存键，行为不变。
  /// 短签 URL（signed grant）场景必须传入稳定资产身份
  /// （SignedMediaDeliveryLease.cacheIdentity）：签名 query 随 TTL 轮换，
  /// 用完整 URL 作键会导致每次换签都重新下载与解码。
  /// 仅作用于首个候选 URL；候选回退指向不同资产字节，不能共享同一键。
  final String? cacheKey;

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
    this.cacheKey,
    this.now,
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
    return _ImageLoadCycleScope(
      sourceIdentity: imageUrl.trim(),
      candidates: candidates,
      now: now,
      builder: (cycle) {
        if (candidates.isEmpty) {
          final error = StateError('image url candidates empty');
          return _ImageLoadFailureReporter(
            key: ObjectKey(cycle),
            onReport: () {
              _recordTerminalMediaLoad(
                ref: ref,
                cycle: cycle,
                result: 'failure',
                candidatesTried: 0,
                error: error,
              );
              onLoadFailed?.call(error);
            },
            child: KeyedSubtree(
              key: appImageLoadErrorKey,
              child: errorWidget ?? _buildErrorWidget(context),
            ),
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
            key: ObjectKey(cycle),
            onReport: () {
              _recordTerminalMediaLoad(
                ref: ref,
                cycle: cycle,
                result: 'failure',
                candidatesTried: 0,
                error: error,
              );
              onLoadFailed?.call(error);
            },
            child: KeyedSubtree(
              key: appImageLoadErrorKey,
              child: errorWidget ?? _buildErrorWidget(context),
            ),
          );
        }
        return _buildCandidateImage(context, ref, candidates, 0, cycle);
      },
    );
  }

  void _recordTerminalMediaLoad({
    required WidgetRef ref,
    required _ImageLoadTelemetryCycle cycle,
    required String result,
    required int candidatesTried,
    Object? error,
  }) {
    if (!cycle.markTerminal()) {
      return;
    }
    ref
        .read(pageLifecycleObservabilityProvider)
        .recordMediaLoad(
          mediaType: 'image',
          result: result,
          copyKey: result == 'failure' ? 'imageLoadFailed' : null,
          error: error,
          durationMs: cycle.durationMs,
          candidatesTried: candidatesTried,
        );
  }

  Widget _buildCandidateImage(
    BuildContext context,
    WidgetRef ref,
    List<String> candidates,
    int index,
    _ImageLoadTelemetryCycle cycle,
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
          cacheKey: index == 0 ? cacheKey : null,
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
            _recordTerminalMediaLoad(
              ref: ref,
              cycle: cycle,
              result: 'success',
              candidatesTried: index + 1,
            );
            final builder = imageBuilder;
            final decoded = builder != null
                ? builder(context, imageProvider)
                : Image(
                    image: imageProvider,
                    fit: fit,
                    width: width,
                    height: height,
                  );
            final child = KeyedSubtree(
              key: appImageLoadSuccessKey,
              child: decoded,
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
          // 占位色随主题动态解析：深色模式禁止闪白底。
          placeholder: (context, url) => KeyedSubtree(
            key: appImageLoadPlaceholderKey,
            child:
                placeholder ??
                Container(color: AppColors.iosGroupedSurface(context)),
          ),
          errorWidget: (context, url, error) {
            final nextIndex = index + 1;
            if (nextIndex < candidates.length) {
              return _buildCandidateImage(
                context,
                ref,
                candidates,
                nextIndex,
                cycle,
              );
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
            _recordTerminalMediaLoad(
              ref: ref,
              cycle: cycle,
              result: 'failure',
              error: error,
              candidatesTried: candidates.length,
            );
            onLoadFailed?.call(error);
            return KeyedSubtree(
              key: appImageLoadErrorKey,
              child: errorWidget ?? _buildErrorWidget(context),
            );
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
          color: AppColors.iosGroupedSurface(context),
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

class _ImageLoadFailureReporter extends StatefulWidget {
  const _ImageLoadFailureReporter({
    super.key,
    required this.child,
    this.onReport,
  });

  final Widget child;
  final VoidCallback? onReport;

  @override
  State<_ImageLoadFailureReporter> createState() =>
      _ImageLoadFailureReporterState();
}

class _ImageLoadFailureReporterState extends State<_ImageLoadFailureReporter> {
  bool _reported = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || _reported) {
        return;
      }
      _reported = true;
      widget.onReport?.call();
    });
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
