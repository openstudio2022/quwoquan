import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/services/active_call_service.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/ui/rtc/models/call_layout_mode.dart';
import 'package:quwoquan_app/ui/rtc/models/call_participant.dart';
import 'package:quwoquan_app/ui/rtc/models/call_state.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_participants_provider.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_session_provider.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_timer_provider.dart';
import 'package:quwoquan_app/ui/rtc/widgets/call_controls_bar.dart';
import 'package:quwoquan_app/ui/rtc/widgets/call_duration_badge.dart';
import 'package:quwoquan_app/ui/rtc/widgets/call_quality_indicator.dart';
import 'package:quwoquan_app/ui/rtc/widgets/participant_list_sheet.dart';
import 'package:quwoquan_app/ui/rtc/widgets/speaker_highlight_layout.dart';
import 'package:quwoquan_app/ui/rtc/widgets/video_grid_layout.dart';

class VideoCallPage extends ConsumerStatefulWidget {
  const VideoCallPage({
    super.key,
    required this.callId,
  });

  final String callId;

  @override
  ConsumerState<VideoCallPage> createState() => _VideoCallPageState();
}

class _VideoCallPageState extends ConsumerState<VideoCallPage> {
  CallLayoutMode _layoutMode = CallLayoutMode.grid;
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
    _controlsHideTimer = Timer(const Duration(seconds: 3), () {
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
    final participantsState = ref.watch(callParticipantsProvider);

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

    final participants = participantsState.connectedParticipants.isNotEmpty
        ? participantsState.connectedParticipants
        : participantsState.participants;

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
        backgroundColor: AppColors.black,
        child: GestureDetector(
          onTap: _toggleControls,
          behavior: HitTestBehavior.opaque,
          onScaleUpdate: (details) {
            if (details.scale > 1.2 && _layoutMode == CallLayoutMode.grid) {
              setState(() => _layoutMode = CallLayoutMode.speaker);
            } else if (details.scale < 0.8 &&
                _layoutMode == CallLayoutMode.speaker) {
              setState(() => _layoutMode = CallLayoutMode.grid);
            }
          },
          child: Stack(
            fit: StackFit.expand,
            children: [
              _buildVideoArea(participants, participantsState),
              _buildOverlayControls(session),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildVideoArea(
    List<CallParticipant> participants,
    CallParticipantsState state,
  ) {
    if (_layoutMode == CallLayoutMode.speaker) {
      return SpeakerHighlightLayout(
        participants: participants,
        activeSpeaker: state.activeSpeaker,
        lockedSpeakerId: state.lockedSpeakerId,
        onTapThumbnail: (userId) {
          ref.read(callParticipantsProvider.notifier).lockSpeaker(userId);
        },
      );
    }

    return VideoGridLayout(
      participants: participants,
      activeSpeakerId: state.activeSpeakerId,
    );
  }

  Widget _buildOverlayControls(CallSessionState session) {
    return AnimatedOpacity(
      opacity: _controlsVisible ? 1.0 : 0.0,
      duration: const Duration(milliseconds: 250),
      child: IgnorePointer(
        ignoring: !_controlsVisible,
        child: Stack(
          children: [
            Positioned(
              top: 0,
              left: 0,
              right: 0,
              child: Container(
                padding: EdgeInsets.only(
                  top: MediaQuery.paddingOf(context).top + AppSpacing.sm,
                  left: AppSpacing.md,
                  right: AppSpacing.md,
                  bottom: AppSpacing.sm,
                ),
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [
                      AppColors.overlayStrong,
                      AppColors.overlayStrong.withValues(alpha: 0.0),
                    ],
                  ),
                ),
                child: Row(
                  children: [
                    if (session.isRecording)
                      Container(
                        padding: EdgeInsets.symmetric(
                          horizontal: AppSpacing.sm,
                          vertical: AppSpacing.xs,
                        ),
                        decoration: BoxDecoration(
                          color: AppColors.error.withValues(alpha: 0.8),
                          borderRadius: BorderRadius.circular(
                            AppSpacing.smallBorderRadius,
                          ),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Container(
                              width: AppSpacing.sm,
                              height: AppSpacing.sm,
                              decoration: const BoxDecoration(
                                color: AppColors.white,
                                shape: BoxShape.circle,
                              ),
                            ),
                            SizedBox(width: AppSpacing.xs),
                            Text(
                              'REC',
                              style: TextStyle(
                                color: AppColors.white,
                                fontSize: AppTypography.xs,
                                fontWeight: AppTypography.semiBold,
                              ),
                            ),
                          ],
                        ),
                      ),
                    const Spacer(),
                    const CallDurationBadge(showBackground: true),
                    const Spacer(),
                    const CallQualityIndicator(),
                  ],
                ),
              ),
            ),
            Positioned(
              top: MediaQuery.paddingOf(context).top + AppSpacing.xl * 2,
              right: AppSpacing.md,
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  _buildParticipantListButton(session),
                  SizedBox(width: AppSpacing.sm),
                  _buildLayoutToggle(),
                ],
              ),
            ),
            Positioned(
              left: 0,
              right: 0,
              bottom: 0,
              child: CallControlsBar(
                callType: CallType.video,
                autoHide: false,
                onHangup: () {
                  ref.read(callSessionProvider.notifier).hangupCall();
                  ref.read(callTimerProvider.notifier).reset();
                },
                onInvite: () {
                  context.push(AppRoutePaths.rtcPickParticipants, extra: {
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
    );
  }

  Widget _buildLayoutToggle() {
    return GestureDetector(
      onTap: () {
        setState(() => _layoutMode = _layoutMode.toggle());
        _startControlsHideTimer();
      },
      child: Container(
        width: AppSpacing.minInteractiveSize,
        height: AppSpacing.minInteractiveSize,
        decoration: BoxDecoration(
          color: AppColors.overlayMedium,
          borderRadius: BorderRadius.circular(AppSpacing.sm),
        ),
        child: Icon(
          _layoutMode.isGrid
              ? CupertinoIcons.person_2
              : CupertinoIcons.square_grid_2x2,
          color: AppColors.white,
          size: AppSpacing.iconMedium,
        ),
      ),
    );
  }

  Widget _buildParticipantListButton(CallSessionState session) {
    return GestureDetector(
      onTap: () {
        showCupertinoModalPopup<void>(
          context: context,
          builder: (_) => Container(
            decoration: BoxDecoration(
              color: CupertinoColors.systemBackground.resolveFrom(context),
              borderRadius: BorderRadius.vertical(top: Radius.circular(AppSpacing.borderRadius)),
            ),
            child: ParticipantListSheet(
              maxParticipants: session.session?.maxParticipants ?? 32,
              onInviteMore: () {
                Navigator.of(context).pop();
                context.push(
                  AppRoutePaths.rtcPickParticipants,
                  extra: <String, dynamic>{
                    'callId': widget.callId,
                    'maxParticipants': session.session?.maxParticipants ?? 32,
                  },
                );
              },
            ),
          ),
        );
      },
      child: Container(
        width: AppSpacing.minInteractiveSize,
        height: AppSpacing.minInteractiveSize,
        decoration: BoxDecoration(
          color: AppColors.overlayMedium,
          borderRadius: BorderRadius.circular(AppSpacing.sm),
        ),
        child: Icon(
          CupertinoIcons.person_2,
          color: AppColors.white,
          size: AppSpacing.iconMedium,
        ),
      ),
    );
  }
}
