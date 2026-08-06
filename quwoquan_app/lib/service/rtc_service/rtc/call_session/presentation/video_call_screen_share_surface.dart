import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/runtime/platform/rtc_room_service.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';

/// 通话中的真实屏幕共享画面。业务共享状态已到达但 LiveKit 轨道尚未订阅时，
/// 显示明确的接收态，避免退回摄像头宫格造成“共享成功但看不到”的误解。
class VideoCallScreenShareSurface extends StatelessWidget {
  const VideoCallScreenShareSurface({super.key, required this.track});

  final RtcVideoTrack? track;

  @override
  Widget build(BuildContext context) {
    final activeTrack = track;
    return ColoredBox(
      key: const ValueKey<String>('video-call-screen-share-surface'),
      color: AppColors.overlayDark,
      child: activeTrack == null
          ? Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  AppRequestFeedback.inline(indicatorColor: AppColors.white),
                  SizedBox(height: AppSpacing.sm),
                  Text(
                    CallText.callScreenShareConnecting,
                    style: TextStyle(
                      color: AppColors.white,
                      fontSize: AppTypography.body,
                      fontWeight: AppTypography.medium,
                    ),
                  ),
                ],
              ),
            )
          : RtcVideoTrackRenderer(
              track: activeTrack,
              fit: RtcVideoViewFit.contain,
            ),
    );
  }
}
