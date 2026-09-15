import 'package:quwoquan_app/runtime/di/public_media_delivery_dependencies.dart';

import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/domain/signed_media_delivery_lease.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/platform/media/app_image_cache_controller.dart';
import 'package:quwoquan_app/runtime/transport/media/media_load_failure_cache.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/runtime/observability/trackers/page_lifecycle_observability.dart';
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
    this.successSemanticIdentifier,
  });

  final String imageUrl;
  final double size;
  final BoxFit fit;
  final Widget? placeholder;
  final Widget? errorWidget;
  final VoidCallback? onLoadSucceeded;
  final void Function(Object error)? onLoadFailed;
  final String? successSemanticIdentifier;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return AppCachedNetworkImage(
      imageUrl: imageUrl,
      width: size,
      height: size,
      fit: fit,
      cdnPreset: CdnImagePreset.avatar,
      placeholder: placeholder,
      errorWidget: errorWidget,
      onLoadSucceeded: onLoadSucceeded,
      onLoadFailed: onLoadFailed,
      successSemanticIdentifier: successSemanticIdentifier,
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
    final normalizedUrl = imageUrl ?? '';
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
  final MediaDeliveryKind mediaKind;
  final Widget Function(BuildContext context, ImageProvider imageProvider)?
  imageBuilder;
  final DateTime Function()? now;

  /// 仅真实解码成功时发布的对象级语义；占位和失败不携带该身份。
  final String? successSemanticIdentifier;

  /// 稳定缓存键（可选）。默认 null 时沿用完整 URL 作缓存键，行为不变。
  /// 短签 URL（signed grant）场景必须传入稳定资产身份
  /// （SignedMediaDeliveryLease.cacheIdentity）：签名 query 随 TTL 轮换，
  /// 用完整 URL 作键会导致每次换签都重新下载与解码。
  /// 仅作用于首个候选 URL；候选回退指向不同资产字节，不能共享同一键。
  final String? cacheKey;
  final SignedMediaDeliveryLease? lease;

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
    this.mediaKind = MediaDeliveryKind.image,
    this.imageBuilder,
    this.cacheKey,
    this.lease,
    this.now,
    this.successSemanticIdentifier,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final candidates = imageUrl.isEmpty ? const <String>[] : <String>[imageUrl];
    return _ImageLoadCycleScope(
      sourceIdentity: imageUrl,
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
    PageLifecycleObservability? observability,
  }) {
    if (!cycle.markTerminal()) {
      return;
    }
    (observability ??
            ref.read<PageLifecycleObservability>(
              pageLifecycleObservabilityProvider,
            ))
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
    final observability = ref.read(pageLifecycleObservabilityProvider);
    ImageProvider<Object> verified;
    try {
      verified = ref
          .watch(publicMediaDeliveryProvider)
          .imageProvider(
            candidates[index],
            profile: cdnPreset,
            kind: mediaKind,
            cacheKey: cacheKey,
            lease: lease,
          );
    } catch (error) {
      return _ImageLoadFailureReporter(
        key: ObjectKey(cycle),
        onReport: () {
          _recordTerminalMediaLoad(
            ref: ref,
            cycle: cycle,
            result: 'failure',
            candidatesTried: 1,
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
    return LayoutBuilder(
      builder: (context, constraints) {
        int? extent(double? explicit, double bound) {
          final logical = explicit ?? bound;
          if (!logical.isFinite || logical <= 0) return null;
          return (logical * MediaQuery.devicePixelRatioOf(context))
              .round()
              .clamp(1, appImageDecodeMaxPhysicalExtent);
        }

        final resized = ResizeImage.resizeIfNeeded(
          extent(width, constraints.maxWidth),
          extent(height, constraints.maxHeight),
          verified,
        );
        return Image(
          image: resized,
          fit: fit,
          width: width,
          height: height,
          frameBuilder: (context, child, frame, synchronous) {
            if (frame == null) {
              return KeyedSubtree(
                key: appImageLoadPlaceholderKey,
                child: placeholder ?? const SizedBox.shrink(),
              );
            }
            MediaLoadFailureCache.instance.clearIdentity(candidates[index]);
            _recordTerminalMediaLoad(
              ref: ref,
              cycle: cycle,
              result: 'success',
              candidatesTried: 1,
            );
            final decoded = Semantics(
              identifier:
                  successSemanticIdentifier ?? appImageLoadSuccessKey.value,
              image: true,
              child: KeyedSubtree(
                key: appImageLoadSuccessKey,
                child: imageBuilder?.call(context, verified) ?? child,
              ),
            );
            return onLoadSucceeded == null
                ? decoded
                : _ImageLoadSuccessReporter(
                    reportKey: candidates[index],
                    onReport: onLoadSucceeded!,
                    child: decoded,
                  );
          },
          errorBuilder: (context, error, stackTrace) =>
              _ImageLoadFailureReporter(
                key: ObjectKey(cycle),
                onReport: () {
                  MediaLoadFailureCache.instance.recordFailure(
                    candidates[index],
                    error: error,
                    candidateUrl: candidates[index],
                  );
                  _recordTerminalMediaLoad(
                    ref: ref,
                    observability: observability,
                    cycle: cycle,
                    result: 'failure',
                    candidatesTried: 1,
                    error: error,
                  );
                  onLoadFailed?.call(error);
                },
                child: KeyedSubtree(
                  key: appImageLoadErrorKey,
                  child: errorWidget ?? _buildErrorWidget(context),
                ),
              ),
        );
      },
    );
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
