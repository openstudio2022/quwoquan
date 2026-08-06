import 'dart:async';
import 'dart:developer' as developer;

import 'package:flutter/material.dart';

import 'package:quwoquan_app/service/content_service/media/media_asset/application/video_preview_track_query.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';

/// 拖动预览的受控增强层。
///
/// manifest、sprite 或 crop 任一失败都返回空组件，时间浮标和 seek 主链不受影响。
class VideoTimelinePreview extends StatefulWidget {
  const VideoTimelinePreview({
    required this.descriptor,
    required this.query,
    required this.target,
    super.key,
  });

  final VideoPreviewTrackDescriptor descriptor;
  final VideoPreviewTrackQuery query;
  final Duration target;

  static const double maximumHeight = AppSpacing.videoTimelinePreviewMaxHeight;

  @override
  State<VideoTimelinePreview> createState() => _VideoTimelinePreviewState();
}

class _VideoTimelinePreviewState extends State<VideoTimelinePreview> {
  static const Duration _debounce = Duration(milliseconds: 100);
  static const double _maximumWidth = AppSpacing.videoTimelinePreviewMaxWidth;

  Timer? _debounceTimer;
  VideoPreviewTrackManifest? _manifest;
  VideoPreviewTrackFrame? _frame;
  int _generation = 0;
  bool _failed = false;

  @override
  void initState() {
    super.initState();
    _loadManifest();
  }

  @override
  void didUpdateWidget(covariant VideoTimelinePreview oldWidget) {
    super.didUpdateWidget(oldWidget);
    final descriptorChanged =
        oldWidget.descriptor.assetId != widget.descriptor.assetId ||
        oldWidget.descriptor.assetVersion != widget.descriptor.assetVersion ||
        oldWidget.descriptor.trackVersion != widget.descriptor.trackVersion ||
        oldWidget.descriptor.manifestReference !=
            widget.descriptor.manifestReference;
    if (descriptorChanged || oldWidget.query != widget.query) {
      _generation += 1;
      _debounceTimer?.cancel();
      _manifest = null;
      _frame = null;
      _failed = false;
      _loadManifest();
      return;
    }
    if (oldWidget.target != widget.target) {
      _scheduleFrameSelection();
    }
  }

  Future<void> _loadManifest() async {
    final generation = ++_generation;
    try {
      final manifest = await widget.query.loadManifest(widget.descriptor);
      if (!mounted || generation != _generation) {
        return;
      }
      setState(() {
        _manifest = manifest;
        _frame = manifest.frameFor(widget.target);
        _failed = false;
      });
    } catch (error, stackTrace) {
      developer.log(
        'video timeline preview manifest unavailable',
        name: 'VideoTimelinePreview',
        error: error,
        stackTrace: stackTrace,
      );
      if (!mounted || generation != _generation) {
        return;
      }
      setState(() {
        _failed = true;
        _manifest = null;
        _frame = null;
      });
    }
  }

  void _scheduleFrameSelection() {
    _debounceTimer?.cancel();
    final manifest = _manifest;
    if (manifest == null || _failed) {
      return;
    }
    _debounceTimer = Timer(_debounce, () {
      if (!mounted) {
        return;
      }
      final next = manifest.frameFor(widget.target);
      if (_frame?.timeMs == next.timeMs &&
          _frame?.sprite.spriteId == next.sprite.spriteId) {
        return;
      }
      setState(() => _frame = next);
    });
  }

  @override
  void dispose() {
    _generation += 1;
    _debounceTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final frame = _frame;
    if (frame == null || _failed) {
      return const SizedBox.shrink();
    }
    final scale = (_maximumWidth / frame.width).clamp(
      AppSpacing.zero,
      VideoTimelinePreview.maximumHeight / frame.height,
    );
    final frameWidth = frame.width * scale;
    final frameHeight = frame.height * scale;
    final spriteWidth = frame.sprite.width * scale;
    final spriteHeight = frame.sprite.height * scale;
    return Center(
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: AppColors.black.withValues(alpha: 0.72),
          borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
          border: Border.all(
            color: AppColors.white.withValues(alpha: 0.20),
            width: AppSpacing.hairline,
          ),
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
          child: SizedBox(
            key: ValueKey<String>(
              'video-timeline-preview-${widget.descriptor.assetId}-'
              '${widget.descriptor.trackVersion}-${frame.timeMs}',
            ),
            width: frameWidth,
            height: frameHeight,
            child: AppCachedNetworkImage(
              imageUrl: frame.sprite.reference.url,
              imageUrlCandidates: <String>[frame.sprite.reference.url],
              width: frameWidth,
              height: frameHeight,
              fit: BoxFit.none,
              placeholder: const SizedBox.shrink(),
              errorWidget: const SizedBox.shrink(),
              onLoadFailed: (error) {
                developer.log(
                  'video timeline preview sprite unavailable',
                  name: 'VideoTimelinePreview',
                  error: error,
                );
              },
              imageBuilder: (context, imageProvider) {
                return ClipRect(
                  child: OverflowBox(
                    alignment: Alignment.topLeft,
                    minWidth: spriteWidth,
                    maxWidth: spriteWidth,
                    minHeight: spriteHeight,
                    maxHeight: spriteHeight,
                    child: Transform.translate(
                      offset: Offset(-frame.x * scale, -frame.y * scale),
                      child: Image(
                        image: imageProvider,
                        width: spriteWidth,
                        height: spriteHeight,
                        fit: BoxFit.fill,
                        filterQuality: FilterQuality.low,
                      ),
                    ),
                  ),
                );
              },
            ),
          ),
        ),
      ),
    );
  }
}
