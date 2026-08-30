import 'dart:async';
import 'package:quwoquan_app/runtime/di/media_delivery_composition.dart';
import 'dart:ui' as ui;

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart' show listEquals;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/di/signed_media_delivery_dependencies.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart'
    show MediaDeliveryKind;
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show MediaDeliveryAccessMode;
import 'package:quwoquan_app/service/content_service/media/media_asset/adapters/cdn_image_url_builder.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/image_book_page_surface.dart';
import 'package:quwoquan_app/design_system/gestures/immersive_gesture_intent_controller.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/media_page_flip_book.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/immersive_media_failure_content.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/spacing/immersive_media_wait_motion.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/runtime/shell/loading/app_request_wait_controller.dart';
import 'package:quwoquan_app/runtime/transport/media/content_media_url.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';

typedef ImageBookImageLoader = ImageBookImageLoadOperation Function({
  required BuildContext context,
  required int pageIndex,
  required List<String> candidates,
  required Size pageSize,
});

abstract interface class ImageBookImageLoadOperation {
  Future<ImageBookImageLoadResult> get result;
  int get candidatesTried;
  void cancel();
}

@immutable
class ImageBookImageLoadResult {
  const ImageBookImageLoadResult({
    required this.image,
    required this.candidatesTried,
  });

  final ui.Image image;
  final int candidatesTried;
}

@immutable
class ImageBookMediaLoadEvent {
  const ImageBookMediaLoadEvent({
    required this.result,
    required this.durationMs,
    required this.candidatesTried,
    this.error,
  });

  final String result;
  final int durationMs;
  final int candidatesTried;
  final Object? error;
}

/// 图片作品的书页式沉浸画布。
///
/// 每页只保留一条解码链；静态页和翻页纹理共享同一个 [ui.Image] 与 cover
/// source rect，避免图片晚到时发生裁剪或亮度切换。
///
/// 每页的取址形态由 typed 交付绑定决定（DEC-033）：公开页走候选推导 + CDN
/// cover 变体，私有页由 SignedMediaDeliveryCoordinator 兑换短签地址后单候选
/// 直传，短签地址不进入候选推导也不经 CDN 变体处理器。本画布不从 URL 形态
/// 反推交付形态，也不在私有页失败时回退公开 URL。
class ImageBookCanvas extends ConsumerStatefulWidget {
  const ImageBookCanvas({
    super.key,
    required this.deliveries,
    required this.onImageChanged,
    this.initialIndex = 0,
    this.onPageflipMotion,
    this.onOverflowPrevious,
    this.onOverflowNext,
    this.gestureIntentController,
    this.imageLoader,
    this.onMediaLoad,
    DateTime Function()? now,
  }) : _now = now ?? DateTime.now;

  /// 逐页 typed 交付绑定。顺序即页序。
  final List<MediaDeliveryBinding> deliveries;
  final int initialIndex;
  final ValueChanged<int> onImageChanged;
  final ValueChanged<MediaPageFlipMotionEvent>? onPageflipMotion;
  final VoidCallback? onOverflowPrevious;
  final VoidCallback? onOverflowNext;
  final ImmersiveGestureIntentController? gestureIntentController;
  final ImageBookImageLoader? imageLoader;
  final ValueChanged<ImageBookMediaLoadEvent>? onMediaLoad;
  final DateTime Function() _now;

  @override
  ConsumerState<ImageBookCanvas> createState() => _ImageBookCanvasState();
}

class _ImageBookCanvasState extends ConsumerState<ImageBookCanvas> {
  static const ImageBookPageSurfaceFactory _pageSurfaceFactory =
      ImageBookPageSurfaceFactory();

  final Map<int, _ImageBookPageResource> _resources =
      <int, _ImageBookPageResource>{};

  late int _currentIndex;
  int _textureRevision = 0;
  int _presentationReleaseGeneration = 0;
  bool _presentationFrozen = false;
  Object? _scheduledWindowSignature;

  int get _safeInitialIndex {
    if (widget.deliveries.length <= 1) {
      return 0;
    }
    return widget.initialIndex.clamp(0, widget.deliveries.length - 1).toInt();
  }

  @override
  void initState() {
    super.initState();
    _currentIndex = _safeInitialIndex;
  }

