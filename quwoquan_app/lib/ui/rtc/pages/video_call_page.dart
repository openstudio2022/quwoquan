import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/services/active_call_service.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/ui/rtc/models/call_layout_mode.dart';
import 'package:quwoquan_app/ui/rtc/models/call_participant_picker_route_extra.dart';
import 'package:quwoquan_app/ui/rtc/models/call_participant.dart';
import 'package:quwoquan_app/ui/rtc/models/call_state.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_participants_provider.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_session_provider.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_timer_provider.dart';
import 'package:quwoquan_app/ui/rtc/widgets/call_controls_bar.dart';
import 'package:quwoquan_app/ui/rtc/widgets/call_duration_badge.dart';
import 'package:quwoquan_app/ui/rtc/widgets/call_quality_indicator.dart';
import 'package:quwoquan_app/ui/rtc/widgets/call_stage_banner.dart';
import 'package:quwoquan_app/ui/rtc/widgets/participant_list_sheet.dart';
import 'package:quwoquan_app/ui/rtc/widgets/speaker_highlight_layout.dart';
import 'package:quwoquan_app/ui/rtc/widgets/video_call_screen_share_status.dart';
import 'package:quwoquan_app/ui/rtc/widgets/video_call_screen_share_surface.dart';
import 'package:quwoquan_app/ui/rtc/widgets/video_grid_layout.dart';

class VideoCallPage extends ConsumerStatefulWidget {
  const VideoCallPage({super.key, required this.callId});

  final String callId;

  @override
  ConsumerState<VideoCallPage> createState() => _VideoCallPageState();
}

