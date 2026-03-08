import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/models/create_media_models.dart';

class OneTapMoviePreviewPage extends StatefulWidget {
  const OneTapMoviePreviewPage({
    super.key,
    required this.items,
  });

  final List<CreateMediaItem> items;

  @override
  State<OneTapMoviePreviewPage> createState() => _OneTapMoviePreviewPageState();
}

class _OneTapMoviePreviewPageState extends State<OneTapMoviePreviewPage> {
  static const int _frameStepMs = 200;
  static const int _secondsPerImage = 3;
  Timer? _timer;
  bool _playing = true;
  Duration _position = Duration.zero;

  List<CreateMediaItem> get _images =>
      widget.items.where((item) => item.isImage).toList();

  Duration get _totalDuration {
    final seconds = (_images.length * _secondsPerImage).clamp(3, 3600);
    return Duration(seconds: seconds);
  }

  @override
  void initState() {
    super.initState();
    _startTicker();
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  void _startTicker() {
    _timer?.cancel();
    _timer = Timer.periodic(
      const Duration(milliseconds: _frameStepMs),
      (_) {
        if (!_playing || !mounted) return;
        final next = _position + const Duration(milliseconds: _frameStepMs);
        if (next >= _totalDuration) {
          setState(() {
            _position = _totalDuration;
            _playing = false;
          });
          return;
        }
        setState(() => _position = next);
      },
    );
  }

  void _togglePlay() {
    setState(() {
      if (_position >= _totalDuration) {
        _position = Duration.zero;
      }
      _playing = !_playing;
    });
  }

  void _seek(double fraction) {
    final safe = fraction.clamp(0.0, 1.0);
    final targetMs = (_totalDuration.inMilliseconds * safe).round();
    setState(() {
      _position = Duration(milliseconds: targetMs);
    });
  }

  int get _currentImageIndex {
    if (_images.isEmpty) return 0;
    final perImageMs = (_secondsPerImage * 1000);
    final index = (_position.inMilliseconds ~/ perImageMs).clamp(0, _images.length - 1);
    return index;
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final bg = Colors.black;
    final fg = Colors.white;
    final progress = _totalDuration.inMilliseconds == 0
        ? 0.0
        : (_position.inMilliseconds / _totalDuration.inMilliseconds)
            .clamp(0.0, 1.0);
    final current = _images.isEmpty ? null : _images[_currentImageIndex];
    return Scaffold(
      backgroundColor: bg,
      body: SafeArea(
        child: Column(
          children: [
            SizedBox(
              height: AppSpacing.toolbarHeight,
              child: Row(
                children: [
                  IconButton(
                    onPressed: () => Navigator.of(context).pop(false),
                    icon: Icon(Icons.arrow_back_ios_new, color: fg),
                  ),
                  const Spacer(),
                  TextButton(
                    onPressed: _images.isEmpty
                        ? null
                        : () => Navigator.of(context).pop(true),
                    child: Text(
                      UITextConstants.mediaPickerNextStep,
                      style: TextStyle(
                        color: _images.isEmpty ? Colors.white54 : Colors.white,
                        fontSize: AppTypography.base,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                  SizedBox(width: AppSpacing.intraGroupSm),
                ],
              ),
            ),
            Expanded(
              child: Center(
                child: Container(
                  margin: EdgeInsets.symmetric(horizontal: AppSpacing.containerLg),
                  decoration: BoxDecoration(
                    color: Colors.black,
                    borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
                  ),
                  clipBehavior: Clip.antiAlias,
                  child: AspectRatio(
                    aspectRatio: 9 / 16,
                    child: current == null
                        ? Center(
                            child: Text(
                              UITextConstants.mediaPickerImageOnly,
                              style: TextStyle(
                                color: Colors.white70,
                                fontSize: AppTypography.base,
                              ),
                            ),
                          )
                        : Image.file(
                            File(current.path),
                            fit: BoxFit.contain,
                            errorBuilder: (context, error, stackTrace) => Center(
                              child: Icon(
                                Icons.broken_image_outlined,
                                color: Colors.white70,
                                size: AppSpacing.iconLarge,
                              ),
                            ),
                          ),
                  ),
                ),
              ),
            ),
            Padding(
              padding: EdgeInsets.fromLTRB(
                AppSpacing.containerMd,
                AppSpacing.intraGroupSm,
                AppSpacing.containerMd,
                AppSpacing.interGroupMd,
              ),
              child: Row(
                children: [
                  GestureDetector(
                    onTap: _togglePlay,
                    child: Icon(
                      _playing ? Icons.pause : Icons.play_arrow,
                      color: Colors.white,
                      size: AppSpacing.iconMedium,
                    ),
                  ),
                  SizedBox(width: AppSpacing.intraGroupSm),
                  Text(
                    _formatDuration(_position),
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: AppTypography.base,
                    ),
                  ),
                  Expanded(
                    child: SliderTheme(
                      data: SliderTheme.of(context).copyWith(
                        activeTrackColor: Colors.white,
                        inactiveTrackColor: Colors.white30,
                        thumbColor: Colors.white,
                        trackHeight: AppSpacing.intraGroupXs / 2,
                      ),
                      child: Slider(
                        value: progress,
                        onChanged: (value) => _seek(value),
                      ),
                    ),
                  ),
                  Text(
                    _formatDuration(_totalDuration),
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: AppTypography.base,
                    ),
                  ),
                ],
              ),
            ),
            if (!isDark) SizedBox(height: AppSpacing.intraGroupSm),
          ],
        ),
      ),
    );
  }

  String _formatDuration(Duration duration) {
    final totalSeconds = duration.inSeconds;
    final minutes = (totalSeconds ~/ 60).toString().padLeft(2, '0');
    final seconds = (totalSeconds % 60).toString().padLeft(2, '0');
    return '$minutes:$seconds';
  }
}
