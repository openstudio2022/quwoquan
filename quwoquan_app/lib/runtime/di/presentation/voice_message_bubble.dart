import 'dart:math' as math;

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/voice_player_manager.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/presentation/voice_waveform_painter.dart';

/// Voice message bubble with play/pause button, waveform, and duration.
class VoiceMessageBubble extends ConsumerWidget {
  const VoiceMessageBubble({
    super.key,
    required this.messageId,
    required this.mediaUrl,
    required this.durationMs,
    required this.waveform,
    required this.isOutgoing,
    this.isRead = true,
    this.messageStatus = 'sent',
  });

  final String messageId;
  final String mediaUrl;
  final int durationMs;
  final List<double> waveform;
  final bool isOutgoing;
  final bool isRead;
  final String messageStatus;

  /// Bubble width follows the familiar chat rhythm: short clips stay tappable,
  /// longer clips grow smoothly without taking over the row.
  double get _bubbleWidth {
    final minWidth = AppSpacing.buttonSize * 2.2;
    final maxWidth = AppSpacing.buttonSize * 5.4;
    final seconds = (durationMs / 1000).clamp(1.0, 60.0);
    final ratio = (seconds / 60).clamp(0.0, 1.0);
    final eased = Curves.easeOutCubic.transform(ratio);
    return minWidth + (maxWidth - minWidth) * eased;
  }

  String get _durationText {
    final totalSeconds = (durationMs / 1000).ceil().clamp(1, 599);
    if (totalSeconds < 60) return '$totalSeconds″';
    final m = totalSeconds ~/ 60;
    final s = totalSeconds % 60;
    return '$m′${s.toString().padLeft(2, '0')}″';
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final playback = ref.watch(
      voicePlayerManagerProvider.select(
        (state) => _VoiceBubblePlaybackView.fromState(state, messageId),
      ),
    );
    final isPlaying = playback.isPlaying;
    final progress = playback.progress;
    final hasPlaybackError = playback.error != null;

    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final incomingSurface = AppColorsFunctional.getColor(
      isDark,
      ColorType.surfaceElevated,
    );
    final bubbleColor = isOutgoing
        ? AppColors.chatBubbleOutgoing
        : incomingSurface;

    final textColor = isOutgoing
        ? AppColorsFunctional.getColor(isDark, ColorType.foregroundInverse)
        : AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);

    final waveColor = isOutgoing
        ? AppColors.white.withValues(alpha: 0.6)
        : AppColorsFunctional.getColor(isDark, ColorType.foregroundTertiary);

    final waveActiveColor = isOutgoing
        ? AppColors.white
        : AppColors.primaryColor;

    final canPlay =
        !hasPlaybackError &&
        mediaUrl.trim().isNotEmpty &&
        (messageStatus == 'sent' || messageStatus == 'delivered');
    final disabledColor = textColor.withValues(alpha: 0.45);

    return LayoutBuilder(
      builder: (context, constraints) {
        final maxWidth = constraints.maxWidth.isFinite
            ? math.max(AppSpacing.buttonSize * 2, constraints.maxWidth)
            : _bubbleWidth;
        final width = math.min(_bubbleWidth, maxWidth);
        return GestureDetector(
          onTap: () {
            if (!canPlay) return;
            ref
                .read(voicePlayerManagerProvider.notifier)
                .play(messageId, mediaUrl);
          },
          child: Opacity(
            opacity: canPlay ? 1 : 0.72,
            child: Container(
              width: width,
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.containerSm,
                vertical: AppSpacing.intraGroupSm,
              ),
              decoration: BoxDecoration(
                color: bubbleColor,
                borderRadius: BorderRadius.circular(
                  AppSpacing.largeBorderRadius,
                ),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  _buildPlayButton(
                    isPlaying,
                    canPlay ? textColor : disabledColor,
                  ),
                  SizedBox(width: AppSpacing.intraGroupXs),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        RepaintBoundary(
                          child: SizedBox(
                            height: AppSpacing.lg,
                            child: VoiceWaveformPainter(
                              waveform: waveform,
                              progress: progress,
                              baseColor: waveColor,
                              activeColor: waveActiveColor,
                              isAnimating: isPlaying,
                            ),
                          ),
                        ),
                        SizedBox(height: AppSpacing.intraGroupXs),
                        Text(
                          hasPlaybackError
                              ? playback.error!
                              : (canPlay
                                    ? _durationText
                                    : ChatText.chatVoiceSending),
                          style: TextStyle(
                            fontSize: AppTypography.xs,
                            color: textColor.withValues(alpha: 0.7),
                          ),
                        ),
                      ],
                    ),
                  ),
                  if (!isOutgoing && !isRead) ...[
                    SizedBox(width: AppSpacing.intraGroupXs),
                    _buildUnreadDot(),
                  ],
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _buildPlayButton(bool isPlaying, Color color) {
    return Icon(
      isPlaying ? CupertinoIcons.pause_fill : CupertinoIcons.play_fill,
      size: AppSpacing.iconMedium,
      color: color,
    );
  }

  Widget _buildUnreadDot() {
    return Container(
      width: AppSpacing.xs + 2,
      height: AppSpacing.xs + 2,
      decoration: BoxDecoration(color: AppColors.error, shape: BoxShape.circle),
    );
  }
}

class _VoiceBubblePlaybackView {
  const _VoiceBubblePlaybackView({
    required this.isPlaying,
    required this.progress,
    this.error,
  });

  factory _VoiceBubblePlaybackView.fromState(
    VoicePlaybackState state,
    String messageId,
  ) {
    final isActive = state.activeMessageId == messageId;
    final hasError =
        state.failedMessageId == messageId &&
        (state.error ?? '').trim().isNotEmpty;
    return _VoiceBubblePlaybackView(
      isPlaying: isActive && state.isPlaying,
      progress: isActive ? state.progress : 0,
      error: hasError ? state.error : null,
    );
  }

  final bool isPlaying;
  final double progress;
  final String? error;

  @override
  bool operator ==(Object other) {
    return other is _VoiceBubblePlaybackView &&
        other.isPlaying == isPlaying &&
        other.progress == progress &&
        other.error == error;
  }

  @override
  int get hashCode => Object.hash(isPlaying, progress, error);
}
