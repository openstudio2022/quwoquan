import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/ui/rtc/models/call_state.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_participants_provider.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_session_provider.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_timer_provider.dart';
import 'package:quwoquan_app/ui/rtc/widgets/call_stage_chrome.dart';
import 'package:quwoquan_app/ui/rtc/widgets/call_stage_banner.dart';
import 'package:quwoquan_app/ui/rtc/widgets/caller_avatar_pulse.dart';

class OutgoingCallPage extends ConsumerStatefulWidget {
  const OutgoingCallPage({super.key, required this.callId});

  final String callId;

  @override
  ConsumerState<OutgoingCallPage> createState() => _OutgoingCallPageState();
}

class _OutgoingCallPageState extends ConsumerState<OutgoingCallPage> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      ref.read(callTimerProvider.notifier).start();
    });
  }

  void _onCallStatusChanged(CallSessionState state) {
    if (!mounted) return;
    if (state.status == CallStatus.inCall) {
      final isVideo = state.callType.isVideo;
      final route = isVideo
          ? AppRoutePaths.rtcVideo(callId: widget.callId)
          : AppRoutePaths.rtcVoice(callId: widget.callId);
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
    final timer = ref.watch(callTimerProvider);
    final session = ref.watch(callSessionProvider);

    ref.listen<CallSessionState>(callSessionProvider, (_, next) {
      _onCallStatusChanged(next);
    });

    if (session.isLoading && session.session == null) {
      return const AppScaffold(
        backgroundColor: AppColors.transparent,
        child: Center(child: CupertinoActivityIndicator()),
      );
    }
    if (session.failure case final failure? when session.session == null) {
      return AppScaffold(
        backgroundColor: AppColors.transparent,
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

    final participants = ref.watch(callParticipantsProvider).participants;
    final remoteParticipants = participants
        .where((participant) => !participant.isInitiator)
        .toList(growable: false);
    final remoteName = remoteParticipants.isNotEmpty
        ? remoteParticipants
              .map((participant) => participant.displayName)
              .join(', ')
        : UITextConstants.user;
    final remoteAvatarUrl = remoteParticipants.length == 1
        ? remoteParticipants.single.avatarUrl
        : null;
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final onGradientFg = AppColors.callStageForeground;

    return AppScaffold(
      backgroundColor: AppColors.transparent,
      body: Container(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [
              AppColorsFunctional.getColor(
                isDark,
                ColorType.callStageGradientStart,
              ),
              AppColorsFunctional.getColor(
                isDark,
                ColorType.callStageGradientEnd,
              ),
            ],
          ),
        ),
        child: SafeArea(
          child: LayoutBuilder(
            builder: (context, constraints) => SingleChildScrollView(
              child: ConstrainedBox(
                constraints: BoxConstraints(minHeight: constraints.maxHeight),
                child: Column(
                  children: [
                    SizedBox(height: AppSpacing.xl * 2),
                    Text(
                      UITextConstants.callOutgoingCalling,
                      style: TextStyle(
                        color: CallStageChrome.secondaryOnGradient(isDark),
                        fontSize: AppTypography.md,
                        fontWeight: AppTypography.normal,
                      ),
                    ),
                    SizedBox(height: AppSpacing.sm),
                    Text(
                      remoteName,
                      style: TextStyle(
                        color: onGradientFg,
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
                        color: CallStageChrome.timerOnGradient(isDark),
                        fontSize: AppTypography.sm,
                        fontWeight: AppTypography.normal,
                        fontFeatures: const [FontFeature.tabularFigures()],
                      ),
                    ),
                    SizedBox(height: AppSpacing.md),
                    CallStageBanner(
                      onRetry: () => ref
                          .read(callSessionProvider.notifier)
                          .retryCurrentCall(),
                    ),
                    SizedBox(height: AppSpacing.xl * 2),
                    CallerAvatarPulse(
                      displayName: remoteName,
                      avatarUrl: remoteAvatarUrl,
                    ),
                    SizedBox(height: AppSpacing.xl * 2),
                    _buildCancelButton(),
                    SizedBox(height: AppSpacing.xl * 2),
                  ],
                ),
              ),
            ),
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
              color: AppColors.callStageForeground,
              size: AppSpacing.xl,
            ),
          ),
          SizedBox(height: AppSpacing.sm),
          Text(
            UITextConstants.cancel,
            style: TextStyle(
              color: AppColors.callStageForeground,
              fontSize: AppTypography.sm,
              fontWeight: AppTypography.normal,
            ),
          ),
        ],
      ),
    );
  }
}
