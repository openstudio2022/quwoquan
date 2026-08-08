part of 'quwoquan_app_shell.dart';

void handleQuwoquanAppLifecycleState({
  required AppLifecycleState state,
  required VoidCallback refreshAppearance,
  required VoidCallback onRealtimeForeground,
  required VoidCallback onRealtimeBackground,
}) {
  switch (state) {
    case AppLifecycleState.resumed:
      refreshAppearance();
      onRealtimeForeground();
      break;
    case AppLifecycleState.paused:
    case AppLifecycleState.detached:
    case AppLifecycleState.hidden:
      onRealtimeBackground();
      break;
    case AppLifecycleState.inactive:
      break;
  }
}

void logQuwoquanAppException({
  required String source,
  required String exceptionText,
  required String stackText,
}) {
  unawaited(
    AppExceptionTelemetryService.instance.recordGlobalException(
      source: source,
      exceptionText: exceptionText,
      stackText: stackText,
    ),
  );
}

Widget wrapWithQuwoquanAppAppearance({
  required BuildContext context,
  required AppearanceSnapshot snapshot,
  required Widget child,
}) {
  return AnnotatedRegion<SystemUiOverlayStyle>(
    value: AppTheme.systemUiOverlayStyleFor(snapshot.effectiveBrightness),
    child: MediaQuery(
      data: MediaQuery.of(context).copyWith(
        textScaler: TextScaler.linear(snapshot.textScaleFactor),
        boldText: false,
        highContrast: false,
      ),
      child: DefaultTextStyle.merge(
        style: const TextStyle(
          decoration: TextDecoration.none,
          decorationThickness: 0,
        ),
        child: _QuwoquanVisualDebugGuard(child: child),
      ),
    ),
  );
}

class _QuwoquanVisualDebugGuard extends StatelessWidget {
  const _QuwoquanVisualDebugGuard({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    assert(() {
      debugPaintSizeEnabled = false;
      debugPaintBaselinesEnabled = false;
      debugPaintPointersEnabled = false;
      debugPaintLayerBordersEnabled = false;
      debugRepaintRainbowEnabled = false;
      return true;
    }());
    return Material(type: MaterialType.transparency, child: child);
  }
}
