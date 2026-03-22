import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/rtc/models/call_participant_dto.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/services/active_call_service.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/ui/rtc/models/call_state.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_session_provider.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_timer_provider.dart';
import 'package:quwoquan_app/ui/rtc/widgets/call_controls_bar.dart';
import 'package:quwoquan_app/ui/rtc/widgets/call_duration_badge.dart';
import 'package:quwoquan_app/ui/rtc/widgets/call_quality_indicator.dart';
import 'package:quwoquan_app/ui/rtc/widgets/participant_list_sheet.dart';

class VoiceCallPage extends ConsumerStatefulWidget {
  const VoiceCallPage({super.key, required this.callId});

  final String callId;

  @override
  ConsumerState<VoiceCallPage> createState() => _VoiceCallPageState();
}

class _VoiceCallPageState extends ConsumerState<VoiceCallPage> {
  bool _controlsVisible = true;
  Timer? _controlsHideTimer;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final timer = ref.read(callTimerProvider);
      if (!timer.isRunning) {
        ref.read(callTimerProvider.notifier).start();
      }
    });
    _startControlsHideTimer();
  }

  @override
  void dispose() {
    _controlsHideTimer?.cancel();
    super.dispose();
  }

  void _startControlsHideTimer() {
    _controlsHideTimer?.cancel();
    _controlsHideTimer = Timer(const Duration(seconds: 5), () {
      if (mounted) setState(() => _controlsVisible = false);
    });
  }

  void _toggleControls() {
    setState(() => _controlsVisible = !_controlsVisible);
    if (_controlsVisible) _startControlsHideTimer();
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
          context.go(AppRoutePaths.chat);
        }
      }
    });

    final participants = session.session?.participants ?? [];

    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) {
          ref.read(activeCallProvider.notifier).enterPipMode();
          if (context.canPop()) {
            context.pop();
          } else {
            context.go(AppRoutePaths.chat);
          }
        }
      },
      child: AppScaffold(
        backgroundColor: Colors.transparent,
        child: GestureDetector(
          onTap: _toggleControls,
          behavior: HitTestBehavior.opaque,
          child: Container(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [AppColors.overlayDark, AppColors.overlayStrong],
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
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        _TopActionButton(
                          icon: CupertinoIcons.person_2,
                          onTap: () {
                            showCupertinoModalPopup<void>(
                              context: context,
                              barrierColor: Colors.transparent,
                              builder: (_) => ParticipantListSheet(
                                maxParticipants:
                                    session.session?.maxParticipants ?? 32,
                                onInviteMore: () {
                                  Navigator.of(context).pop();
                                  context.push(
                                    AppRoutePaths.rtcPickParticipants,
                                    extra: <String, dynamic>{
                                      'callId': widget.callId,
                                      'maxParticipants':
                                          session.session?.maxParticipants ??
                                          32,
                                    },
                                  );
                                },
                              ),
                            );
                          },
                        ),
                        SizedBox(width: AppSpacing.sm),
                        const CallQualityIndicator(),
                      ],
                    ),
                  ),
                  Positioned(
                    left: 0,
                    right: 0,
                    bottom: 0,
                    child: AnimatedOpacity(
                      opacity: _controlsVisible ? 1.0 : 0.0,
                      duration: const Duration(milliseconds: 250),
                      child: IgnorePointer(
                        ignoring: !_controlsVisible,
                        child: CallControlsBar(
                          callType: CallType.audio,
                          autoHide: false,
                          onHangup: () {
                            ref.read(callSessionProvider.notifier).hangupCall();
                            ref.read(callTimerProvider.notifier).reset();
                          },
                          onInvite: () {
                            context.push(
                              AppRoutePaths.rtcPickParticipants,
                              extra: {
                                'callId': widget.callId,
                                'maxParticipants':
                                    session.session?.maxParticipants ?? 32,
                              },
                            );
                          },
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildParticipantAvatars(List<CallParticipantDto> participants) {
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

class _TopActionButton extends StatelessWidget {
  const _TopActionButton({required this.icon, required this.onTap});

  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: AppSpacing.minInteractiveSize,
        height: AppSpacing.minInteractiveSize,
        decoration: BoxDecoration(
          color: AppColors.overlayMedium,
          borderRadius: BorderRadius.circular(AppSpacing.sm),
        ),
        child: Icon(icon, color: AppColors.white, size: AppSpacing.iconMedium),
      ),
    );
  }
}
