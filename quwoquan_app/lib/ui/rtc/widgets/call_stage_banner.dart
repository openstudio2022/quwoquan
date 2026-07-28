import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/widgets/app_request_feedback.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/errors/runtime_error_display.dart';
import 'package:quwoquan_app/ui/rtc/models/call_state.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_participants_provider.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_session_provider.dart';
import 'package:quwoquan_app/ui/rtc/widgets/call_quality_indicator.dart';

/// 通话过程态横幅：连接中/振铃/单人等待/重连/弱网/已结束等的统一可见反馈。
///
/// 过程态由 [resolveCallStage] 单一派生，本组件只负责把 [CallStage] 映射为
/// 文案与样式（R24：不在页面里各自拼接过程态）。
class CallStageBanner extends ConsumerWidget {
  const CallStageBanner({super.key, this.onRetry});

  final VoidCallback? onRetry;

  /// [CallStage] -> 用户可见文案（统一来自 [UITextConstants]）。
  static String messageFor(CallStage stage) {
    return switch (stage) {
      CallStage.connecting => CallText.callStageConnecting,
      CallStage.ringing => CallText.callStageRinging,
      CallStage.waitingPeer => CallText.callStageWaitingPeer,
      CallStage.reconnecting => CallText.callStageReconnecting,
      CallStage.weakNetwork => CallText.callStageWeakNetwork,
      CallStage.peerNoAnswer => CallText.callStagePeerNoAnswer,
      CallStage.peerLeft => CallText.callStagePeerLeft,
      CallStage.ended => CallText.callStageEnded,
      CallStage.inCall => CallText.callOngoing,
    };
  }

  /// 通话中（[CallStage.inCall]）无需横幅；其余过程态均提示。
  static bool shouldShow(CallStage stage) => stage != CallStage.inCall;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(callSessionProvider);
    final participants = ref.watch(callParticipantsProvider);
    final quality = ref.watch(callQualityProvider);
    final failure = session.failure;

    if (failure != null) {
      return Container(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.sm,
        ),
        decoration: BoxDecoration(
          color: AppColors.error.withValues(alpha: 0.92),
          borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Flexible(
              child: Text(
                runtimeFailureDisplayMessage(failure),
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: AppColors.white,
                  fontSize: AppTypography.sm,
                  fontWeight: AppTypography.medium,
                ),
              ),
            ),
            if (onRetry != null) ...[
              SizedBox(width: AppSpacing.sm),
              CupertinoButton(
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.sm,
                  vertical: AppSpacing.xs,
                ),
                minimumSize: const Size(
                  AppSpacing.minInteractiveSize,
                  AppSpacing.minInteractiveSize,
                ),
                onPressed: onRetry,
                child: Text(
                  FoundationText.retry,
                  style: TextStyle(
                    color: AppColors.white,
                    fontSize: AppTypography.sm,
                    fontWeight: AppTypography.semiBold,
                  ),
                ),
              ),
            ],
          ],
        ),
      );
    }

    final connectedPeerCount = participants.connectedParticipants
        .where((p) => !p.isLocal)
        .length;
    final stage = resolveCallStage(
      status: session.status,
      connectedPeerCount: connectedPeerCount,
      isReconnecting: session.isReconnecting,
      isWeakNetwork:
          quality == NetworkQuality.weak || quality == NetworkQuality.poor,
      endReason: EndReason.fromString(session.session?.endReason),
    );

    if (!shouldShow(stage)) {
      return const SizedBox.shrink();
    }

    final isAlert =
        stage == CallStage.reconnecting || stage == CallStage.weakNetwork;
    final background = isAlert
        ? AppColors.warning.withValues(alpha: 0.92)
        : AppColors.overlayDark;

    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.sm,
      ),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (stage == CallStage.connecting ||
              stage == CallStage.reconnecting) ...[
            SizedBox(
              width: AppSpacing.iconSmall,
              height: AppSpacing.iconSmall,
              child: AppRequestFeedback.inline(indicatorColor: AppColors.white),
            ),
            SizedBox(width: AppSpacing.sm),
          ],
          Flexible(
            child: Text(
              messageFor(stage),
              textAlign: TextAlign.center,
              style: TextStyle(
                color: AppColors.white,
                fontSize: AppTypography.sm,
                fontWeight: AppTypography.medium,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
