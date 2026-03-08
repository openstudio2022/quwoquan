import 'package:flutter/cupertino.dart';

/// Renders a voice message waveform with progress fill animation.
class VoiceWaveformPainter extends StatelessWidget {
  const VoiceWaveformPainter({
    super.key,
    required this.waveform,
    required this.progress,
    required this.baseColor,
    required this.activeColor,
    this.isAnimating = false,
    this.barCount = 30,
  });

  final List<double> waveform;
  final double progress;
  final Color baseColor;
  final Color activeColor;
  final bool isAnimating;
  final int barCount;

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      painter: _WaveformPainter(
        waveform: _resample(waveform, barCount),
        progress: progress,
        baseColor: baseColor,
        activeColor: activeColor,
      ),
      size: Size.infinite,
    );
  }

  /// Resamples the waveform data to a fixed number of bars.
  static List<double> _resample(List<double> input, int targetCount) {
    if (input.isEmpty) {
      return List.filled(targetCount, 0.15);
    }
    if (input.length == targetCount) return input;

    final result = <double>[];
    final ratio = input.length / targetCount;
    for (var i = 0; i < targetCount; i++) {
      final start = (i * ratio).floor();
      final end = ((i + 1) * ratio).ceil().clamp(0, input.length);
      if (start >= end) {
        result.add(0.15);
        continue;
      }
      var sum = 0.0;
      for (var j = start; j < end; j++) {
        sum += input[j];
      }
      result.add((sum / (end - start)).clamp(0.05, 1.0));
    }
    return result;
  }
}

class _WaveformPainter extends CustomPainter {
  _WaveformPainter({
    required this.waveform,
    required this.progress,
    required this.baseColor,
    required this.activeColor,
  });

  final List<double> waveform;
  final double progress;
  final Color baseColor;
  final Color activeColor;

  @override
  void paint(Canvas canvas, Size size) {
    if (waveform.isEmpty) return;

    final barWidth = size.width / (waveform.length * 2 - 1);
    final maxHeight = size.height;
    final progressX = size.width * progress;

    final basePaint = Paint()
      ..color = baseColor
      ..strokeCap = StrokeCap.round;

    final activePaint = Paint()
      ..color = activeColor
      ..strokeCap = StrokeCap.round;

    for (var i = 0; i < waveform.length; i++) {
      final x = i * barWidth * 2;
      final barHeight = (waveform[i] * maxHeight).clamp(2.0, maxHeight);
      final top = (maxHeight - barHeight) / 2;

      final rect = RRect.fromRectAndRadius(
        Rect.fromLTWH(x, top, barWidth, barHeight),
        Radius.circular(barWidth / 2),
      );

      canvas.drawRRect(rect, x <= progressX ? activePaint : basePaint);
    }
  }

  @override
  bool shouldRepaint(_WaveformPainter oldDelegate) {
    return oldDelegate.progress != progress ||
        oldDelegate.waveform != waveform ||
        oldDelegate.baseColor != baseColor ||
        oldDelegate.activeColor != activeColor;
  }
}
