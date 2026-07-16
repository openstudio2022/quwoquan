import 'dart:async';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart' show listEquals;
import 'package:flutter/material.dart' show Icons;
import 'package:quwoquan_app/cloud/media/cdn_image_url_builder.dart';
import 'package:quwoquan_app/components/media/image/book/image_book_page_surface.dart';
import 'package:quwoquan_app/components/media/shared/gesture/immersive_gesture_intent_controller.dart';
import 'package:quwoquan_app/components/media/shared/pageflip/media_page_flip_book.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/media/content_media_url.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';

typedef ImageBookImageLoader =
    Future<ui.Image> Function({
      required BuildContext context,
      required int pageIndex,
      required List<String> candidates,
      required Size pageSize,
    });

@immutable
class ImageBookMediaLoadEvent {
  const ImageBookMediaLoadEvent({
    required this.result,
    this.error,
    this.durationMs,
    this.candidatesTried,
  });

  final String result;
  final Object? error;
  final int? durationMs;
  final int? candidatesTried;
}

/// 图片作品的书页式沉浸画布。
///
/// 每页只保留一条解码链；静态页和翻页纹理共享同一个 [ui.Image] 与 cover
/// source rect，避免图片晚到时发生裁剪或亮度切换。
class ImageBookCanvas extends StatefulWidget {
  const ImageBookCanvas({
    super.key,
    required this.imageUrls,
    required this.onImageChanged,
    this.initialIndex = 0,
    this.onPageflipMotion,
    this.onOverflowPrevious,
    this.onOverflowNext,
    this.gestureIntentController,
    this.imageLoader,
    this.onMediaLoad,
  });

  final List<String> imageUrls;
  final int initialIndex;
  final ValueChanged<int> onImageChanged;
  final ValueChanged<MediaPageFlipMotionEvent>? onPageflipMotion;
  final VoidCallback? onOverflowPrevious;
  final VoidCallback? onOverflowNext;
  final ImmersiveGestureIntentController? gestureIntentController;
  final ImageBookImageLoader? imageLoader;
  final ValueChanged<ImageBookMediaLoadEvent>? onMediaLoad;

  @override
  State<ImageBookCanvas> createState() => _ImageBookCanvasState();
}

class _ImageBookCanvasState extends State<ImageBookCanvas> {
  static const ImageBookPageSurfaceFactory _pageSurfaceFactory =
      ImageBookPageSurfaceFactory();
  static const Duration _loadingOverlayDelay = Duration(milliseconds: 300);
  static const Duration _imageFadeDuration = Duration(milliseconds: 160);
  static const Duration _reducedMotionImageFadeDuration = Duration(
    milliseconds: 120,
  );

  final Map<int, _ImageBookPageResource> _resources =
      <int, _ImageBookPageResource>{};

  late int _currentIndex;
  int _textureRevision = 0;
  int _presentationReleaseGeneration = 0;
  bool _presentationFrozen = false;
  Object? _scheduledWindowSignature;

  int get _safeInitialIndex {
    if (widget.imageUrls.length <= 1) {
      return 0;
    }
    return widget.initialIndex.clamp(0, widget.imageUrls.length - 1).toInt();
  }

  @override
  void initState() {
    super.initState();
    _currentIndex = _safeInitialIndex;
  }