  @override
  void didUpdateWidget(covariant ImageBookCanvas oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!listEquals(widget.deliveries, oldWidget.deliveries)) {
      _disposeResources();
      _textureRevision += 1;
      _scheduledWindowSignature = null;
    }
    final nextInitialIndex = _safeInitialIndex;
    if (widget.initialIndex != oldWidget.initialIndex &&
        nextInitialIndex != _currentIndex) {
      _currentIndex = nextInitialIndex;
      _scheduledWindowSignature = null;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) {
          widget.onImageChanged(_currentIndex);
        }
      });
    }
  }

  @override
  void dispose() {
    _disposeResources();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final images = widget.deliveries;
    if (images.isEmpty) {
      return const ColoredBox(color: AppColors.worksBackground);
    }
    return LayoutBuilder(
      builder: (context, constraints) {
        final pageSize = Size(
          constraints.maxWidth.isFinite && constraints.maxWidth > 0
              ? constraints.maxWidth
              : MediaQuery.sizeOf(context).width,
          constraints.maxHeight.isFinite && constraints.maxHeight > 0
              ? constraints.maxHeight
              : MediaQuery.sizeOf(context).height,
        );
        _scheduleLoadWindow(images, pageSize);
        return Stack(
          fit: StackFit.expand,
          children: <Widget>[
            MediaPageFlipBook(
              key: const ValueKey('works-photo-book-stage'),
              pageCount: images.length,
              initialPage: _currentIndex.clamp(0, images.length - 1),
              contentSignature: Object.hashAll(images),
              textureReadinessSignature: _textureRevision,
              textureSnapshotBuilder: (context, index, size, pixelRatio) {
                return _buildTexturePair(
                  context: context,
                  pageIndex: index,
                  binding: images[index],
                  pageSize: size,
                  pixelRatio: pixelRatio,
                );
              },
              stageColor: AppColors.worksBackground,
              onPageChanged: (index) =>
                  _handlePageChanged(index, images, pageSize),
              onMotionEvent: widget.onPageflipMotion,
              onTextureTransactionActiveChanged:
                  _handleTextureTransactionActiveChanged,
              onOverflowPrevious: widget.onOverflowPrevious,
              onOverflowNext: widget.onOverflowNext,
              gestureIntentController: widget.gestureIntentController,
              pageBuilder: (context, index) {
                final resource = _resources[index];
                final reduceMotion = _reduceMotionEnabled;
                // 滞回转场（REQ-020）：指示出现过则经交叉淡出呈现，
                // 静默期内完成用快速淡入，感知为瞬时且无硬切。
                final indicatorShown =
                    resource?.presentedLoadingOverlayReady ?? false;
                return _ImageBookPage(
                  key: ValueKey<String>('image-book-page-$index'),
                  resource: resource,
                  coverSourceRect: resource?.image == null
                      ? null
                      : _pageSurfaceFactory.coverSourceRect(
                          resource!.image!,
                          pageSize,
                        ),
                  hideStatusOverlay: _presentationFrozen,
                  fadeDuration: reduceMotion
                      ? ImmersiveMediaWaitMotion.reducedMotionTransition
                      : indicatorShown
                      ? ImmersiveMediaWaitMotion.crossFade
                      : ImmersiveMediaWaitMotion.quickReveal,
                  reduceMotion: reduceMotion,
                  onRetry: () => _retryPage(
                    index: index,
                    binding: images[index],
                    pageSize: pageSize,
                  ),
                );
              },
            ),
            const Positioned.fill(
              child: IgnorePointer(child: _ImageBookReadabilityOverlay()),
            ),
          ],
        );
      },
    );
  }

  DateTime get _now => widget._now();

  bool get _reduceMotionEnabled {
    return MediaQuery.maybeOf(context)?.disableAnimations ??
        WidgetsBinding
            .instance
            .platformDispatcher
            .accessibilityFeatures
            .disableAnimations;
  }

  void _scheduleLoadWindow(List<MediaDeliveryBinding> images, Size pageSize) {
    final signature = Object.hash(
      _currentIndex,
      pageSize.width.round(),
      pageSize.height.round(),
      Object.hashAll(images),
    );
    if (_scheduledWindowSignature == signature) {
      return;
    }
    _scheduledWindowSignature = signature;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      _ensureLoadWindow(images, pageSize);
    });
  }

  void _handlePageChanged(
    int index,
    List<MediaDeliveryBinding> images,
    Size pageSize,
  ) {
    final changed = index != _currentIndex;
    _currentIndex = index;
    _scheduledWindowSignature = null;
    _ensureLoadWindow(images, pageSize);
    if (changed) {
      setState(() {});
    }
    widget.onImageChanged(index);
  }

  void _handleTextureTransactionActiveChanged(bool active) {
    if (_presentationFrozen == active) {
      return;
    }
    final releaseGeneration = ++_presentationReleaseGeneration;
    _presentationFrozen = active;
    if (mounted) {
      setState(() {});
    }
    if (active) {
      return;
    }
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted ||
          _presentationFrozen ||
          releaseGeneration != _presentationReleaseGeneration) {
        return;
      }
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted ||
            _presentationFrozen ||
            releaseGeneration != _presentationReleaseGeneration) {
          return;
        }
        var presentationChanged = false;
        for (final resource in _resources.values) {
          if (!resource.presentationDirty) {
            continue;
          }
          resource.applyPresentation();
          presentationChanged = true;
        }
        if (presentationChanged) {
          setState(() {});
        }
      });
      WidgetsBinding.instance.scheduleFrame();
    });
  }

  void _ensureLoadWindow(List<MediaDeliveryBinding> images, Size pageSize) {
    final retained = <int>{_currentIndex - 1, _currentIndex, _currentIndex + 1}
      ..removeWhere((index) => index < 0 || index >= images.length);
    for (final index in retained) {
      _ensurePageLoad(
        index: index,
        binding: images[index],
        pageSize: pageSize,
      );
    }
    for (final index in _resources.keys.toList(growable: false)) {
      if (!retained.contains(index)) {
        _resources.remove(index)?.dispose();
      }
    }
  }

  Future<MediaPageFlipTexturePair?> _buildTexturePair({
    required BuildContext context,
    required int pageIndex,
    required MediaDeliveryBinding binding,
    required Size pageSize,
    required double pixelRatio,
  }) async {
    _ensurePageLoad(index: pageIndex, binding: binding, pageSize: pageSize);
    final resource = _resources[pageIndex];
    if (resource == null ||
        resource.availability == _ImageBookPageAvailability.pending) {
      return _pageSurfaceFactory.buildNeutralTexture(
        pageSize: pageSize,
        pixelRatio: pixelRatio,
      );
    }
    final image = resource.image;
    if (resource.availability == _ImageBookPageAvailability.failed ||
        image == null) {
      return _pageSurfaceFactory.buildNeutralTexture(
        pageSize: pageSize,
        pixelRatio: pixelRatio,
      );
    }
    return _pageSurfaceFactory.rasterizeImageTexture(
      image: image,
      pageSize: pageSize,
      pixelRatio: pixelRatio,
    );
  }

  void _ensurePageLoad({
    required int index,
    required MediaDeliveryBinding binding,
    required Size pageSize,
    bool force = false,
    bool immediateIndicator = false,
  }) {
    final resource = _resources.putIfAbsent(
      index,
      () => _ImageBookPageResource(binding),
    );
    final signed = binding.isSignedGrant;
    // 私有页的地址要等 grant 兑换才有，候选推导只服务公开页；短签地址不进入
    // 候选推导也不经 CDN 变体，否则签名会被改写。
    final candidates = signed
        ? const <String>[]
        : _processedCoverCandidates(binding.publicUrl);
    if (binding.isSignedGrantWithoutAsset) {
      // 投影声明私有却没有资产身份：自相矛盾，落显式判否，不回退公开 URL。
      _presentContradictoryBinding(index: index, resource: resource);
      return;
    }
    if (!signed && candidates.isEmpty) {
      if (resource.availability == _ImageBookPageAvailability.absent) {
        return;
      }
      resource
        ..cancelWaitTimers()
        ..cancelActiveLoad()
        ..loadInFlight = false
        ..availability = _ImageBookPageAvailability.absent
        ..error = null
        ..applyPresentation();
      _textureRevision += 1;
      widget.onMediaLoad?.call(
        const ImageBookMediaLoadEvent(
          result: 'absent',
          durationMs: 0,
          candidatesTried: 0,
        ),
      );
      return;
    }
    if (!force &&
        (resource.loadInFlight ||
            resource.availability != _ImageBookPageAvailability.pending)) {
      return;
    }
    resource
      ..cancelWaitTimers()
      ..cancelActiveLoad()
      ..loadInFlight = true
      ..loadingOverlayReady = immediateIndicator
      ..indicatorShownAt = immediateIndicator ? _now : null
      ..slowHintReady = false
      ..error = null
      ..generation += 1;
    if (!resource.presentationDirty) {
      resource.applyPresentation();
    }
    final generation = resource.generation;
    final startedAt = _now;
    bool stale() =>
        !mounted ||
        _resources[index] != resource ||
        resource.generation != generation ||
        resource.availability != _ImageBookPageAvailability.pending;

    if (!immediateIndicator) {
      resource.loadingTimer = Timer(
        ImmersiveMediaWaitMotion.imageIndicatorDelay,
        () {
          if (stale()) {
            return;
          }
          resource
            ..loadingOverlayReady = true
            ..indicatorShownAt = _now;
          _syncPresentation(resource);
        },
      );
    }
    resource.slowHintTimer = Timer(AppRequestWaitTimings.blockedSlowHint, () {
      if (stale()) {
        return;
      }
      resource.slowHintReady = true;
      _syncPresentation(resource);
    });
    resource.deadlineTimer = Timer(
      AppRequestWaitTimings.foregroundReadDeadline,
      () {
        if (stale() || resource.pendingReadyImage != null) {
          return;
        }
        final candidatesTried = resource.activeLoad?.candidatesTried ?? 0;
        resource.generation += 1;
        resource
          ..cancelWaitTimers()
          ..cancelActiveLoad()
          ..loadInFlight = false
          ..availability = _ImageBookPageAvailability.failed
          ..error = TimeoutException(
            'image book load deadline exceeded',
            AppRequestWaitTimings.foregroundReadDeadline,
          );
        _textureRevision += 1;
        _syncPresentation(resource);
        widget.onMediaLoad?.call(
          ImageBookMediaLoadEvent(
            result: 'timeout',
            durationMs:
                AppRequestWaitTimings.foregroundReadDeadline.inMilliseconds,
            candidatesTried: candidatesTried,
          ),
        );
      },
    );
    if (signed) {
      unawaited(
        _loadSignedPage(
          index: index,
          resource: resource,
          generation: generation,
          binding: binding,
          pageSize: pageSize,
          startedAt: startedAt,
          forceResign: force,
        ),
      );
      return;
    }
    _startPageOperation(
      index: index,
      resource: resource,
      generation: generation,
      candidates: candidates,
      pageSize: pageSize,
      startedAt: startedAt,
    );
  }

  void _startPageOperation({
    required int index,
    required _ImageBookPageResource resource,
    required int generation,
    required List<String> candidates,
    required Size pageSize,
    required DateTime startedAt,
  }) {
    final operation =
        widget.imageLoader?.call(
          context: context,
          pageIndex: index,
          candidates: candidates,
          pageSize: pageSize,
        ) ??
        _DefaultImageBookImageLoadOperation(
          context: context,
          candidates: candidates,
          pageSize: pageSize,
        );
    resource.activeLoad = operation;
    unawaited(
      _loadPage(
        index: index,
        resource: resource,
        generation: generation,
        operation: operation,
        startedAt: startedAt,
      ),
    );
  }

  /// 私有页的解码链：先经 coordinator 兑换短签地址，再进入同一条解码/呈现链。
  ///
  /// 兑换耗时计入本页等待窗口（指示延迟、慢提示与读取死线都已在调用方开启），
  /// 因此私有页与公开页的等待观感一致。用户驱动的重试走强制换签：旧签名已被
  /// 交付边缘拒绝，复用缓存只会重复失败。
  Future<void> _loadSignedPage({
    required int index,
    required _ImageBookPageResource resource,
    required int generation,
    required MediaDeliveryBinding binding,
    required Size pageSize,
    required DateTime startedAt,
    required bool forceResign,
  }) async {
    final coordinator = ref.read(signedMediaDeliveryCoordinatorProvider);
    bool stale() =>
        !mounted ||
        _resources[index] != resource ||
        resource.generation != generation;
    try {
      final lease = forceResign
          ? await coordinator.refresh(
              assetId: binding.assetId,
              kind: MediaDeliveryKind.image,
            )
          : await coordinator.resolve(
              assetId: binding.assetId,
              kind: MediaDeliveryKind.image,
              accessMode: MediaDeliveryAccessMode.signedGrant,
            );
      if (stale()) {
        return;
      }
      _startPageOperation(
        index: index,
        resource: resource,
        generation: generation,
        // 短签地址单候选直传：不推导候选，不经 CDN 变体。
        candidates: <String>[lease.deliveryUri.toString()],
        pageSize: pageSize,
        startedAt: startedAt,
      );
    } on Object catch (error) {
      if (stale()) {
        return;
      }
      resource
        ..cancelWaitTimers()
        ..cancelActiveLoad()
        ..loadInFlight = false
        ..availability = _ImageBookPageAvailability.failed
        ..error = error;
      _textureRevision += 1;
      _syncPresentation(resource);
      widget.onMediaLoad?.call(
        ImageBookMediaLoadEvent(
          result: 'failure',
          error: error,
          durationMs: _now.difference(startedAt).inMilliseconds,
          candidatesTried: 0,
        ),
      );
    }
  }

  void _presentContradictoryBinding({
    required int index,
    required _ImageBookPageResource resource,
  }) {
    final error = StateError(
      'image book page $index declares signed_grant delivery without an asset id',
    );
    if (resource.availability == _ImageBookPageAvailability.failed) {
      return;
    }
    resource
      ..cancelWaitTimers()
      ..cancelActiveLoad()
      ..loadInFlight = false
      ..availability = _ImageBookPageAvailability.failed
      ..error = error
      ..applyPresentation();
    _textureRevision += 1;
    widget.onMediaLoad?.call(
      ImageBookMediaLoadEvent(
        result: 'failure',
        error: error,
        durationMs: 0,
        candidatesTried: 0,
      ),
    );
  }

  Future<void> _loadPage({
    required int index,
    required _ImageBookPageResource resource,
    required int generation,
    required ImageBookImageLoadOperation operation,
    required DateTime startedAt,
  }) async {
    try {
      final result = await operation.result;
      final durationMs = _now.difference(startedAt).inMilliseconds;
      if (!mounted ||
          _resources[index] != resource ||
          resource.generation != generation) {
        result.image.dispose();
        return;
      }
      resource.activeLoad = null;

      void present() {
        resource
          ..cancelWaitTimers()
          ..loadInFlight = false
          ..availability = _ImageBookPageAvailability.ready
          ..image?.dispose()
          ..image = result.image
          ..pendingReadyImage = null
          ..error = null;
        _textureRevision += 1;
        _syncPresentation(resource);
        widget.onMediaLoad?.call(
          ImageBookMediaLoadEvent(
            result: 'success',
            durationMs: durationMs,
            candidatesTried: result.candidatesTried,
          ),
        );
      }

      final indicatorShownAt = resource.indicatorShownAt;
      if (indicatorShownAt == null) {
        present();
        return;
      }
      final remaining = ImmersiveMediaWaitMotion.remainingIndicatorDisplay(
        indicatorShownAt,
        now: _now,
      );
      if (remaining <= Duration.zero) {
        present();
        return;
      }
      resource
        ..pendingReadyImage = result.image
        ..slowHintTimer?.cancel()
        ..deadlineTimer?.cancel();
      resource.minDisplayTimer?.cancel();
      resource.minDisplayTimer = Timer(remaining, () {
        if (!mounted ||
            _resources[index] != resource ||
            resource.generation != generation) {
          return;
        }
        present();
      });
    } catch (error) {
      final durationMs = _now.difference(startedAt).inMilliseconds;
      final candidatesTried = operation.candidatesTried;
      if (!mounted ||
          _resources[index] != resource ||
          resource.generation != generation) {
        return;
      }
      resource.activeLoad = null;

      void presentFailure() {
        if (!mounted ||
            _resources[index] != resource ||
            resource.generation != generation) {
          return;
        }
        resource
          ..cancelWaitTimers()
          ..loadInFlight = false
          ..availability = _ImageBookPageAvailability.failed
          ..error = error;
        _textureRevision += 1;
        _syncPresentation(resource);
        widget.onMediaLoad?.call(
          ImageBookMediaLoadEvent(
            result: 'failure',
            error: error,
            durationMs: durationMs,
            candidatesTried: candidatesTried,
          ),
        );
      }

      final indicatorShownAt = resource.indicatorShownAt;
      final remaining = indicatorShownAt == null
          ? Duration.zero
          : ImmersiveMediaWaitMotion.remainingIndicatorDisplay(
              indicatorShownAt,
              now: _now,
            );
      if (remaining <= Duration.zero) {
        presentFailure();
        return;
      }
      resource
        ..slowHintTimer?.cancel()
        ..deadlineTimer?.cancel();
      resource.minDisplayTimer?.cancel();
      resource.minDisplayTimer = Timer(remaining, presentFailure);
    }
  }

  void _syncPresentation(_ImageBookPageResource resource) {
    if (_presentationFrozen) {
      resource.presentationDirty = true;
    } else {
      resource.applyPresentation();
    }
    if (mounted) {
      setState(() {});
    }
  }

  void _retryPage({
    required int index,
    required MediaDeliveryBinding binding,
    required Size pageSize,
  }) {
    final resource = _resources[index];
    if (resource == null) {
      return;
    }
    resource
      ..cancelWaitTimers()
      ..cancelActiveLoad()
      ..image?.dispose()
      ..image = null
      ..availability = _ImageBookPageAvailability.pending
      ..error = null
      ..loadingOverlayReady = false
      ..slowHintReady = false
      ..indicatorShownAt = null
      ..applyPresentation();
    _textureRevision += 1;
    widget.onMediaLoad?.call(
      const ImageBookMediaLoadEvent(
        result: 'retry',
        durationMs: 0,
        candidatesTried: 0,
      ),
    );
    setState(() {});
    _ensurePageLoad(
      index: index,
      binding: binding,
      pageSize: pageSize,
      force: true,
      immediateIndicator: true,
    );
  }

  List<String> _processedCoverCandidates(String imageUrl) {
    final processed = <String>[];
    for (final candidate in resolveContentMediaUrlCandidates(imageUrl)) {
      final normalized = candidate.trim();
      final uri = Uri.tryParse(normalized);
      if (uri == null || uri.scheme != 'https' || uri.host.isEmpty) {
        continue;
      }
      final coverUrl = CdnImageUrlBuilder.cover(normalized);
      if (!processed.contains(coverUrl)) {
        processed.add(coverUrl);
      }
    }
    return processed;
  }

  void _disposeResources() {
    for (final resource in _resources.values) {
      resource.dispose();
    }
    _resources.clear();
  }
}

