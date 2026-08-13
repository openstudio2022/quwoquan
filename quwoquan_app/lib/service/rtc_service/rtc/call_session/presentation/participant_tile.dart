import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/runtime/platform/rtc_room_service.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/media_device_provider.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/domain/call_participant.dart';
import 'package:quwoquan_app/design_system/spacing/call_surface_motion.dart';

class ParticipantTile extends ConsumerWidget {
  const ParticipantTile({
    super.key,
    required this.participant,
    this.isActiveSpeaker = false,
    this.showName = true,
    this.borderRadius,
    this.videoTrack,
  });

  final CallParticipantViewData participant;
  final bool isActiveSpeaker;
  final bool showName;
  final BorderRadius? borderRadius;
  final RtcVideoTrack? videoTrack;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final effectiveRadius =
        borderRadius ?? BorderRadius.circular(AppSpacing.sm);
    // Prefer the track bound onto the participant VM (synced from LiveKit);
    // fall back to an explicitly passed track for callers that manage it.
    final effectiveTrack = videoTrack ?? participant.videoTrack;
    final mirrorLocalPreview = shouldMirrorLocalPreview(
      isLocal: participant.isLocal,
      cameraPosition: ref.watch(
        mediaDeviceProvider.select((device) => device.cameraPosition),
      ),
    );

    return AnimatedContainer(
      duration: CallSurfaceMotion.stateFade,
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
          if (participant.isCameraOn && effectiveTrack != null)
            RtcVideoTrackRenderer(
              track: effectiveTrack,
              mirror: mirrorLocalPreview,
            )
          else if (participant.isCameraOn && effectiveTrack == null)
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
              child: AppCircularAvatar(
                imageUrl: participant.avatarUrl,
                size: AppSpacing.xl * 2,
                backgroundColor: AppColors.primaryColor.withValues(alpha: 0.3),
                fallback: Text(
                  participant.displayName.isNotEmpty
                      ? participant.displayName[0].toUpperCase()
                      : '?',
                  style: TextStyle(
                    color: AppColors.white,
                    fontSize: AppTypography.xxl,
                    fontWeight: AppTypography.semiBold,
                  ),
                ),
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
                  borderRadius: BorderRadius.circular(
                    AppSpacing.smallBorderRadius,
                  ),
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
          if (!participant.isLocal && participant.needsTrustWarning)
            Positioned(
              left: AppSpacing.sm,
              top: AppSpacing.sm,
              child: Container(
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.sm,
                  vertical: AppSpacing.xs,
                ),
                decoration: BoxDecoration(
                  color: AppColors.warning.withValues(alpha: 0.85),
                  borderRadius: BorderRadius.circular(
                    AppSpacing.smallBorderRadius,
                  ),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      CupertinoIcons.shield_fill,
                      color: AppColors.white,
                      size: AppSpacing.iconSmall,
                    ),
                    SizedBox(width: AppSpacing.xs),
                    Text(
                      CallText.callTrustUnknownBadge,
                      style: TextStyle(
                        color: AppColors.white,
                        fontSize: AppTypography.xs,
                        fontWeight: AppTypography.semiBold,
                      ),
                    ),
                  ],
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
