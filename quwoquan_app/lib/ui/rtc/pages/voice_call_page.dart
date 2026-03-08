import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/rtc/models/call_participant_dto.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/services/active_call_service.dart';
import 'package:quwoquan_app/ui/rtc/models/call_state.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_session_provider.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_timer_provider.dart';
import 'package:quwoquan_app/ui/rtc/widgets/call_controls_bar.dart';
import 'package:quwoquan_app/ui/rtc/widgets/call_duration_badge.dart';
import 'package:quwoquan_app/ui/rtc/widgets/call_quality_indicator.dart';

class VoiceCallPage extends ConsumerStatefulWidget {
  const VoiceCallPage({
    super.key,
    required this.callId,
  });

  final String callId;

  @override
  ConsumerState<VoiceCallPage> createState() => _VoiceCallPageState();
}

class _VoiceCallPageState extends ConsumerState<VoiceCallPage> {
  @override
  void initState() {
    super.initState();
    final timer = ref.read(callTimerProvider);
    if (!timer.isRunning) {
      ref.read(callTimerProvider.notifier).start();
    }
  }

  @override
  Widget build(BuildContext context) {
    final session = ref.watch(callSessionProvider);

    ref.listen<CallSessionState>(callSessionProvider, (_, next) {
      if (!mounted) return;
      if (next.status == CallStatus.ended) {
        ref.read(callTimerProvider.notifier).reset();
        if (context.canPop()) {
          context.pop();
        } else {
          context.go('/chat');
        }
      }
    });

    final participants = session.session?.participants ?? [];

    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) {
          ref.read(activeCallProvider.notifier).enterPipMode();
          context.pop();
        }
      },
      child: Scaffold(
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
            bottom: false,
            child: Stack(
              children: [
                Column(
                  children: [
                    SizedBox(height: AppSpacing.xl),
                    const CallDurationBadge(),
                    SizedBox(height: AppSpacing.xl),
                    Expanded(
                      child: Center(
                        child: _buildParticipantAvatars(participants),
                      ),
                    ),
                  ],
                ),
                Positioned(
                  top: AppSpacing.sm,
                  right: AppSpacing.md,
                  child: const CallQualityIndicator(),
                ),
                Positioned(
                  left: 0,
                  right: 0,
                  bottom: 0,
                  child: CallControlsBar(
                    callType: CallType.audio,
                    onHangup: () {
                      ref.read(callSessionProvider.notifier).hangupCall();
                      ref.read(callTimerProvider.notifier).reset();
                    },
                    onInvite: () {
                      context.push('/rtc/pick-participants', extra: {
                        'callId': widget.callId,
                        'maxParticipants':
                            session.session?.maxParticipants ?? 32,
                      });
                    },
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildParticipantAvatars(
    List<CallParticipantDto> participants,
  ) {
    if (participants.isEmpty) {
      return Icon(
        CupertinoIcons.phone,
        color: AppColors.white.withValues(alpha: 0.3),
        size: AppSpacing.oneHundred,
      );
    }

    final remoteParticipants = participants
        .where((p) => p.role != 'initiator')
        .toList();

    if (remoteParticipants.isEmpty) {
      return Icon(
        CupertinoIcons.phone,
        color: AppColors.white.withValues(alpha: 0.3),
        size: AppSpacing.oneHundred,
      );
    }

    if (remoteParticipants.length == 1) {
      final userId = remoteParticipants.first.userId;
      return Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          CircleAvatar(
            radius: AppSpacing.oneHundred / 2,
            backgroundColor: AppColors.primaryColor.withValues(alpha: 0.3),
            child: Text(
              userId.isNotEmpty ? userId[0].toUpperCase() : '?',
              style: TextStyle(
                color: AppColors.white,
                fontSize: AppTypography.xxxl,
                fontWeight: AppTypography.semiBold,
              ),
            ),
          ),
          SizedBox(height: AppSpacing.md),
          Text(
            userId,
            style: TextStyle(
              color: AppColors.white,
              fontSize: AppTypography.lg,
              fontWeight: AppTypography.medium,
            ),
          ),
        ],
      );
    }

    return Wrap(
      alignment: WrapAlignment.center,
      spacing: AppSpacing.sm,
      runSpacing: AppSpacing.sm,
      children: remoteParticipants.take(6).map((p) {
        return CircleAvatar(
          radius: AppSpacing.xl,
          backgroundColor: AppColors.primaryColor.withValues(alpha: 0.3),
          child: Text(
            p.userId.isNotEmpty ? p.userId[0].toUpperCase() : '?',
            style: TextStyle(
              color: AppColors.white,
              fontSize: AppTypography.lg,
              fontWeight: AppTypography.semiBold,
            ),
          ),
        );
      }).toList(),
    );
  }
}
