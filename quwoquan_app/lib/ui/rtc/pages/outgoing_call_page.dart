import 'dart:async';
import 'package:quwoquan_app/core/constants/settings_semantic_constants.dart';
import 'dart:ui';

import 'package:flutter/foundation.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';
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
  Timer? _debugAutoConnectTimer;
  bool _debugAutoConnect = true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      ref.read(callTimerProvider.notifier).start();
      _scheduleDebugAutoConnect();
    });
  }

  @override
  void dispose() {
    _debugAutoConnectTimer?.cancel();
    super.dispose();
  }

  bool get _showDebugControls =>
      kDebugMode &&
      ref.read(appDataSourceModeProvider) == AppDataSourceMode.mock;

  void _scheduleDebugAutoConnect() {
    _debugAutoConnectTimer?.cancel();
    if (!_showDebugControls || !_debugAutoConnect) return;
    _debugAutoConnectTimer = Timer(const Duration(seconds: 5), () {
      if (!mounted) return;
      ref.read(callSessionProvider.notifier).debugSimulateRemoteAnswer();
    });
  }

  void _toggleDebugAutoConnect(bool value) {
    setState(() => _debugAutoConnect = value);
    _scheduleDebugAutoConnect();
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
        : UITextConstants.user;

    return Scaffold(
      backgroundColor: Colors.transparent,
      body: Container(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [
              AppColors.welcomeGradientStart,
              AppColors.welcomeGradientEnd,
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
                    SizedBox(height: AppSpacing.xl * 2),
                    CallerAvatarPulse(
                      displayName: remoteName,
                    ),
                    SizedBox(height: AppSpacing.xl * 2),
                    if (_showDebugControls) _buildDebugPanel(),
                    if (_showDebugControls) SizedBox(height: AppSpacing.xl),
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
              color: AppColors.white,
              size: AppSpacing.xl,
            ),
          ),
          SizedBox(height: AppSpacing.sm),
          Text(
            UITextConstants.cancel,
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

  Widget _buildDebugPanel() {
    return Padding(
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.lg),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
          child: Container(
            width: double.infinity,
            padding: EdgeInsets.all(AppSpacing.md),
            decoration: BoxDecoration(
              color: AppColors.white.withValues(alpha: 0.14),
              borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
              border: Border.all(
                color: AppColors.white.withValues(alpha: 0.18),
              ),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        UITextConstants.callDebugAutoConnectInFiveSeconds,
                        style: TextStyle(
                          color: AppColors.white,
                          fontSize: AppTypography.md,
                          fontWeight: AppTypography.semiBold,
                        ),
                      ),
                    ),
                    CupertinoSwitch(value: _debugAutoConnect, onChanged: _toggleDebugAutoConnect, activeColor: SettingsSemanticConstants.switchActiveTrackColor),
                  ],
                ),
                Text(
                  UITextConstants.callDebugOnlyHint,
                  style: TextStyle(
                    color: AppColors.white.withValues(alpha: 0.72),
                    fontSize: AppTypography.sm,
                  ),
                ),
                SizedBox(height: AppSpacing.md),
                Row(
                  children: [
                    Expanded(
                      child: _DebugActionButton(
                        label: UITextConstants.callDebugManualAnswer,
                        onTap: () {
                          _debugAutoConnectTimer?.cancel();
                          ref
                              .read(callSessionProvider.notifier)
                              .debugSimulateRemoteAnswer();
                        },
                      ),
                    ),
                    SizedBox(width: AppSpacing.sm),
                    Expanded(
                      child: _DebugActionButton(
                        label: UITextConstants.callDecline,
                        onTap: () {
                          _debugAutoConnectTimer?.cancel();
                          ref
                              .read(callSessionProvider.notifier)
                              .debugSimulateRejected();
                        },
                      ),
                    ),
                    SizedBox(width: AppSpacing.sm),
                    Expanded(
                      child: _DebugActionButton(
                        label: UITextConstants.callDebugTimeout,
                        onTap: () {
                          _debugAutoConnectTimer?.cancel();
                          ref
                              .read(callSessionProvider.notifier)
                              .debugSimulateRejected(timeout: true);
                        },
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _DebugActionButton extends StatelessWidget {
  const _DebugActionButton({
    required this.label,
    required this.onTap,
  });

  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: AppSpacing.minInteractiveSize,
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        color: AppColors.white.withValues(alpha: 0.14),
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
        onPressed: onTap,
        child: Text(
          label,
          style: TextStyle(
            color: AppColors.white,
            fontSize: AppTypography.sm,
            fontWeight: AppTypography.medium,
          ),
        ),
      ),
    );
  }
}
