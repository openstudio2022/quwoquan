import 'dart:async';
import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/errors/runtime_error_display.dart';
import 'package:quwoquan_app/components/media/picker/one_tap_movie_composer.dart';
import 'package:quwoquan_app/components/media/shared/media_creation_bottom_button.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/models/create_media_models.dart';

class OneTapMoviePreviewPage extends StatefulWidget {
  const OneTapMoviePreviewPage({
    super.key,
    required this.items,
    this.composer = const MethodChannelOneTapMovieComposer(),
  });

  final List<CreateMediaItem> items;
  final OneTapMovieComposer composer;

  @override
  State<OneTapMoviePreviewPage> createState() => _OneTapMoviePreviewPageState();
}

class _OneTapMoviePreviewPageState extends State<OneTapMoviePreviewPage> {
  static const int _frameStepMs = 200;
  static const int _secondsPerImage = 3;
  Timer? _timer;
  bool _playing = true;
  bool _composing = false;
  Duration _position = Duration.zero;
  String _selectedEffectId = 'original';

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
    _timer = Timer.periodic(const Duration(milliseconds: _frameStepMs), (_) {
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
    });
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

  Future<void> _composeAndContinue() async {
    if (_images.isEmpty || _composing) {
      return;
    }
    if (_selectedEffectId == _OneTapMovieEffectIds.original) {
      _continueWithSourceImages();
      return;
    }
    setState(() {
      _composing = true;
      _playing = false;
    });
    try {
      final result = await widget.composer.compose(images: _images);
      if (!mounted) return;
      Navigator.of(context).pop(
        OneTapMovieComposeResult(
          videoPath: result.videoPath,
          durationMs: result.durationMs,
          coverPath: result.coverPath,
          effectId: _selectedEffectId,
        ),
      );
    } on UnsupportedError {
      if (!mounted) return;
      _continueWithSourceImages();
    } catch (error) {
      if (!mounted) return;
      setState(() => _composing = false);
      await AppActionErrorFeedback.show(
        context,
        semantic: runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.submit,
          scope: UiErrorScope.global,
        ),
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _composeAndContinue();
          }
        },
      );
    }
  }

  void _continueWithSourceImages() {
    Navigator.of(context).pop(
      OneTapMovieComposeResult(
        videoPath: '',
        durationMs: _totalDuration.inMilliseconds,
        effectId: _selectedEffectId,
      ),
    );
  }

  int get _currentImageIndex {
    if (_images.isEmpty) return 0;
    final perImageMs = (_secondsPerImage * 1000);
    final index = (_position.inMilliseconds ~/ perImageMs).clamp(
      0,
      _images.length - 1,
    );
    return index;
  }

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final bg = AppColors.black;
    final fg = AppColors.white;
    final progress = _totalDuration.inMilliseconds == 0
        ? 0.0
        : (_position.inMilliseconds / _totalDuration.inMilliseconds).clamp(
            0.0,
            1.0,
          );
    final current = _images.isEmpty ? null : _images[_currentImageIndex];
    return AppScaffold(
      backgroundColor: bg,
      child: SafeArea(
        child: Column(
          children: [
            SizedBox(
              height: AppSpacing.toolbarHeight,
              child: Row(
                children: [
                  CupertinoButton(
                    padding: EdgeInsets.zero,
                    onPressed: () => Navigator.of(context).pop(),
                    minimumSize: Size(
                      AppSpacing.minInteractiveSize,
                      AppSpacing.minInteractiveSize,
                    ),
                    child: Icon(CupertinoIcons.back, color: fg),
                  ),
                  const Spacer(),
                  SizedBox(width: AppSpacing.minInteractiveSize),
                ],
              ),
            ),
            Expanded(
              child: Center(
                child: Container(
                  margin: EdgeInsets.symmetric(
                    horizontal: AppSpacing.containerLg,
                  ),
                  decoration: BoxDecoration(
                    color: AppColors.black,
                    borderRadius: BorderRadius.circular(
                      AppSpacing.largeBorderRadius,
                    ),
                  ),
                  clipBehavior: Clip.antiAlias,
                  child: AspectRatio(
                    aspectRatio: 9 / 16,
                    child: current == null
                        ? Center(
                            child: Text(
                              UITextConstants.mediaPickerImageOnly,
                              style: TextStyle(
                                color: AppColors.white.withValues(alpha: 0.7),
                                fontSize: AppTypography.base,
                              ),
                            ),
                          )
                        : Image.file(
                            File(current.path),
                            fit: BoxFit.contain,
                            errorBuilder: (context, error, stackTrace) =>
                                Center(
                                  child: Icon(
                                    Icons.broken_image_outlined,
                                    color: AppColors.white.withValues(
                                      alpha: 0.7,
                                    ),
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
                AppSpacing.intraGroupSm,
              ),
              child: Row(
                children: [
                  GestureDetector(
                    onTap: _togglePlay,
                    child: Icon(
                      _playing
                          ? CupertinoIcons.pause
                          : CupertinoIcons.play_arrow,
                      color: AppColors.white,
                      size: AppSpacing.iconMedium,
                    ),
                  ),
                  SizedBox(width: AppSpacing.intraGroupSm),
                  Text(
                    _formatDuration(_position),
                    style: TextStyle(
                      color: AppColors.white,
                      fontSize: AppTypography.base,
                    ),
                  ),
                  Expanded(
                    child: CupertinoSlider(
                      value: progress,
                      onChanged: (value) => _seek(value),
                      activeColor: AppColors.white,
                      thumbColor: AppColors.white,
                    ),
                  ),
                  Text(
                    _formatDuration(_totalDuration),
                    style: TextStyle(
                      color: AppColors.white,
                      fontSize: AppTypography.base,
                    ),
                  ),
                ],
              ),
            ),
            SizedBox(
              height: AppSpacing.bottomNavHeight + AppSpacing.containerSm,
              child: ListView.separated(
                scrollDirection: Axis.horizontal,
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.containerMd,
                  vertical: AppSpacing.intraGroupXs,
                ),
                itemCount: _oneTapMovieEffects.length,
                separatorBuilder: (context, index) =>
                    SizedBox(width: AppSpacing.intraGroupSm),
                itemBuilder: (context, index) {
                  final effect = _oneTapMovieEffects[index];
                  final selected = effect.id == _selectedEffectId;
                  return GestureDetector(
                    onTap: () => setState(() => _selectedEffectId = effect.id),
                    child: Container(
                      width: AppSpacing.bottomNavHeight * 1.4,
                      alignment: Alignment.center,
                      decoration: BoxDecoration(
                        color: selected
                            ? AppColors.primaryColor.withValues(alpha: 0.18)
                            : AppColors.white.withValues(alpha: 0.08),
                        borderRadius: BorderRadius.circular(
                          AppSpacing.borderRadius,
                        ),
                        border: Border.all(
                          color: selected
                              ? AppColors.primaryColor
                              : AppColors.white.withValues(alpha: 0.16),
                        ),
                      ),
                      child: Text(
                        effect.label,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          color: selected
                              ? AppColors.primaryColor
                              : AppColors.white.withValues(alpha: 0.86),
                          fontSize: AppTypography.sm,
                          fontWeight: selected
                              ? AppTypography.semiBold
                              : AppTypography.regular,
                        ),
                      ),
                    ),
                  );
                },
              ),
            ),
            Padding(
              padding: EdgeInsets.fromLTRB(
                AppSpacing.containerMd,
                AppSpacing.intraGroupSm,
                AppSpacing.containerMd,
                (MediaQuery.paddingOf(context).bottom > 0
                        ? MediaQuery.paddingOf(context).bottom
                        : AppSpacing.containerMd) +
                    AppSpacing.intraGroupSm,
              ),
              child: MediaCreationBottomButton(
                label: _composing
                    ? UITextConstants.mediaPickerOneTapMovieComposing
                    : UITextConstants.mediaPickerNextStep,
                variant: MediaCreationBottomButtonVariant.fullWidthNeutral,
                isLoading: _composing,
                onPressed: _images.isEmpty || _composing
                    ? null
                    : _composeAndContinue,
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

class _OneTapMovieEffect {
  const _OneTapMovieEffect({required this.id, required this.label});

  final String id;
  final String label;
}

abstract final class _OneTapMovieEffectIds {
  static const String original = 'original';
}

const _oneTapMovieEffects = <_OneTapMovieEffect>[
  _OneTapMovieEffect(
    id: _OneTapMovieEffectIds.original,
    label: UITextConstants.mediaPickerOneTapMovieOriginal,
  ),
  _OneTapMovieEffect(
    id: 'gentle_motion',
    label: UITextConstants.mediaPickerOneTapMovieGentleMotion,
  ),
  _OneTapMovieEffect(
    id: 'beat',
    label: UITextConstants.mediaPickerOneTapMovieBeat,
  ),
  _OneTapMovieEffect(
    id: 'scenery',
    label: UITextConstants.mediaPickerOneTapMovieScenery,
  ),
];
