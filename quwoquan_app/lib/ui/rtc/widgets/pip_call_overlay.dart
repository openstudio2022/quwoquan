import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/services/active_call_service.dart';
import 'package:quwoquan_app/ui/rtc/models/call_participant.dart';

/// In-app floating PiP window for active calls.
/// 120×160pt draggable window that snaps to corners.
class PipCallOverlay extends ConsumerStatefulWidget {
  const PipCallOverlay({
    super.key,
    required this.onReturnToCall,
    required this.onHangup,
    this.activeSpeaker,
  });

  final VoidCallback onReturnToCall;
  final VoidCallback onHangup;
  final CallParticipant? activeSpeaker;

  @override
  ConsumerState<PipCallOverlay> createState() => _PipCallOverlayState();
}

class _PipCallOverlayState extends ConsumerState<PipCallOverlay> {
  static const _width = 120.0;
  static const _height = 160.0;
  static const _edgePadding = 12.0;

  Offset _position = const Offset(_edgePadding, 100.0);

  void _onDragEnd(DragEndDetails details, BoxConstraints constraints) {
    final maxX = constraints.maxWidth - _width - _edgePadding;
    final maxY = constraints.maxHeight - _height - _edgePadding;
    final centerX = _position.dx + _width / 2;
    final snapX = centerX < constraints.maxWidth / 2
        ? _edgePadding
        : maxX;
    final clampedY = _position.dy.clamp(_edgePadding, maxY);

    setState(() {
      _position = Offset(snapX, clampedY);
    });
  }

  @override
  Widget build(BuildContext context) {
    final callState = ref.watch(activeCallProvider);
    if (!callState.isInCall || !callState.isPipMode) {
      return const SizedBox.shrink();
    }

    return LayoutBuilder(
      builder: (context, constraints) {
        return Stack(
          children: [
            AnimatedPositioned(
              duration: const Duration(milliseconds: 250),
              curve: Curves.easeOut,
              left: _position.dx,
              top: _position.dy,
              child: GestureDetector(
                onTap: widget.onReturnToCall,
                onLongPress: () => _confirmHangup(context),
                onPanUpdate: (d) {
                  setState(() {
                    _position = Offset(
                      (_position.dx + d.delta.dx).clamp(
                        _edgePadding,
                        constraints.maxWidth - _width - _edgePadding,
                      ),
                      (_position.dy + d.delta.dy).clamp(
                        _edgePadding,
                        constraints.maxHeight - _height - _edgePadding,
                      ),
                    );
                  });
                },
                onPanEnd: (d) => _onDragEnd(d, constraints),
                child: Container(
                  width: _width,
                  height: _height,
                  decoration: BoxDecoration(
                    color: AppColors.overlayDark,
                    borderRadius:
                        BorderRadius.circular(AppSpacing.borderRadius),
                    boxShadow: [
                      BoxShadow(
                        color: AppColors.overlayLight,
                        blurRadius: AppSpacing.sm,
                        offset: Offset(0, AppSpacing.xs),
                      ),
                    ],
                  ),
                  clipBehavior: Clip.antiAlias,
                  child: Stack(
                    fit: StackFit.expand,
                    children: [
                      _buildContent(callState),
                      Positioned(
                        bottom: AppSpacing.xs,
                        left: 0,
                        right: 0,
                        child: Center(
                          child: Text(
                            _formatDuration(callState.elapsed),
                            style: TextStyle(
                              color: AppColors.white,
                              fontSize: AppTypography.xs,
                              fontWeight: AppTypography.medium,
                              fontFeatures: const [
                                FontFeature.tabularFigures(),
                              ],
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ],
        );
      },
    );
  }

  Widget _buildContent(ActiveCallState callState) {
    final speaker = widget.activeSpeaker;
    if (speaker != null && speaker.isCameraOn) {
      return Container(
        color: AppColors.overlayMedium,
        child: Center(
          child: Icon(
            CupertinoIcons.video_camera,
            color: AppColors.white.withValues(alpha: 0.4),
            size: AppSpacing.xl,
          ),
        ),
      );
    }

    return Container(
      color: AppColors.overlayDark,
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            CircleAvatar(
              radius: AppSpacing.lg,
              backgroundColor: AppColors.primaryColor.withValues(alpha: 0.3),
              backgroundImage: speaker?.avatarUrl != null
                  ? NetworkImage(speaker!.avatarUrl!)
                  : null,
              child: speaker?.avatarUrl == null
                  ? Icon(
                      callState.callType == 'video'
                          ? CupertinoIcons.video_camera
                          : CupertinoIcons.phone,
                      color: AppColors.white,
                      size: AppSpacing.iconMedium,
                    )
                  : null,
            ),
            SizedBox(height: AppSpacing.xs),
            Text(
              speaker?.displayName ?? '通话中',
              style: TextStyle(
                color: AppColors.white,
                fontSize: AppTypography.xs,
                fontWeight: AppTypography.medium,
              ),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ],
        ),
      ),
    );
  }

  String _formatDuration(Duration d) {
    final m = d.inMinutes.remainder(60).toString().padLeft(2, '0');
    final s = d.inSeconds.remainder(60).toString().padLeft(2, '0');
    return '$m:$s';
  }

  void _confirmHangup(BuildContext context) {
    showCupertinoDialog<void>(
      context: context,
      builder: (ctx) => CupertinoAlertDialog(
        title: const Text('结束通话'),
        content: const Text('确定要挂断当前通话吗？'),
        actions: [
          CupertinoDialogAction(
            child: const Text('取消'),
            onPressed: () => Navigator.pop(ctx),
          ),
          CupertinoDialogAction(
            isDestructiveAction: true,
            child: const Text('挂断'),
            onPressed: () {
              Navigator.pop(ctx);
              widget.onHangup();
            },
          ),
        ],
      ),
    );
  }
}
