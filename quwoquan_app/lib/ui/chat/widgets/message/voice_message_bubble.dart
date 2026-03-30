import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/ui/chat/providers/voice_player_manager.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/voice_waveform_painter.dart';

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

  /// Bubble width proportional to duration: 120px for 1s, up to 260px for 60s+.
  double get _bubbleWidth {
    const minWidth = 120.0;
    const maxWidth = 260.0;
    final seconds = durationMs / 1000;
    final ratio = (seconds / 60).clamp(0.0, 1.0);
    return minWidth + (maxWidth - minWidth) * ratio;
  }

  String get _durationText {
    final totalSeconds = (durationMs / 1000).ceil();
    if (totalSeconds < 60) return '$totalSeconds″';
    final m = totalSeconds ~/ 60;
    final s = totalSeconds % 60;
    return '$m′${s.toString().padLeft(2, '0')}″';
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final playback = ref.watch(voicePlayerManagerProvider);
    final isActive = playback.activeMessageId == messageId;
    final isPlaying = isActive && playback.isPlaying;
    final progress = isActive ? playback.progress : 0.0;

    final isDark =
        CupertinoTheme.of(context).brightness == Brightness.dark;
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

    return GestureDetector(
      onTap: () {
        if (messageStatus != 'sent' && messageStatus != 'delivered') return;
        ref.read(voicePlayerManagerProvider.notifier).play(messageId, mediaUrl);
      },
      child: Container(
        width: _bubbleWidth,
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.containerSm,
          vertical: AppSpacing.intraGroupSm,
        ),
        decoration: BoxDecoration(
          color: bubbleColor,
          borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            _buildPlayButton(isPlaying, textColor),
            SizedBox(width: AppSpacing.intraGroupXs),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  SizedBox(
                    height: AppSpacing.lg,
                    child: VoiceWaveformPainter(
                      waveform: waveform,
                      progress: progress,
                      baseColor: waveColor,
                      activeColor: waveActiveColor,
                      isAnimating: isPlaying,
                    ),
                  ),
                  SizedBox(height: AppSpacing.intraGroupXs),
                  Text(
                    _durationText,
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
      decoration: BoxDecoration(
        color: AppColors.error,
        shape: BoxShape.circle,
      ),
    );
  }
}