final class _DefaultImageBookImageLoadOperation
    implements ImageBookImageLoadOperation {
  _DefaultImageBookImageLoadOperation({
    required this.context,
    required List<String> candidates,
    required this.pageSize,
  }) : candidates = List<String>.unmodifiable(candidates) {
    unawaited(_run());
  }

  final BuildContext context;
  final List<String> candidates;
  final Size pageSize;
  final Completer<ImageBookImageLoadResult> _resultCompleter =
      Completer<ImageBookImageLoadResult>();

  ImageStream? _activeStream;
  ImageStreamListener? _activeListener;
  Completer<ui.Image>? _activeCandidateCompleter;
  bool _cancelled = false;
  int _candidatesTried = 0;

  @override
  Future<ImageBookImageLoadResult> get result => _resultCompleter.future;

  @override
  int get candidatesTried => _candidatesTried;

  Future<void> _run() async {
    Object? lastError;
    StackTrace? lastStackTrace;
    for (final candidate in candidates) {
      if (_cancelled) {
        return;
      }
      _candidatesTried += 1;
      try {
        final image = await _resolveCandidate(candidate);
        if (_cancelled) {
          image.dispose();
          return;
        }
        if (!_resultCompleter.isCompleted) {
          _resultCompleter.complete(
            ImageBookImageLoadResult(
              image: image,
              candidatesTried: _candidatesTried,
            ),
          );
        } else {
          image.dispose();
        }
        return;
      } catch (error, stackTrace) {
        if (_cancelled) {
          return;
        }
        lastError = error;
        lastStackTrace = stackTrace;
      }
    }
    if (!_resultCompleter.isCompleted) {
      _resultCompleter.completeError(
        lastError ?? StateError('image book has no loadable candidates'),
        lastStackTrace ?? StackTrace.current,
      );
    }
  }

  Future<ui.Image> _resolveCandidate(String candidate) {
    final completer = Completer<ui.Image>();
    final provider = CachedNetworkImageProvider(
      candidate,
      cacheManager: AppImageCacheController.cacheManagerForPreset(
        CdnImagePreset.cover,
      ),
    );
    final stream = provider.resolve(
      createLocalImageConfiguration(context, size: pageSize),
    );
    late final ImageStreamListener listener;
    listener = ImageStreamListener(
      (ImageInfo info, bool synchronousCall) {
        _detachCandidate(stream, listener, completer);
        final image = info.image.clone();
        if (!completer.isCompleted) {
          completer.complete(image);
        } else {
          image.dispose();
        }
      },
      onError: (Object error, StackTrace? stackTrace) {
        _detachCandidate(stream, listener, completer);
        if (!completer.isCompleted) {
          completer.completeError(error, stackTrace);
        }
      },
    );
    _activeStream = stream;
    _activeListener = listener;
    _activeCandidateCompleter = completer;
    stream.addListener(listener);
    return completer.future;
  }

  void _detachCandidate(
    ImageStream stream,
    ImageStreamListener listener,
    Completer<ui.Image> completer,
  ) {
    stream.removeListener(listener);
    if (identical(_activeStream, stream) &&
        identical(_activeListener, listener) &&
        identical(_activeCandidateCompleter, completer)) {
      _activeStream = null;
      _activeListener = null;
      _activeCandidateCompleter = null;
    }
  }

  @override
  void cancel() {
    if (_cancelled) {
      return;
    }
    _cancelled = true;
    final stream = _activeStream;
    final listener = _activeListener;
    final candidateCompleter = _activeCandidateCompleter;
    if (stream != null && listener != null) {
      stream.removeListener(listener);
    }
    _activeStream = null;
    _activeListener = null;
    _activeCandidateCompleter = null;
    const cancellation = _ImageBookImageLoadCancelled();
    if (candidateCompleter != null && !candidateCompleter.isCompleted) {
      candidateCompleter.completeError(cancellation, StackTrace.current);
    }
    if (!_resultCompleter.isCompleted) {
      _resultCompleter.completeError(cancellation, StackTrace.current);
    }
  }
}

