import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
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

class OutgoingCallPage extends ConsumerStatefulWidget {
  const OutgoingCallPage({
    super.key,
    required this.callId,
  });

  final String callId;

  @override
  ConsumerState<OutgoingCallPage> createState() => _OutgoingCallPageState();
}

class _OutgoingCallPageState extends ConsumerState<OutgoingCallPage> {
  @override
  void initState() {
    super.initState();
    ref.read(callTimerProvider.notifier).start();
  }

  @override
  void dispose() {
    super.dispose();
  }

  void _onCallStatusChanged(CallSessionState state) {
    if (!mounted) return;
    if (state.status == CallStatus.inCall) {
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
    final timer = ref.watch(callTimerProvider);

    ref.listen<CallSessionState>(callSessionProvider, (_, next) {
      _onCallStatusChanged(next);
    });

    final participants = session.session?.participants ?? [];
    final remoteName = participants.length > 1
        ? participants
            .where((p) => p.role != 'initiator')
            .map((p) => p.userId)
            .join(', ')
        : '用户';

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
                '正在呼叫...',
                style: TextStyle(
                  color: AppColors.white.withValues(alpha: 0.7),
                  fontSize: AppTypography.md,
                  fontWeight: AppTypography.normal,
                ),
              ),
              SizedBox(height: AppSpacing.sm),
              Text(
                remoteName,
                style: TextStyle(
                  color: AppColors.white,
                  fontSize: AppTypography.xxl,
                  fontWeight: AppTypography.semiBold,
                ),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
              SizedBox(height: AppSpacing.sm),
              Text(
                timer.formattedTime,
                style: TextStyle(
                  color: AppColors.white.withValues(alpha: 0.5),
                  fontSize: AppTypography.sm,
                  fontWeight: AppTypography.normal,
                  fontFeatures: const [FontFeature.tabularFigures()],
                ),
              ),
              const Spacer(),
              CallerAvatarPulse(
                displayName: remoteName,
              ),
              const Spacer(),
              _buildCancelButton(),
              SizedBox(height: AppSpacing.xl * 2),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildCancelButton() {
    return GestureDetector(
      onTap: () {
        ref.read(callSessionProvider.notifier).cancelCall();
        ref.read(callTimerProvider.notifier).reset();
      },
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: AppSpacing.iconButtonMinSizeMd,
            height: AppSpacing.iconButtonMinSizeMd,
            decoration: const BoxDecoration(
              color: AppColors.error,
              shape: BoxShape.circle,
            ),
            child: Icon(
              CupertinoIcons.phone_down_fill,
              color: AppColors.white,
              size: AppSpacing.xl,
            ),
          ),
          SizedBox(height: AppSpacing.sm),
          Text(
            '取消',
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
