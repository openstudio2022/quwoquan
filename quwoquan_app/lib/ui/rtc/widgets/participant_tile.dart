import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:livekit_client/livekit_client.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/ui/rtc/models/call_participant.dart';

class ParticipantTile extends StatelessWidget {
  const ParticipantTile({
    super.key,
    required this.participant,
    this.isActiveSpeaker = false,
    this.showName = true,
    this.borderRadius,
    this.videoTrack,
  });

  final CallParticipant participant;
  final bool isActiveSpeaker;
  final bool showName;
  final BorderRadius? borderRadius;
  final VideoTrack? videoTrack;

  @override
  Widget build(BuildContext context) {
    final effectiveRadius =
        borderRadius ?? BorderRadius.circular(AppSpacing.sm);

    return AnimatedContainer(
      duration: const Duration(milliseconds: 300),
      decoration: BoxDecoration(
        color: AppColors.overlayDark,
        borderRadius: effectiveRadius,
        border: isActiveSpeaker
            ? Border.all(
                color: AppColors.white.withValues(alpha: 0.8),
                width: AppSpacing.twoPointFour,
              )
            : null,
        boxShadow: isActiveSpeaker
            ? [
                BoxShadow(
                  color: AppColors.white.withValues(alpha: 0.3),
                  blurRadius: AppSpacing.sm,
                  spreadRadius: AppSpacing.one,
                ),
              ]
            : null,
      ),
      clipBehavior: Clip.antiAlias,
      child: Stack(
        fit: StackFit.expand,
        children: [
          if (participant.isCameraOn && videoTrack != null)
            VideoTrackRenderer(videoTrack!)
          else if (participant.isCameraOn && videoTrack == null)
            Container(
              color: AppColors.overlayMedium,
              child: Center(
                child: Icon(
                  CupertinoIcons.video_camera,
                  color: AppColors.white.withValues(alpha: 0.3),
                  size: AppSpacing.xl,
                ),
              ),
            )
          else
            Center(
              child: CircleAvatar(
                radius: AppSpacing.xl,
                backgroundColor:
                    AppColors.primaryColor.withValues(alpha: 0.3),
                backgroundImage: participant.avatarUrl != null
                    ? NetworkImage(participant.avatarUrl!)
                    : null,
                child: participant.avatarUrl == null
                    ? Text(
                        participant.displayName.isNotEmpty
                            ? participant.displayName[0].toUpperCase()
                            : '?',
                        style: TextStyle(
                          color: AppColors.white,
                          fontSize: AppTypography.xxl,
                          fontWeight: AppTypography.semiBold,
                        ),
                      )
                    : null,
              ),
            ),
          if (showName)
            Positioned(
              left: AppSpacing.sm,
              bottom: AppSpacing.sm,
              child: Container(
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.sm,
                  vertical: AppSpacing.xs,
                ),
                decoration: BoxDecoration(
                  color: AppColors.overlayMedium,
                  borderRadius:
                      BorderRadius.circular(AppSpacing.smallBorderRadius),
                ),
                child: Text(
                  participant.displayName,
                  style: TextStyle(
                    color: AppColors.white,
                    fontSize: AppTypography.sm,
                    fontWeight: AppTypography.normal,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ),
          if (participant.isMuted)
            Positioned(
              right: AppSpacing.sm,
              bottom: AppSpacing.sm,
              child: Container(
                width: AppSpacing.iconMedium,
                height: AppSpacing.iconMedium,
                decoration: BoxDecoration(
                  color: AppColors.overlayMedium,
                  shape: BoxShape.circle,
                ),
                child: Icon(
                  CupertinoIcons.mic_off,
                  color: AppColors.error,
                  size: AppSpacing.iconSmall,
                ),
              ),
            ),
        ],
      ),
    );
  }
}