class _VideoCallPageState extends ConsumerState<VideoCallPage> {
  CallLayoutMode _layoutMode = CallLayoutMode.grid;
  bool _controlsVisible = true;
  bool _controlsLocked = false;
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
      if (mounted && !_controlsLocked) {
        setState(() => _controlsVisible = false);
      }
    });
  }

  void _toggleControls() {
    if (_controlsLocked) return;
    setState(() => _controlsVisible = !_controlsVisible);
    if (_controlsVisible) _startControlsHideTimer();
  }

  void _toggleControlsLock() {
    setState(() {
      _controlsLocked = !_controlsLocked;
      _controlsVisible = true;
    });
    if (_controlsLocked) {
      _controlsHideTimer?.cancel();
    } else {
      _startControlsHideTimer();
    }
  }

  CallParticipantPickerRouteExtra _invitePickerExtra(
    CallSessionState session,
    int currentParticipantCount,
  ) {
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

    final backdrop = AppColorsFunctional.getColor(
      CupertinoTheme.of(context).brightness == Brightness.dark,
      ColorType.fullBleedMediaBackdrop,
    );
    if (session.isLoading && session.session == null) {
      return AppScaffold(
        backgroundColor: backdrop,
        child: AppRequestFeedback.section(),
      );
    }
    if (session.failure case final failure? when session.session == null) {
      return AppScaffold(
        backgroundColor: backdrop,
        child: SafeArea(
          child: AppPageErrorState(
            semantic: runtimeErrorSemantic(
              context,
              error: failure,
              category: UiErrorCategory.pageLoad,
              scope: UiErrorScope.page,
            ),
            onAction: (action) async {
              if (action.type == UiErrorActionType.retry ||
                  action.type == UiErrorActionType.resubmit) {
                await ref
                    .read(callSessionProvider.notifier)
                    .joinCall(widget.callId);
              }
            },
          ),
        ),
      );
    }

    final participants = participantsState.connectedParticipants.isNotEmpty
        ? participantsState.connectedParticipants
        : participantsState.participants;
    final declaredParticipantCount = session.session?.participantCount ?? 0;
    final observedParticipantCount = participantsState.participants.length;
    final currentParticipantCount =
        declaredParticipantCount > observedParticipantCount
        ? declaredParticipantCount
        : observedParticipantCount;

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
        backgroundColor: backdrop,
        child: GestureDetector(
          onTap: _toggleControls,
          behavior: HitTestBehavior.opaque,
          onScaleUpdate: (details) {
            if (_controlsLocked) return;
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
              _buildVideoArea(participants, participantsState, session),
              _buildOverlayControls(session, currentParticipantCount),
              _buildStageBanner(),
              VideoCallScreenShareStatus(
                visible: session.session?.isScreenSharing == true,
                canStop: session.isLocalScreenSharing,
                onStop: () => unawaited(
                  ref.read(callSessionProvider.notifier).stopScreenShare(),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildStageBanner() {
    return Positioned(
      top: MediaQuery.paddingOf(context).top + AppSpacing.xl * 3,
      left: AppSpacing.md,
      right: AppSpacing.md,
      child: Align(
        alignment: Alignment.topCenter,
        child: CallStageBanner(
          onRetry: () =>
              ref.read(callSessionProvider.notifier).retryCurrentCall(),
        ),
      ),
    );
  }

  Widget _buildVideoArea(
    List<CallParticipant> participants,
    CallParticipantsState state,
    CallSessionState session,
  ) {
    if (session.session?.isScreenSharing == true) {
      final declaredSharerId = session.session?.screenShareUserId;
      CallParticipant? sharer;
      for (final participant in participants) {
        if (participant.userId == declaredSharerId) {
          sharer = participant;
          break;
        }
        if (sharer == null && participant.hasScreenShareTrack) {
          sharer = participant;
        }
      }
      final shareSurface = VideoCallScreenShareSurface(
        track: sharer?.screenShareTrack,
      );
      if (sharer == null) {
        return shareSurface;
      }
      return SpeakerHighlightLayout(
        participants: participants,
        activeSpeaker: sharer,
        lockedSpeakerId: state.lockedSpeakerId,
        highlightedContent: shareSurface,
        onTapThumbnail: (userId) {
          ref.read(callParticipantsProvider.notifier).lockSpeaker(userId);
        },
      );
    }
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

  Widget _buildOverlayControls(CallSessionState session, int participantCount) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final topFadeBase = AppColorsFunctional.getColor(
      isDark,
      ColorType.createMediaOverlayBase,
    );
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
                      topFadeBase.withValues(alpha: isDark ? 0.48 : 0.62),
                      topFadeBase.withValues(alpha: 0.0),
                    ],
                  ),
                ),
                child: Row(
                  children: [
                    const Spacer(),
                    const CallDurationBadge(showBackground: true),
                    const Spacer(),
                    const CallQualityIndicator(),
                  ],
                ),
              ),
            ),
            if (!_controlsLocked)
              Positioned(
                top: MediaQuery.paddingOf(context).top + AppSpacing.xl * 2,
                right: AppSpacing.md,
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    _buildParticipantListButton(session, participantCount),
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
                interactionLocked: _controlsLocked,
                onToggleInteractionLock: _toggleControlsLock,
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
                    extra: _invitePickerExtra(session, participantCount),
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildLayoutToggle() {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final fg = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final glass = AppColorsFunctional.getColor(isDark, ColorType.glassSurface);
    return GestureDetector(
      onTap: () {
        setState(() => _layoutMode = _layoutMode.toggle());
        _startControlsHideTimer();
      },
      child: Container(
        width: AppSpacing.minInteractiveSize,
        height: AppSpacing.minInteractiveSize,
        decoration: BoxDecoration(
          color: glass.withValues(alpha: 0.92),
          borderRadius: BorderRadius.circular(AppSpacing.sm),
        ),
        child: Icon(
          _layoutMode.isGrid
              ? CupertinoIcons.person_2
              : CupertinoIcons.square_grid_2x2,
          color: fg,
          size: AppSpacing.iconMedium,
        ),
      ),
    );
  }

  Widget _buildParticipantListButton(
    CallSessionState session,
    int participantCount,
  ) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final fg = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final glass = AppColorsFunctional.getColor(isDark, ColorType.glassSurface);
    return GestureDetector(
      onTap: () {
        showAppBottomModal<void>(
          context: context,
          builder: (sheetContext) => ParticipantListSheet(
            maxParticipants: session.session?.maxParticipants ?? 32,
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
                      extra: _invitePickerExtra(session, participantCount),
                    );
                  },
                ),
              );
            },
          ),
        );
      },
      child: Stack(
        clipBehavior: Clip.none,
        children: [
          Container(
            width: AppSpacing.minInteractiveSize,
            height: AppSpacing.minInteractiveSize,
            decoration: BoxDecoration(
              color: glass.withValues(alpha: 0.92),
              borderRadius: BorderRadius.circular(AppSpacing.sm),
            ),
            child: Icon(
              CupertinoIcons.person_2,
              color: fg,
              size: AppSpacing.iconMedium,
            ),
          ),
          if (callParticipantOverflowCount(participantCount) case final count
              when count > 0)
            Positioned(
              key: const ValueKey('video-call-participant-overflow'),
              top: -AppSpacing.xs,
              right: -AppSpacing.xs,
              child: Container(
                constraints: BoxConstraints(
                  minWidth: AppSpacing.iconMedium,
                  minHeight: AppSpacing.iconMedium,
                ),
                padding: EdgeInsets.symmetric(horizontal: AppSpacing.xs),
                decoration: BoxDecoration(
                  color: AppColors.error,
                  borderRadius: BorderRadius.circular(
                    AppSpacing.largeBorderRadius,
                  ),
                ),
                alignment: Alignment.center,
                child: Text(
                  UITextConstants.callAdditionalParticipants(count),
                  style: TextStyle(
                    color: AppColors.white,
                    fontSize: AppTypography.xs,
                    fontWeight: AppTypography.semiBold,
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
