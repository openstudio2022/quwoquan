import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/ui/rtc/models/call_state.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_session_provider.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_timer_provider.dart';
import 'package:quwoquan_app/ui/rtc/widgets/caller_avatar_pulse.dart';

class IncomingCallPage extends ConsumerStatefulWidget {
  const IncomingCallPage({
    super.key,
    required this.callId,
  });

  final String callId;

  @override
  ConsumerState<IncomingCallPage> createState() => _IncomingCallPageState();
}

class _IncomingCallPageState extends ConsumerState<IncomingCallPage> {
  @override
  void initState() {
    super.initState();
    HapticFeedback.heavyImpact();
  }

  void _onCallStatusChanged(CallSessionState state) {
    if (!mounted) return;
    if (state.status == CallStatus.inCall) {
      ref.read(callTimerProvider.notifier).start();
      final isVideo = state.callType.isVideo;
      final route = isVideo
          ? '/rtc/video/${widget.callId}'
          : '/rtc/voice/${widget.callId}';
      context.go(route);
    } else if (state.status == CallStatus.ended) {
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

    final initiatorId = session.session?.initiatorId ?? '';
    final isVideo = session.callType.isVideo;

    return Scaffold(
      backgroundColor: Colors.transparent,
      body: Container(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [
              AppColors.overlayDark,
              AppColors.overlayStrong,
            ],
          ),
        ),
        child: SafeArea(
          child: Column(
            children: [
              SizedBox(height: AppSpacing.xl * 2),
              Text(
                '$initiatorId 邀请你${isVideo ? '视频' : '语音'}通话',
                style: TextStyle(
                  color: AppColors.white.withValues(alpha: 0.8),
                  fontSize: AppTypography.md,
                  fontWeight: AppTypography.normal,
                ),
                textAlign: TextAlign.center,
              ),
              SizedBox(height: AppSpacing.sm),
              Text(
                initiatorId,
                style: TextStyle(
                  color: AppColors.white,
                  fontSize: AppTypography.xxl,
                  fontWeight: AppTypography.semiBold,
                ),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
              const Spacer(),
              CallerAvatarPulse(
                displayName: initiatorId,
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
            label: '拒绝',
            color: AppColors.error,
            onTap: () {
              ref.read(callSessionProvider.notifier).rejectCall(widget.callId);
            },
          ),
          _CallActionButton(
            icon: session.callType.isVideo
                ? CupertinoIcons.video_camera
                : CupertinoIcons.phone,
            label: '接听',
            color: AppColors.success,
            onTap: () {
              ref.read(callSessionProvider.notifier).answerCall(widget.callId);
            },
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
    return GestureDetector(
      onTap: onTap,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: AppSpacing.iconButtonMinSizeMd,
            height: AppSpacing.iconButtonMinSizeMd,
            decoration: BoxDecoration(
              color: color,
              shape: BoxShape.circle,
            ),
            child: Icon(
              icon,
              color: AppColors.white,
              size: AppSpacing.xl,
            ),
          ),
          SizedBox(height: AppSpacing.sm),
          Text(
            label,
            style: TextStyle(
              color: AppColors.white,
              fontSize: AppTypography.sm,
              fontWeight: AppTypography.normal,
            ),
          ),
        ],
      ),
    );
  }
}
