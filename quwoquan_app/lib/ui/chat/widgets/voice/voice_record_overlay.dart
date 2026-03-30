import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/ui/chat/widgets/voice/voice_recorder.dart';

/// Interactive overlay for voice recording.
/// Supports: long-press start, release to send, swipe up to cancel, timer display.
class VoiceRecordOverlay extends StatefulWidget {
  const VoiceRecordOverlay({
    super.key,
    required this.recorder,
    required this.onComplete,
    required this.onCancel,
  });

  final VoiceRecorder recorder;
  final ValueChanged<VoiceRecordResult> onComplete;
  final VoidCallback onCancel;

  @override
  State<VoiceRecordOverlay> createState() => _VoiceRecordOverlayState();
}

class _VoiceRecordOverlayState extends State<VoiceRecordOverlay> {
  bool _isCancelling = false;
  Timer? _timer;
  int _elapsedSeconds = 0;
  List<double> _amplitudes = [];
  StreamSubscription<List<double>>? _ampSub;

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) {
        setState(() {
          _elapsedSeconds = widget.recorder.elapsedMs ~/ 1000;
        });
      }
    });
    _ampSub = widget.recorder.onAmplitude.listen((amps) {
      if (mounted) setState(() => _amplitudes = amps);
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    _ampSub?.cancel();
    super.dispose();
  }

  void _onVerticalDragUpdate(DragUpdateDetails details) {
    setState(() {
      _isCancelling = details.localPosition.dy < -80;
    });
  }

  Future<void> _onRelease() async {
    if (_isCancelling) {
      await widget.recorder.cancel();
      widget.onCancel();
      return;
    }

    final result = await widget.recorder.stop();
    if (result != null) {
      widget.onComplete(result);
    } else {
      widget.onCancel();
    }
  }

  String _formatTime(int seconds) {
    final m = seconds ~/ 60;
    final s = seconds % 60;
    return '${m.toString().padLeft(2, '0')}:${s.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onVerticalDragUpdate: _onVerticalDragUpdate,
      onVerticalDragEnd: (_) => _onRelease(),
      onPanEnd: (_) => _onRelease(),
      child: Container(
        width: double.infinity,
        padding: EdgeInsets.symmetric(
          vertical: AppSpacing.lg,
          horizontal: AppSpacing.md,
        ),
        decoration: BoxDecoration(
          color: _isCancelling
              ? AppColors.error.withValues(alpha: 0.15)
              : AppColors.chatBackground,
          borderRadius: BorderRadius.vertical(
            top: Radius.circular(AppSpacing.largeBorderRadius),
          ),
        ),
        child: SafeArea(
          top: false,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              _buildWaveform(),
              SizedBox(height: AppSpacing.sm),
              Text(
                _formatTime(_elapsedSeconds),
                style: TextStyle(
                  fontSize: AppTypography.lg,
                  fontWeight: AppTypography.semiBold,
                  color: _isCancelling ? AppColors.error : AppColors.dark.foregroundPrimary,
                ),
              ),
              SizedBox(height: AppSpacing.xs),
              Text(
                _isCancelling ? '松开取消' : '上滑取消，松开发送',
                style: TextStyle(
                  fontSize: AppTypography.sm,
                  color: _isCancelling
                      ? AppColors.error
                      : AppColors.dark.foregroundSecondary,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildWaveform() {
    final displayAmps =
        _amplitudes.length > 40 ? _amplitudes.sublist(_amplitudes.length - 40) : _amplitudes;

    return SizedBox(
      height: AppSpacing.xl * 2,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: List.generate(
          displayAmps.isEmpty ? 20 : displayAmps.length,
          (i) {
            final amp = displayAmps.isEmpty ? 0.1 : displayAmps[i];
            return Container(
              width: AppSpacing.three,
              height: (amp * AppSpacing.xl * 2)
                  .clamp(AppSpacing.two, AppSpacing.xl * 2),
              margin: const EdgeInsets.symmetric(horizontal: AppSpacing.one),
              decoration: BoxDecoration(
                color: _isCancelling
                    ? AppColors.error
                    : AppColors.primaryColor,
                borderRadius: BorderRadius.circular(AppSpacing.smallBorderRadius),
              ),
            );
          },
        ),
      ),
    );
  }
}
