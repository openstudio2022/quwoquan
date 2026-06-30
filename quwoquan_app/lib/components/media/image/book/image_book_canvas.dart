import 'dart:async';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/cloud/media/cdn_image_url_builder.dart';
import 'package:quwoquan_app/components/media/image/book/image_book_page_surface.dart';
import 'package:quwoquan_app/components/media/shared/pageflip/media_page_flip_book.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/media/content_media_url.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';

/// 图片作品的书页式沉浸画布。
///
/// 输入是通用图片 URL 列表与回调，避免公共组件依赖 discovery/content 业务 DTO。
class ImageBookCanvas extends StatefulWidget {
  const ImageBookCanvas({
    super.key,
    required this.imageUrls,
    required this.onImageChanged,
    this.initialIndex = 0,
    this.onOverflowPrevious,
    this.onOverflowNext,
  });

  final List<String> imageUrls;
  final int initialIndex;
  final ValueChanged<int> onImageChanged;
  final VoidCallback? onOverflowPrevious;
  final VoidCallback? onOverflowNext;

  @override
  State<ImageBookCanvas> createState() => _ImageBookCanvasState();
}

class _ImageBookCanvasState extends State<ImageBookCanvas> {
  static const ImageBookPageSurfaceFactory _pageSurfaceFactory =
      ImageBookPageSurfaceFactory();

  final Set<int> _textureReadyIndices = <int>{};
  final Set<int> _textureFailedIndices = <int>{};