  @override
  void didUpdateWidget(covariant ImageBookCanvas oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!listEquals(widget.imageUrls, oldWidget.imageUrls)) {
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
    final images = widget.imageUrls
        .map((url) => url.trim())
        .where((url) => url.isNotEmpty)
        .toList(growable: false);
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
                  imageUrl: images[index],
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
                  fadeDuration: _reduceMotionEnabled
                      ? _reducedMotionImageFadeDuration
                      : _imageFadeDuration,
                  onRetry: () => _retryPage(
                    index: index,
                    imageUrl: images[index],
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

  bool get _reduceMotionEnabled {
    return MediaQuery.maybeOf(context)?.disableAnimations ??
        WidgetsBinding
            .instance
            .platformDispatcher
            .accessibilityFeatures
            .disableAnimations;
  }

  void _scheduleLoadWindow(List<String> images, Size pageSize) {
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

  void _handlePageChanged(int index, List<String> images, Size pageSize) {
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

  void _ensureLoadWindow(List<String> images, Size pageSize) {
    final retained = <int>{_currentIndex - 1, _currentIndex, _currentIndex + 1}
      ..removeWhere((index) => index < 0 || index >= images.length);
    for (final index in retained) {
      _ensurePageLoad(
        index: index,
        imageUrl: images[index],
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
    required String imageUrl,
    required Size pageSize,
    required double pixelRatio,
  }) async {
    _ensurePageLoad(index: pageIndex, imageUrl: imageUrl, pageSize: pageSize);
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
    required String imageUrl,
    required Size pageSize,
    bool force = false,
  }) {
    final resource = _resources.putIfAbsent(
      index,
      () => _ImageBookPageResource(imageUrl),
    );
    if (!force &&
        (resource.loadInFlight ||
            resource.availability != _ImageBookPageAvailability.pending)) {
      return;
    }
    resource
      ..loadInFlight = true
      ..loadingOverlayReady = false
      ..error = null
      ..generation += 1;
    if (!resource.presentationDirty) {
      resource.applyPresentation();
    }
    final generation = resource.generation;
    resource.loadingTimer?.cancel();
    resource.loadingTimer = Timer(_loadingOverlayDelay, () {
      if (!mounted ||
          _resources[index] != resource ||
          resource.generation != generation ||
          resource.availability != _ImageBookPageAvailability.pending) {
        return;
      }
      resource.loadingOverlayReady = true;
      _syncPresentation(resource);
    });
    final candidates = _processedCoverCandidates(
      imageUrl,
      math.max(750, pageSize.width),
    );
    unawaited(
      _loadPage(
        context: context,
        index: index,
        resource: resource,
        generation: generation,
        candidates: candidates,
        pageSize: pageSize,
      ),
    );
  }

  Future<void> _loadPage({
    required BuildContext context,
    required int index,
    required _ImageBookPageResource resource,
    required int generation,
    required List<String> candidates,
    required Size pageSize,
  }) async {
    final startedAt = DateTime.now();
    try {
      final image =
          await (widget.imageLoader?.call(
                context: context,
                pageIndex: index,
                candidates: candidates,
                pageSize: pageSize,
              ) ??
              _loadFirstCandidate(context, candidates, pageSize));
      if (!mounted ||
          _resources[index] != resource ||
          resource.generation != generation) {
        image.dispose();
        return;
      }
      resource
        ..loadingTimer?.cancel()
        ..loadInFlight = false
        ..availability = _ImageBookPageAvailability.ready
        ..image?.dispose()
        ..image = image
        ..error = null;
      _textureRevision += 1;
      _syncPresentation(resource);
      widget.onMediaLoad?.call(
        ImageBookMediaLoadEvent(
          result: 'success',
          durationMs: DateTime.now().difference(startedAt).inMilliseconds,
          candidatesTried: candidates.length,
        ),
      );
    } catch (error) {
      if (!mounted ||
          _resources[index] != resource ||
          resource.generation != generation) {
        return;
      }
      resource
        ..loadingTimer?.cancel()
        ..loadInFlight = false
        ..availability = _ImageBookPageAvailability.failed
        ..error = error;
      _textureRevision += 1;
      _syncPresentation(resource);
      widget.onMediaLoad?.call(
        ImageBookMediaLoadEvent(
          result: 'failure',
          error: error,
          durationMs: DateTime.now().difference(startedAt).inMilliseconds,
          candidatesTried: candidates.length,
        ),
      );
    }
  }

  Future<ui.Image> _loadFirstCandidate(
    BuildContext context,
    List<String> candidates,
    Size pageSize,
  ) async {
    Object? lastError;
    for (final candidate in candidates) {
      try {
        return await _resolveImageProvider(
          context: context,
          provider: CachedNetworkImageProvider(
            candidate,
            cacheManager: AppImageCacheController.cacheManagerForPreset(
              CdnImagePreset.cover,
            ),
          ),
          pageSize: pageSize,
        );
      } catch (error) {
        lastError = error;
      }
    }
    throw lastError ?? StateError('image book has no loadable candidates');
  }

  Future<ui.Image> _resolveImageProvider({
    required BuildContext context,
    required ImageProvider provider,
    required Size pageSize,
  }) {
    final completer = Completer<ui.Image>();
    final stream = provider.resolve(
      createLocalImageConfiguration(context, size: pageSize),
    );
    late final ImageStreamListener listener;
    listener = ImageStreamListener(
      (ImageInfo info, bool synchronousCall) {
        stream.removeListener(listener);
        if (!completer.isCompleted) {
          completer.complete(info.image.clone());
        }
      },
      onError: (Object error, StackTrace? stackTrace) {
        stream.removeListener(listener);
        if (!completer.isCompleted) {
          completer.completeError(error, stackTrace);
        }
      },
    );
    stream.addListener(listener);
    return completer.future;
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
    required String imageUrl,
    required Size pageSize,
  }) {
    final resource = _resources[index];
    if (resource == null) {
      return;
    }
    resource
      ..image?.dispose()
      ..image = null
      ..availability = _ImageBookPageAvailability.pending
      ..error = null
      ..loadingOverlayReady = false
      ..applyPresentation();
    _textureRevision += 1;
    widget.onMediaLoad?.call(const ImageBookMediaLoadEvent(result: 'retry'));
    setState(() {});
    _ensurePageLoad(
      index: index,
      imageUrl: imageUrl,
      pageSize: pageSize,
      force: true,
    );
  }

  List<String> _processedCoverCandidates(String imageUrl, double width) {
    final processed = <String>[];
    for (final candidate in resolveContentMediaUrlCandidates(imageUrl)) {
      final normalized = candidate.trim();
      if (normalized.isEmpty) {
        continue;
      }
      final coverUrl = CdnImageUrlBuilder.cover(
        normalized,
        width: math.max(1, width.round()),
      );
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

enum _ImageBookPageAvailability { pending, ready, failed }

class _ImageBookPageResource {
  _ImageBookPageResource(this.imageUrl);

  final String imageUrl;
  _ImageBookPageAvailability availability = _ImageBookPageAvailability.pending;
  _ImageBookPageAvailability presentedAvailability =
      _ImageBookPageAvailability.pending;
  ui.Image? image;
  Object? error;
  Object? presentedError;
  Timer? loadingTimer;
  bool loadInFlight = false;
  bool loadingOverlayReady = false;
  bool presentedLoadingOverlayReady = false;
  bool presentationDirty = false;
  int generation = 0;

  void applyPresentation() {
    presentedAvailability = availability;
    presentedError = error;
    presentedLoadingOverlayReady = loadingOverlayReady;
    presentationDirty = false;
  }

  void dispose() {
    generation += 1;
    loadingTimer?.cancel();
    image?.dispose();
    image = null;
  }
}

class _ImageBookPage extends StatelessWidget {
  const _ImageBookPage({
    super.key,
    required this.resource,
    required this.coverSourceRect,
    required this.hideStatusOverlay,
    required this.fadeDuration,
    required this.onRetry,
  });

  final _ImageBookPageResource? resource;
  final Rect? coverSourceRect;
  final bool hideStatusOverlay;
  final Duration fadeDuration;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final availability =
        resource?.presentedAvailability ?? _ImageBookPageAvailability.pending;
    final image = availability == _ImageBookPageAvailability.ready
        ? resource?.image
        : null;
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
          if (!hideStatusOverlay &&
              availability == _ImageBookPageAvailability.pending &&
              (resource?.presentedLoadingOverlayReady ?? false))
            const _ImageBookLoadingOverlay(),
          if (!hideStatusOverlay &&
              availability == _ImageBookPageAvailability.failed)
            _ImageBookFailureOverlay(onRetry: onRetry),
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
  const _ImageBookLoadingOverlay();

  @override
  Widget build(BuildContext context) {
    return const Center(
      key: ValueKey<String>('image-book-loading-overlay'),
      child: Opacity(
        opacity: 0.36,
        child: CupertinoActivityIndicator(color: AppColors.white),
      ),
    );
  }
}

class _ImageBookFailureOverlay extends StatelessWidget {
  const _ImageBookFailureOverlay({required this.onRetry});

  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      key: const ValueKey<String>('image-book-failure-overlay'),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Icon(
            Icons.image_not_supported_outlined,
            color: AppColors.white.withValues(alpha: 0.46),
            size: AppSpacing.iconLarge,
          ),
          const SizedBox(height: AppSpacing.sm),
          Text(
            UITextConstants.imageLoadFailed,
            style: TextStyle(
              color: AppColors.white.withValues(alpha: 0.68),
              fontSize: 14,
            ),
          ),
          const SizedBox(height: AppSpacing.sm),
          CupertinoButton(
            key: const ValueKey<String>('image-book-retry'),
            padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.md,
              vertical: AppSpacing.sm,
            ),
            minimumSize: const Size.square(AppSpacing.smallButtonSize),
            onPressed: onRetry,
            child: const Row(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Icon(CupertinoIcons.refresh, size: AppSpacing.iconSmall),
                SizedBox(width: AppSpacing.sm),
                Text(UITextConstants.retry),
              ],
            ),
          ),
        ],
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
            child: ColoredBox(color: Color(0x2E000000)),
          ),
        ),
      ],
    );
  }
}