final class _ImageBookImageLoadCancelled implements Exception {
  const _ImageBookImageLoadCancelled();
}

enum _ImageBookPageAvailability { pending, ready, failed, absent }

class _ImageBookPageResource {
  _ImageBookPageResource(this.binding);

  final MediaDeliveryBinding binding;
  _ImageBookPageAvailability availability = _ImageBookPageAvailability.pending;
  _ImageBookPageAvailability presentedAvailability =
      _ImageBookPageAvailability.pending;
  ui.Image? image;

  /// 滞回最短展示窗口内暂存的已解码图（REQ-020）：指示保持满窗口后呈现。
  ui.Image? pendingReadyImage;
  ImageBookImageLoadOperation? activeLoad;
  Object? error;
  Object? presentedError;
  Timer? loadingTimer;
  Timer? slowHintTimer;
  Timer? deadlineTimer;
  Timer? minDisplayTimer;
  DateTime? indicatorShownAt;
  bool loadInFlight = false;
  bool loadingOverlayReady = false;
  bool presentedLoadingOverlayReady = false;
  bool slowHintReady = false;
  bool presentedSlowHintReady = false;
  bool presentationDirty = false;
  int generation = 0;

  void applyPresentation() {
    presentedAvailability = availability;
    presentedError = error;
    presentedLoadingOverlayReady = loadingOverlayReady;
    presentedSlowHintReady = slowHintReady;
    presentationDirty = false;
  }

