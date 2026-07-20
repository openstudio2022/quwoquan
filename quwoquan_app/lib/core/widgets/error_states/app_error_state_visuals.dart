part of 'app_error_states.dart';

class _SoftPlanetIllustration extends StatelessWidget {
  const _SoftPlanetIllustration();

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      size: const Size(_softErrorIllustrationSize, _softErrorIllustrationSize),
      painter: _SoftPlanetPainter(
        planetColor: AppColors.iosTintedFill(context),
        orbitColor: AppColors.iosAccent(context).withValues(alpha: 0.62),
        signalColor: AppColors.iosTertiaryLabel(
          context,
        ).withValues(alpha: 0.35),
      ),
    );
  }
}

class _SoftPlanetPainter extends CustomPainter {
  const _SoftPlanetPainter({
    required this.planetColor,
    required this.orbitColor,
    required this.signalColor,
  });

  final Color planetColor;
  final Color orbitColor;
  final Color signalColor;

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final planetPaint = Paint()..color = planetColor;
    canvas.drawCircle(center, size.width * 0.22, planetPaint);

    final orbitPaint = Paint()
      ..color = orbitColor
      ..style = PaintingStyle.stroke
      ..strokeWidth = AppSpacing.hairline * 4
      ..strokeCap = StrokeCap.round;
    canvas.save();
    canvas.translate(center.dx, center.dy);
    canvas.rotate(-math.pi / 7);
    canvas.drawArc(
      Rect.fromCenter(
        center: Offset.zero,
        width: size.width * 0.72,
        height: size.height * 0.32,
      ),
      math.pi * 0.08,
      math.pi * 1.55,
      false,
      orbitPaint,
    );
    canvas.restore();

    final signalPaint = Paint()
      ..color = signalColor
      ..style = PaintingStyle.stroke
      ..strokeWidth = AppSpacing.hairline * 3
      ..strokeCap = StrokeCap.round;
    final signalOrigin = Offset(size.width * 0.64, size.height * 0.24);
    for (var i = 0; i < 2; i++) {
      final radius = size.width * (0.11 + i * 0.09);
      canvas.drawArc(
        Rect.fromCircle(center: signalOrigin, radius: radius),
        -math.pi / 2.4,
        math.pi / 2.5,
        false,
        signalPaint,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _SoftPlanetPainter oldDelegate) {
    return oldDelegate.planetColor != planetColor ||
        oldDelegate.orbitColor != orbitColor ||
        oldDelegate.signalColor != signalColor;
  }
}

Color _toneAccentColor(BuildContext context, UiErrorTone tone) {
  return switch (tone) {
    UiErrorTone.info => AppColors.iosAccent(context),
    UiErrorTone.caution => CupertinoDynamicColor.resolve(
      CupertinoColors.systemOrange,
      context,
    ),
    UiErrorTone.critical => AppColors.iosDestructive(context),
    UiErrorTone.neutral => AppColors.iosSecondaryLabel(context),
  };
}

Widget _wrapWithErrorAppearance(
  BuildContext context,
  UiErrorSemantic semantic,
  Widget child,
) {
  final brightness = semantic.appearanceMode.brightness;
  if (brightness == null) {
    return child;
  }
  return CupertinoTheme(
    data: CupertinoTheme.of(context).copyWith(brightness: brightness),
    child: child,
  );
}
