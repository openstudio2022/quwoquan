import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/presentation/call_ended_feedback.dart';
import 'package:quwoquan_app/design_system/layout/app_scaffold.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/domain/call_state.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/call_session_provider.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/call_timer_provider.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/presentation/call_permission_guard.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/presentation/call_stage_chrome.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/presentation/call_stage_banner.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/presentation/caller_avatar_pulse.dart';

class IncomingCallPage extends ConsumerStatefulWidget {
  const IncomingCallPage({super.key, required this.callId});

  final String callId;

  @override
  ConsumerState<IncomingCallPage> createState() => _IncomingCallPageState();
}

class _IncomingCallPageState extends ConsumerState<IncomingCallPage> {
  @override
  void initState() {
    super.initState();
    HapticFeedback.heavyImpact();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      unawaited(
        ref
            .read(callSessionProvider.notifier)
            .refreshIncomingCall(widget.callId),
      );
    });
  }

  /// 接听前权限预检：麦克风为硬门槛；视频缺摄像头降级为仅语音继续。
  Future<void> _onAccept(CallType callType) async {
    final outcome = await CallPermissionGuard.ensure(
      context,
      callType: callType,
    );
    if (!mounted || outcome == CallPermissionOutcome.blocked) {
      return;
    }
    ref.read(callSessionProvider.notifier).answerCall(widget.callId);
  }

  void _onCallStatusChanged(CallSessionState state) {
    if (!mounted) return;
    if (state.status == CallStatus.inCall) {
      ref.read(callTimerProvider.notifier).start();
      final isVideo = state.callType.isVideo;
      final route = isVideo
          ? AppRoutePaths.rtcVideo(callId: widget.callId)
          : AppRoutePaths.rtcVoice(callId: widget.callId);
      context.go(route);
    } else if (state.status == CallStatus.ended) {
      // 超时未接的终态原因在跳离前提示（跳离会吞掉页内 banner）。
      final feedback = callEndedFeedbackText(
        endReason: state.session?.endReason,
        outgoing: false,
      );
      if (feedback != null) {
        AppToast.show(context, feedback);
      }
      if (context.canPop()) {
        context.pop();
      } else {
        context.go(AppRoutePaths.chat);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final session = ref.watch(callSessionProvider);

    ref.listen<CallSessionState>(callSessionProvider, (_, next) {
      _onCallStatusChanged(next);
    });

    final presentation = session.incomingPresentation;
    final initiatorId =
        presentation?.callerId ?? session.session?.initiatorId ?? '';
    final callerName = presentation?.displayName.trim().isNotEmpty == true
        ? presentation!.displayName.trim()
        : initiatorId;
    final isVideo = session.callType.isVideo;
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final onGradientFg = CallStageChrome.primaryOnGradient(isDark);

    return AppScaffold(
      backgroundColor: AppColors.transparent,
      body: Container(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: CallStageChrome.backgroundGradient(isDark),
          ),
        ),
        child: SafeArea(
          child: Column(
            children: [
              SizedBox(height: AppSpacing.xl * 2),
              Text(
                '$callerName ${isVideo ? CallText.callIncomingVideo : CallText.callIncomingVoice}',
                style: TextStyle(
                  color: onGradientFg.withValues(alpha: 0.8),
                  fontSize: AppTypography.md,
                  fontWeight: AppTypography.normal,
                ),
                textAlign: TextAlign.center,
              ),
              SizedBox(height: AppSpacing.sm),
              Text(
                callerName,
                style: TextStyle(
                  color: onGradientFg,
                  fontSize: AppTypography.xxl,
                  fontWeight: AppTypography.semiBold,
                ),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
              const Spacer(),
              CallerAvatarPulse(
                displayName: callerName,
                avatarUrl: presentation?.avatarUrl,
              ),
              SizedBox(height: AppSpacing.md),
              CallStageBanner(
                onRetry: () => ref
                    .read(callSessionProvider.notifier)
                    .refreshIncomingCall(widget.callId),
              ),
              const Spacer(),
              _buildActionButtons(session),
              SizedBox(height: AppSpacing.xl * 2),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildActionButtons(CallSessionState session) {
    return Padding(
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.xl * 2),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceEvenly,
        children: [
          _CallActionButton(
            icon: CupertinoIcons.phone_down_fill,
            label: CallText.callReject,
            color: AppColors.error,
            onTap: () {
              ref.read(callSessionProvider.notifier).rejectCall(widget.callId);
            },
          ),
          _CallActionButton(
            icon: session.callType.isVideo
                ? CupertinoIcons.video_camera
                : CupertinoIcons.phone,
            label: CallText.callAccept,
            color: AppColors.primaryColor,
            onTap: () => _onAccept(session.callType),
          ),
        ],
      ),
    );
  }
}

class _CallActionButton extends StatelessWidget {
  const _CallActionButton({
    required this.icon,
    required this.label,
    required this.color,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    // 接听/拒接合并为单一可点击语义节点，读屏用户可直接寻址关键动作。
    return Semantics(
      button: true,
      label: label,
      excludeSemantics: true,
      child: GestureDetector(
        onTap: onTap,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: AppSpacing.iconButtonMinSizeMd,
              height: AppSpacing.iconButtonMinSizeMd,
              decoration: BoxDecoration(color: color, shape: BoxShape.circle),
              child: Icon(
                icon,
                color: AppColors.callStageForeground,
                size: AppSpacing.xl,
              ),
            ),
            SizedBox(height: AppSpacing.sm),
            Text(
              label,
              style: TextStyle(
                color: AppColors.callStageForeground,
                fontSize: AppTypography.sm,
                fontWeight: AppTypography.normal,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