  int get _safeInitialIndex {
    if (widget.imageUrls.length <= 1) {
      return 0;
    }
    return widget.initialIndex.clamp(0, widget.imageUrls.length - 1).toInt();
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _precacheInitialPage());
  }

  @override
  void didUpdateWidget(covariant ImageBookCanvas oldWidget) {
    super.didUpdateWidget(oldWidget);
    final imagesChanged = widget.imageUrls != oldWidget.imageUrls;
    if (imagesChanged) {
      _textureReadyIndices.clear();
      _textureFailedIndices.clear();
    }
    if (imagesChanged || widget.initialIndex != oldWidget.initialIndex) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) {
          return;
        }
        widget.onImageChanged(_safeInitialIndex);
        _precacheNeighborImages(_safeInitialIndex);
      });
    }
  }

  void _markTextureReady(int index) {
    if (!mounted) {
      return;
    }
    final changed =
        _textureReadyIndices.add(index) | _textureFailedIndices.remove(index);
    if (changed) {
      setState(() {});
    }
  }

  void _markTextureFailed(int index) {
    if (!mounted) {
      return;
    }
    final changed =
        _textureFailedIndices.add(index) | _textureReadyIndices.remove(index);
    if (changed) {
      setState(() {});
    }
  }

  Object _textureReadinessSignature() {
    final ready = _textureReadyIndices.toList(growable: false)..sort();
    final failed = _textureFailedIndices.toList(growable: false)..sort();
    return Object.hash(Object.hashAll(ready), Object.hashAll(failed));
  }

  void _precacheInitialPage() {
    if (!mounted) {
      return;
    }
    _precacheNeighborImages(_safeInitialIndex);
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
    return MediaPageFlipBook(
      key: const ValueKey('works-photo-book-stage'),
      pageCount: images.length,
      initialPage: _safeInitialIndex,
      contentSignature: Object.hashAll(images),
      textureReadinessSignature: _textureReadinessSignature(),
      isPageTextureReady: (index) =>
          _textureReadyIndices.contains(index) ||
          _textureFailedIndices.contains(index),
      textureSnapshotBuilder: (context, index, pageSize, pixelRatio) {
        return _buildImageTextureSnapshot(
          context: context,
          pageIndex: index,
          imageUrl: images[index],
          pageSize: pageSize,
          pixelRatio: pixelRatio,
        );
      },
      stageColor: AppColors.worksBackground,
      onPageChanged: (index) {
        _precacheNeighborImages(index);
        widget.onImageChanged(index);
      },
      onOverflowPrevious: widget.onOverflowPrevious,
      onOverflowNext: widget.onOverflowNext,
      pageBuilder: (context, index) {
        return _ImageBookPage(
          imageUrl: images[index],
          onImageLoaded: () => _markTextureReady(index),
          onImageFailed: () => _markTextureFailed(index),
        );
      },
    );
  }

  void _precacheNeighborImages(int centerIndex) {
    for (final index in <int>[centerIndex - 1, centerIndex, centerIndex + 1]) {
      if (index < 0 || index >= widget.imageUrls.length) {
        continue;
      }
      if (_textureReadyIndices.contains(index) ||
          _textureFailedIndices.contains(index)) {
        continue;
      }
      final url = widget.imageUrls[index].trim();
      if (url.isEmpty) {
        continue;
      }
      final candidates = _processedCoverCandidates(url, 750);
      unawaited(_precacheImageCandidates(index, candidates));
    }
  }

  Future<void> _precacheImageCandidates(
    int pageIndex,
    List<String> candidates,
  ) async {
    if (candidates.isEmpty) {
      _markTextureFailed(pageIndex);
      return;
    }
    for (final candidate in candidates) {
      try {
        await precacheImage(
          CachedNetworkImageProvider(
            candidate,
            cacheManager: AppImageCacheController.cacheManagerForPreset(
              CdnImagePreset.cover,
            ),
          ),
          context,
        );
        _markTextureReady(pageIndex);
        return;
      } catch (_) {
        continue;
      }
    }
    _markTextureFailed(pageIndex);
  }

  Future<MediaPageFlipTexturePair?> _buildImageTextureSnapshot({
    required BuildContext context,
    required int pageIndex,
    required String imageUrl,
    required Size pageSize,
    required double pixelRatio,
  }) async {
    final candidates = _processedCoverCandidates(
      imageUrl,
      math.max(750, pageSize.width),
    );
    if (candidates.isEmpty || pageSize.isEmpty) {
      return _pageSurfaceFactory.buildFailureTexture(
        pageSize: pageSize,
        pixelRatio: pixelRatio,
      );
    }
    if (_textureFailedIndices.contains(pageIndex)) {
      return _pageSurfaceFactory.buildFailureTexture(
        pageSize: pageSize,
        pixelRatio: pixelRatio,
      );
    }
    final providers = candidates
        .map(
          (candidate) => CachedNetworkImageProvider(
            candidate,
            cacheManager: AppImageCacheController.cacheManagerForPreset(
              CdnImagePreset.cover,
            ),
          ),
        )
        .toList(growable: false);
    if (!_textureReadyIndices.contains(pageIndex)) {
      for (final provider in providers) {
        final cached = _resolveCachedImageProviderSynchronously(
          context: context,
          provider: provider,
          pageSize: pageSize,
        );
        if (cached != null) {
          WidgetsBinding.instance.addPostFrameCallback((_) {
            _markTextureReady(pageIndex);
          });
          return await _pageSurfaceFactory.rasterizeImageTexture(
            image: cached,
            pageSize: pageSize,
            pixelRatio: pixelRatio,
          );
        }
      }
      return _pageSurfaceFactory.buildFailureTexture(
        pageSize: pageSize,
        pixelRatio: pixelRatio,
      );
    }
    for (final provider in providers) {
      try {
        final image = await _resolveImageProvider(
          context: context,
          provider: provider,
          pageSize: pageSize,
        );
        return await _pageSurfaceFactory.rasterizeImageTexture(
          image: image,
          pageSize: pageSize,
          pixelRatio: pixelRatio,
        );
      } catch (_) {
        continue;
      }
    }
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _markTextureFailed(pageIndex);
    });
    return _pageSurfaceFactory.buildFailureTexture(
      pageSize: pageSize,
      pixelRatio: pixelRatio,
    );
  }

  List<String> _processedCoverCandidates(String imageUrl, double width) {
    final candidates = resolveContentMediaUrlCandidates(imageUrl);
    final processed = <String>[];
    for (final candidate in candidates) {
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
          completer.complete(info.image);
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

  ui.Image? _resolveCachedImageProviderSynchronously({
    required BuildContext context,
    required ImageProvider provider,
    required Size pageSize,
  }) {
    ui.Image? resolvedImage;
    final stream = provider.resolve(
      createLocalImageConfiguration(context, size: pageSize),
    );
    late final ImageStreamListener listener;
    listener = ImageStreamListener(
      (ImageInfo info, bool synchronousCall) {
        if (synchronousCall) {
          resolvedImage = info.image;
        }
        stream.removeListener(listener);
      },
      onError: (Object error, StackTrace? stackTrace) {
        stream.removeListener(listener);
      },
    );
    stream.addListener(listener);
    if (resolvedImage == null) {
      stream.removeListener(listener);
    }
    return resolvedImage;
  }
}

class _ImageBookPage extends StatelessWidget {
  const _ImageBookPage({
    required this.imageUrl,
    required this.onImageLoaded,
    required this.onImageFailed,
  });

  final String imageUrl;
  final VoidCallback onImageLoaded;
  final VoidCallback onImageFailed;

  @override
  Widget build(BuildContext context) {
    return Stack(
      fit: StackFit.expand,
      children: [
        AppCachedNetworkImage(
          imageUrl: imageUrl,
          imageUrlCandidates: resolveContentMediaUrlCandidates(imageUrl),
          cdnPreset: CdnImagePreset.cover,
          fit: BoxFit.cover,
          onLoadFailed: (_) {
            WidgetsBinding.instance.addPostFrameCallback((_) {
              onImageFailed();
            });
          },
          imageBuilder: (context, imageProvider) {
            WidgetsBinding.instance.addPostFrameCallback((_) {
              onImageLoaded();
            });
            return Image(
              image: imageProvider,
              fit: BoxFit.cover,
              width: double.infinity,
              height: double.infinity,
            );
          },
          placeholder: const _ImageBookPlaceholderSurface(),
          errorWidget: const _ImageBookPlaceholderSurface(isFailure: true),
        ),
        Positioned.fill(
          child: IgnorePointer(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    AppColors.black.withValues(alpha: 0.06),
                    AppColors.black.withValues(alpha: 0.58),
                  ],
                ),
              ),
            ),
          ),
        ),
        Positioned(
          left: AppSpacing.zero,
          right: AppSpacing.zero,
          bottom: AppSpacing.zero,
          height: AppSpacing.hairline,
          child: ColoredBox(color: AppColors.black.withValues(alpha: 0.18)),
        ),
      ],
    );
  }
}

class _ImageBookPlaceholderSurface extends StatelessWidget {
  const _ImageBookPlaceholderSurface({this.isFailure = false});

  final bool isFailure;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: isFailure ? const Color(0xFF18202C) : const Color(0xFF141B25),
      ),
      child: const SizedBox.expand(),
    );
  }
}