  void cancelWaitTimers() {
    loadingTimer?.cancel();
    slowHintTimer?.cancel();
    deadlineTimer?.cancel();
    minDisplayTimer?.cancel();
  }

  void cancelActiveLoad() {
    activeLoad?.cancel();
    activeLoad = null;
  }

  void dispose() {
    generation += 1;
    cancelWaitTimers();
    cancelActiveLoad();
    image?.dispose();
    image = null;
    pendingReadyImage?.dispose();
    pendingReadyImage = null;
  }
}

class _ImageBookPage extends StatelessWidget {
  const _ImageBookPage({
    super.key,
    required this.resource,
    required this.coverSourceRect,
    required this.hideStatusOverlay,
    required this.fadeDuration,
    required this.reduceMotion,
    required this.onRetry,
  });

  final _ImageBookPageResource? resource;
  final Rect? coverSourceRect;
  final bool hideStatusOverlay;
  final Duration fadeDuration;
  final bool reduceMotion;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final availability =
        resource?.presentedAvailability ?? _ImageBookPageAvailability.pending;
    final image = availability == _ImageBookPageAvailability.ready
        ? resource?.image
        : null;
    final showLoading =
        availability == _ImageBookPageAvailability.pending &&
        (resource?.presentedLoadingOverlayReady ?? false);
    final showFailure = availability == _ImageBookPageAvailability.failed;
    final showAbsent = availability == _ImageBookPageAvailability.absent;
    return ColoredBox(
      color: AppColors.imageBookPlaceholderBackdrop,
      child: Stack(
        fit: StackFit.expand,
        children: <Widget>[
          AnimatedOpacity(
            key: const ValueKey<String>('image-book-ready-fade'),
            opacity: image == null ? 0 : 1,
            duration: fadeDuration,
            curve: Curves.easeOut,
            child: image == null || coverSourceRect == null
                ? const SizedBox.expand()
                : CustomPaint(
                    key: const ValueKey<String>('image-book-decoded-surface'),
                    painter: _ImageBookDecodedPagePainter(
                      image: image,
                      sourceRect: coverSourceRect!,
                    ),
                    child: const SizedBox.expand(),
                  ),
          ),
          // 状态层滞回转场（REQ-020）：指示 200ms 淡入登场、250ms 交叉淡出
          // 退场，无硬切；翻页冻结期间整层立即隐藏，几何与纹理不受影响。
          if (!hideStatusOverlay)
            Positioned.fill(
              child: AnimatedSwitcher(
                duration: reduceMotion
                    ? ImmersiveMediaWaitMotion.reducedMotionTransition
                    : ImmersiveMediaWaitMotion.indicatorFadeIn,
                reverseDuration: reduceMotion
                    ? ImmersiveMediaWaitMotion.reducedMotionTransition
                    : ImmersiveMediaWaitMotion.crossFade,
                switchInCurve: Curves.easeOut,
                switchOutCurve: Curves.easeIn,
                child: showAbsent
                    ? const _ImageBookFailureOverlay(
                        key: ValueKey<String>('image-book-status-absent'),
                      )
                    : showFailure
                    ? _ImageBookFailureOverlay(
                        key: const ValueKey<String>('image-book-status-failed'),
                        onRetry: onRetry,
                      )
                    : showLoading
                    ? _ImageBookLoadingOverlay(
                        key: const ValueKey<String>(
                          'image-book-status-loading',
                        ),
                        slowHintVisible:
                            resource?.presentedSlowHintReady ?? false,
                        reduceMotion: reduceMotion,
                      )
                    : const SizedBox.shrink(
                        key: ValueKey<String>('image-book-status-idle'),
                      ),
              ),
            ),
        ],
      ),
    );
  }
}

