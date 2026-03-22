import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/widgets/app_action_sheet.dart';
import 'package:quwoquan_app/ui/rtc/models/call_state.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_session_provider.dart';
import 'package:quwoquan_app/ui/rtc/providers/media_device_provider.dart';

class CallControlsBar extends ConsumerStatefulWidget {
  const CallControlsBar({
    super.key,
    required this.callType,
    this.onHangup,
    this.onInvite,
    this.autoHide = true,
  });

  final CallType callType;
  final VoidCallback? onHangup;
  final VoidCallback? onInvite;
  final bool autoHide;

  @override
  ConsumerState<CallControlsBar> createState() => _CallControlsBarState();
}

class _CallControlsBarState extends ConsumerState<CallControlsBar> {
  bool _visible = true;
  Timer? _hideTimer;

  @override
  void initState() {
    super.initState();
    _resetHideTimer();
  }

  @override
  void dispose() {
    _hideTimer?.cancel();
    super.dispose();
  }

  void _resetHideTimer() {
    if (!widget.autoHide) return;
    _hideTimer?.cancel();
    _hideTimer = Timer(const Duration(seconds: 3), () {
      if (mounted) setState(() => _visible = false);
    });
  }

  void _onTapArea() {
    setState(() => _visible = !_visible);
    if (_visible) _resetHideTimer();
  }

  @override
  Widget build(BuildContext context) {
    final session = ref.watch(callSessionProvider);
    final device = ref.watch(mediaDeviceProvider);

    return GestureDetector(
      onTap: _onTapArea,
      behavior: HitTestBehavior.translucent,
      child: AnimatedOpacity(
        opacity: _visible ? 1.0 : 0.0,
        duration: const Duration(milliseconds: 250),
        child: IgnorePointer(
          ignoring: !_visible,
          child: Container(
            padding: EdgeInsets.symmetric(
              horizontal: AppSpacing.lg,
              vertical: AppSpacing.md,
            ),
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.bottomCenter,
                end: Alignment.topCenter,
                colors: [
                  AppColors.overlayStrong,
                  AppColors.overlayStrong.withValues(alpha: 0.0),
                ],
              ),
            ),
            child: SafeArea(
              top: false,
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                children: [
                  _ControlButton(
                    icon: session.isMuted
                        ? CupertinoIcons.mic_off
                        : CupertinoIcons.mic,
                    label: session.isMuted ? '已静音' : '静音',
                    isActive: session.isMuted,
                    onTap: () {
                      ref.read(callSessionProvider.notifier).toggleMute();
                      _resetHideTimer();
                    },
                  ),
                  if (widget.callType.isVideo) ...[
                    _ControlButton(
                      icon: session.isCameraOn
                          ? CupertinoIcons.video_camera
                          : CupertinoIcons.video_camera_solid,
                      label: session.isCameraOn ? '关闭摄像头' : '打开摄像头',
                      isActive: !session.isCameraOn,
                      onTap: () {
                        ref.read(callSessionProvider.notifier).toggleCamera();
                        _resetHideTimer();
                      },
                    ),
                    _ControlButton(
                      icon: CupertinoIcons.switch_camera,
                      label: '翻转',
                      isActive: false,
                      onTap: () {
                        ref.read(mediaDeviceProvider.notifier).flipCamera();
                        _resetHideTimer();
                      },
                    ),
                  ] else
                    _ControlButton(
                      icon: CupertinoIcons.video_camera,
                      label: '开启视频',
                      isActive: false,
                      onTap: () {
                        ref.read(callSessionProvider.notifier).toggleCamera();
                        _resetHideTimer();
                      },
                    ),
                  _ControlButton(
                    icon: CupertinoIcons.person_add,
                    label: '邀请',
                    isActive: false,
                    onTap: () {
                      widget.onInvite?.call();
                      _resetHideTimer();
                    },
                  ),
                  GestureDetector(
                    onLongPress: () => _showAudioOutputPicker(context, device),
                    child: _ControlButton(
                      icon: device.audioOutput == AudioOutput.speaker
                          ? CupertinoIcons.speaker_2_fill
                          : CupertinoIcons.speaker_1,
                      label: device.audioOutput.label,
                      isActive: device.audioOutput == AudioOutput.speaker,
                      onTap: () {
                        ref.read(mediaDeviceProvider.notifier).toggleSpeaker();
                        _resetHideTimer();
                      },
                    ),
                  ),
                  _HangupButton(
                    onTap: () {
                      widget.onHangup?.call();
                    },
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Future<void> _showAudioOutputPicker(
    BuildContext context,
    MediaDeviceState device,
  ) async {
    final selected = await showAppActionSheet<AudioOutput>(
      context,
      title: '音频输出',
      sections: [
        AppActionSheetSection<AudioOutput>(
          items: [
            AppActionSheetItem<AudioOutput>(
              value: AudioOutput.earpiece,
              label: '听筒',
              isSelected: device.audioOutput == AudioOutput.earpiece,
            ),
            AppActionSheetItem<AudioOutput>(
              value: AudioOutput.speaker,
              label: '扬声器',
              isSelected: device.audioOutput == AudioOutput.speaker,
            ),
            if (device.isBluetoothAvailable)
              AppActionSheetItem<AudioOutput>(
                value: AudioOutput.bluetooth,
                label: '蓝牙',
                isSelected: device.audioOutput == AudioOutput.bluetooth,
              ),
          ],
        ),
      ],
    );
    if (selected == null) return;
    ref.read(mediaDeviceProvider.notifier).setAudioOutput(selected);
  }
}

class _ControlButton extends StatelessWidget {
  const _ControlButton({
    required this.icon,
    required this.label,
    required this.isActive,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final bool isActive;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: SizedBox(
        width: AppSpacing.iconButtonMinSizeMd,
        height: AppSpacing.iconButtonMinSizeMd,
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              width: AppSpacing.minInteractiveSize,
              height: AppSpacing.minInteractiveSize,
              decoration: BoxDecoration(
                color: isActive
                    ? AppColors.white.withValues(alpha: 0.9)
                    : AppColors.white.withValues(alpha: 0.15),
                shape: BoxShape.circle,
              ),
              child: Icon(
                icon,
                color: isActive ? AppColors.black : AppColors.white,
                size: AppSpacing.iconMedium,
              ),
            ),
            SizedBox(height: AppSpacing.xs),
            Text(
              label,
              style: TextStyle(
                color: AppColors.white,
                fontSize: AppTypography.xs,
                fontWeight: AppTypography.normal,
              ),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ],
        ),
      ),
    );
  }
}

class _HangupButton extends StatelessWidget {
  const _HangupButton({required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: SizedBox(
        width: AppSpacing.iconButtonMinSizeMd,
        height: AppSpacing.iconButtonMinSizeMd,
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              width: AppSpacing.minInteractiveSize,
              height: AppSpacing.minInteractiveSize,
              decoration: const BoxDecoration(
                color: AppColors.error,
                shape: BoxShape.circle,
              ),
              child: Icon(
                CupertinoIcons.phone_down_fill,
                color: AppColors.white,
                size: AppSpacing.iconMedium,
              ),
            ),
            SizedBox(height: AppSpacing.xs),
            Text(
              '挂断',
              style: TextStyle(
                color: AppColors.white,
                fontSize: AppTypography.xs,
                fontWeight: AppTypography.normal,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
