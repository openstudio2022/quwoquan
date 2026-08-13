import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/active_call_service.dart';
import 'package:quwoquan_app/design_system/surfaces/app_modal_presenter.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/design_system/layout/app_scaffold.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/second_incoming_call_provider.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/domain/call_participant_picker_route_extra.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/domain/call_participant.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/domain/call_state.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/call_participants_provider.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/call_session_provider.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/call_timer_provider.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/presentation/call_stage_chrome.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/presentation/call_controls_bar.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/presentation/call_duration_badge.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/presentation/call_quality_indicator.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/presentation/call_stage_banner.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/presentation/participant_list_sheet.dart';
import 'package:quwoquan_app/design_system/spacing/call_surface_motion.dart';

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
    _controlsHideTimer = Timer(CallSurfaceMotion.voiceControlsAutoHide, () {
      if (mounted) setState(() => _controlsVisible = false);
    });
  }

  void _toggleControls() {
    setState(() => _controlsVisible = !_controlsVisible);
    if (_controlsVisible) _startControlsHideTimer();
  }

  CallParticipantPickerRouteExtra _invitePickerExtra(
    CallSessionState session,
    int observedParticipantCount,
  ) {
    final declaredCount = session.session?.participantCount ?? 0;
    final currentParticipantCount = declaredCount > observedParticipantCount
        ? declaredCount
        : observedParticipantCount;
    return CallParticipantPickerRouteExtra.existingCallInvite(
      callId: widget.callId,
      currentParticipantCount: currentParticipantCount,
      maxParticipants: session.session?.maxParticipants ?? 32,
      conversationId: session.session?.conversationId,
    );
  }

  @override
  Widget build(BuildContext context) {
    final session = ref.watch(callSessionProvider);
    final participantState = ref.watch(callParticipantsProvider);

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

    // 通话中第二来电轻提示：不覆盖通话 UI，展示后消费掉状态。
    ref.listen(secondIncomingCallProvider, (_, envelope) {
      if (!mounted || envelope == null) return;
      ref.read(secondIncomingCallProvider.notifier).consume();
      AppToast.show(context, CallText.callSecondIncomingHint);
    });

    final participants = participantState.participants;
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final stageGradient = CallStageChrome.backgroundGradient(isDark);

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
        backgroundColor: AppColors.transparent,
        child: GestureDetector(
          onTap: _toggleControls,
          behavior: HitTestBehavior.opaque,
          child: Container(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: stageGradient,
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
                      SizedBox(height: AppSpacing.md),
                      CallStageBanner(
                        onRetry: () => ref
                            .read(callSessionProvider.notifier)
                            .retryCurrentCall(),
                      ),
                      SizedBox(height: AppSpacing.md),
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
                            showAppBottomModal<void>(
                              context: context,
                              builder: (sheetContext) => ParticipantListSheet(
                                maxParticipants:
                                    session.session?.maxParticipants ?? 32,
                                onInviteMore: () {
                                  unawaited(
                                    dismissAppModalAndRun(
                                      sheetContext,
                                      action: () {
                                        if (!context.mounted) {
                                          return;
                                        }
                                        context.push(
                                          AppRoutePaths.rtcPickParticipants,
                                          extra: _invitePickerExtra(
                                            session,
                                            participants.length,
                                          ),
                                        );
                                      },
                                    ),
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
                      duration: CallSurfaceMotion.surfaceTransition,
                      child: IgnorePointer(
                        ignoring: !_controlsVisible,
                        child: CallControlsBar(
                          callType: CallType.audio,
                          autoHide: false,
                          onHangup: () async {
                            final result = await ref
                                .read(callSessionProvider.notifier)
                                .hangupCall();
                            if (result.succeeded) {
                              ref.read(callTimerProvider.notifier).reset();
                            }
                          },
                          onInvite: () {
                            context.push(
                              AppRoutePaths.rtcPickParticipants,
                              extra: _invitePickerExtra(
                                session,
                                participants.length,
                              ),
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

  Widget _buildParticipantAvatars(List<CallParticipantViewData> participants) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final mutedFg = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    ).withValues(alpha: 0.35);
    final nameFg = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final onAccent = AppColorsFunctional.getColor(
      isDark,
      ColorType.badgeForeground,
    );

    if (participants.isEmpty) {
      return Icon(
        CupertinoIcons.phone,
        color: mutedFg,
        size: AppSpacing.oneHundred,
      );
    }

    final remoteParticipants = participants
        .where((participant) => !participant.isLocal)
        .toList();

    if (remoteParticipants.isEmpty) {
      return Icon(
        CupertinoIcons.phone,
        color: mutedFg,
        size: AppSpacing.oneHundred,
      );
    }

    if (remoteParticipants.length == 1) {
      final participant = remoteParticipants.first;
      final displayName = participant.displayName;
      return Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          AppCircularAvatar(
            imageUrl: participant.avatarUrl,
            size: AppSpacing.oneHundred,
            backgroundColor: AppColors.primaryColor.withValues(alpha: 0.3),
            fallback: Text(
              displayName.isNotEmpty ? displayName[0].toUpperCase() : '?',
              style: TextStyle(
                color: onAccent,
                fontSize: AppTypography.xxxl,
                fontWeight: AppTypography.semiBold,
              ),
            ),
          ),
          SizedBox(height: AppSpacing.md),
          Text(
            displayName,
            style: TextStyle(
              color: nameFg,
              fontSize: AppTypography.lg,
              fontWeight: AppTypography.medium,
            ),
          ),
        ],
      );
    }

    final overflow = callParticipantOverflowCount(remoteParticipants.length);
    final visibleParticipants = remoteParticipants.take(
      callParticipantSummaryLimit,
    );
    return Wrap(
      alignment: WrapAlignment.center,
      spacing: AppSpacing.sm,
      runSpacing: AppSpacing.sm,
      children: <Widget>[
        ...visibleParticipants.map((participant) {
          return AppCircularAvatar(
            imageUrl: participant.avatarUrl,
            size: AppSpacing.xl * 2,
            backgroundColor: AppColors.primaryColor.withValues(alpha: 0.3),
            fallback: Text(
              participant.displayName.isNotEmpty
                  ? participant.displayName[0].toUpperCase()
                  : '?',
              style: TextStyle(
                color: onAccent,
                fontSize: AppTypography.lg,
                fontWeight: AppTypography.semiBold,
              ),
            ),
          );
        }),
        if (overflow > 0)
          CircleAvatar(
            radius: AppSpacing.xl,
            backgroundColor: AppColors.overlayMedium,
            child: Text(
              UITextConstants.callAdditionalParticipants(overflow),
              style: TextStyle(
                color: onAccent,
                fontSize: AppTypography.sm,
                fontWeight: AppTypography.semiBold,
              ),
            ),
          ),
      ],
    );
  }
}

class _TopActionButton extends StatelessWidget {
  const _TopActionButton({required this.icon, required this.onTap});

  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final fg = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final glass = AppColorsFunctional.getColor(isDark, ColorType.glassSurface);
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: AppSpacing.minInteractiveSize,
        height: AppSpacing.minInteractiveSize,
        decoration: BoxDecoration(
          color: glass.withValues(alpha: 0.92),
          borderRadius: BorderRadius.circular(AppSpacing.sm),
        ),
        child: Icon(icon, color: fg, size: AppSpacing.iconMedium),
      ),
    );
  }
}