class _ImageBookDecodedPagePainter extends CustomPainter {
  const _ImageBookDecodedPagePainter({
    required this.image,
    required this.sourceRect,
  });

  final ui.Image image;
  final Rect sourceRect;

  @override
  void paint(Canvas canvas, Size size) {
    canvas.drawImageRect(
      image,
      sourceRect,
      Offset.zero & size,
      Paint()
        ..isAntiAlias = false
        ..filterQuality = FilterQuality.medium,
    );
  }

  @override
  bool shouldRepaint(covariant _ImageBookDecodedPagePainter oldDelegate) {
    return oldDelegate.image != image || oldDelegate.sourceRect != sourceRect;
  }
}

class _ImageBookLoadingOverlay extends StatelessWidget {
  const _ImageBookLoadingOverlay({
    super.key,
    required this.slowHintVisible,
    required this.reduceMotion,
  });

  final bool slowHintVisible;
  final bool reduceMotion;

  @override
  Widget build(BuildContext context) {
    return Center(
      key: const ValueKey<String>('image-book-loading-overlay'),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Opacity(
            opacity: 0.36,
            child: AppRequestFeedback.inline(
              indicatorColor: AppColors.immersiveForeground,
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupSm),
          // 慢提示槽位常驻（REQ-020）：3s 时文字淡入，不引起布局重排。
          AnimatedOpacity(
            key: const ValueKey<String>('image-book-slow-hint'),
            opacity: slowHintVisible ? 1 : 0,
            duration: reduceMotion
                ? ImmersiveMediaWaitMotion.reducedMotionTransition
                : ImmersiveMediaWaitMotion.indicatorFadeIn,
            child: Text(
              FoundationText.requestWaitSlow,
              style: TextStyle(
                color: AppColors.immersiveForeground.withValues(alpha: 0.7),
                fontSize: AppTypography.sm,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ImageBookFailureOverlay extends StatelessWidget {
  const _ImageBookFailureOverlay({super.key, this.onRetry});

  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      key: const ValueKey<String>('image-book-failure-overlay'),
      child: ImmersiveMediaFailureContent(
        presentation: const MediaFailurePresentation(
          title: ContentText.imageLoadFailed,
        ),
        onRetry: onRetry,
        retryKey: const ValueKey<String>('image-book-retry'),
      ),
    );
  }
}

class _ImageBookReadabilityOverlay extends StatelessWidget {
  const _ImageBookReadabilityOverlay();

  @override
  Widget build(BuildContext context) {
    return Stack(
      fit: StackFit.expand,
      children: <Widget>[
        DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: <Color>[
                AppColors.black.withValues(alpha: 0.06),
                AppColors.black.withValues(alpha: 0.58),
              ],
            ),
          ),
        ),
        const Align(
          alignment: Alignment.bottomCenter,
          child: SizedBox(
            height: AppSpacing.hairline,
            child: ColoredBox(color: AppColors.imageBookReadabilityHairline),
          ),
        ),
      ],
    );
  }
}
