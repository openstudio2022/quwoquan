import 'dart:math' as math;
import 'dart:ui' show Offset;

import 'package:flutter/foundation.dart';

enum ImmersiveGestureIntentPhase {
  idle,
  tracking,
  previewing,
  locked,
  rejected,
}

enum ImmersiveGestureAxis { horizontal, vertical }

enum ImmersiveGestureIntent {
  undecided,
  pageFlipForward,
  pageFlipBack,
  verticalWorkSwitch,
  boundaryRubberBand,
  edgeDismiss,
  rejected,
}

@immutable
class ImmersiveGestureCapabilities {
  const ImmersiveGestureCapabilities({
    required this.pageCount,
    required this.currentPageIndex,
    required this.canFlipForward,
    required this.canFlipBack,
    this.allowVerticalSwitch = true,
    this.allowBoundaryRubberBand = true,
    this.startedInPageFlipHotzone = true,
  });

  final int pageCount;
  final int currentPageIndex;
  final bool canFlipForward;
  final bool canFlipBack;
  final bool allowVerticalSwitch;
  final bool allowBoundaryRubberBand;
  final bool startedInPageFlipHotzone;

  bool canFlipForDelta(double dx) {
    if (pageCount <= 1) {
      return false;
    }
    if (dx < 0) {
      return canFlipForward;
    }
    if (dx > 0) {
      return canFlipBack;
    }
    return false;
  }
}

class ImmersiveGestureIntentController extends ChangeNotifier {
  ImmersiveGestureIntentController({DateTime Function()? now})
    : _now = now ?? DateTime.now;

  static const double jitterDistance = 6;
  static const double previewDistance = 6;
  static const double decisiveDistance = 12;
  static const double forcedDecisionDistance = 18;
  static const double axisDominanceRatio = 1.12;
  static const double pageFlipHotzoneRatio = 1.05;
  static const double strongHorizontalBoundaryRatio = 1.6;
  static const Duration retryIntentWindow = Duration(milliseconds: 1200);

  final DateTime Function() _now;

  Offset? _startPosition;
  Offset _totalDelta = Offset.zero;
  ImmersiveGestureCapabilities? _capabilities;
  ImmersiveGestureIntentPhase _phase = ImmersiveGestureIntentPhase.idle;
  ImmersiveGestureIntent _lockedIntent = ImmersiveGestureIntent.undecided;
  ImmersiveGestureIntent _previewIntent = ImmersiveGestureIntent.undecided;
  ImmersiveGestureAxis? _dominantAxis;
  ImmersiveGestureAxis? _lastUncommittedAxis;
  int _lastUncommittedDirectionSign = 0;
  DateTime? _lastUncommittedAt;

  ImmersiveGestureIntentPhase get phase => _phase;
  ImmersiveGestureIntent get lockedIntent => _lockedIntent;
  ImmersiveGestureIntent get previewIntent => _previewIntent;
  ImmersiveGestureAxis? get dominantAxis => _dominantAxis;
  Offset get totalDelta => _totalDelta;

  bool get isTracking => _phase != ImmersiveGestureIntentPhase.idle;

  bool get isPageFlipLocked =>
      _lockedIntent == ImmersiveGestureIntent.pageFlipForward ||
      _lockedIntent == ImmersiveGestureIntent.pageFlipBack;

  bool get isVerticalLocked =>
      _lockedIntent == ImmersiveGestureIntent.verticalWorkSwitch;

  bool get shouldHoldVerticalScroll {
    if (_phase != ImmersiveGestureIntentPhase.locked) {
      return false;
    }
    final intent = _lockedIntent;
    return intent == ImmersiveGestureIntent.pageFlipForward ||
        intent == ImmersiveGestureIntent.pageFlipBack ||
        intent == ImmersiveGestureIntent.boundaryRubberBand ||
        intent == ImmersiveGestureIntent.edgeDismiss;
  }

  bool get shouldIgnorePageFlipInput =>
      _lockedIntent == ImmersiveGestureIntent.verticalWorkSwitch ||
      _lockedIntent == ImmersiveGestureIntent.rejected;

  void begin({
    required Offset position,
    required ImmersiveGestureCapabilities capabilities,
  }) {
    _startPosition = position;
    _totalDelta = Offset.zero;
    _capabilities = capabilities;
    _phase = ImmersiveGestureIntentPhase.tracking;
    _lockedIntent = ImmersiveGestureIntent.undecided;
    _previewIntent = ImmersiveGestureIntent.undecided;
    _dominantAxis = null;
    notifyListeners();
  }

  ImmersiveGestureIntent update({
    required Offset position,
    ImmersiveGestureCapabilities? capabilities,
  }) {
    final start = _startPosition;
    if (start == null) {
      final nextCapabilities = capabilities ?? _capabilities;
      if (nextCapabilities == null) {
        return ImmersiveGestureIntent.undecided;
      }
      begin(position: position, capabilities: nextCapabilities);
      return ImmersiveGestureIntent.undecided;
    }
    if (capabilities != null) {
      _capabilities = capabilities;
    }
    if (_phase == ImmersiveGestureIntentPhase.locked) {
      return _lockedIntent;
    }
    final caps = _capabilities;
    if (caps == null) {
      return ImmersiveGestureIntent.undecided;
    }
    _totalDelta = position - start;
    final absX = _totalDelta.dx.abs();
    final absY = _totalDelta.dy.abs();
    final majorDistance = math.max(absX, absY);
    _dominantAxis = absX >= absY
        ? ImmersiveGestureAxis.horizontal
        : ImmersiveGestureAxis.vertical;
    if (majorDistance < jitterDistance) {
      _setPreview(ImmersiveGestureIntent.undecided);
      return ImmersiveGestureIntent.undecided;
    }

    final secondTry = _isSecondTry(_totalDelta);
    final preview = _intentForDelta(_totalDelta, caps, forceDominant: false);
    if (majorDistance >= previewDistance) {
      _setPreview(preview);
    }

    final horizontalRatio = _ratio(absX, absY);
    final verticalRatio = _ratio(absY, absX);
    final horizontalThreshold =
        caps.startedInPageFlipHotzone && caps.canFlipForDelta(_totalDelta.dx)
        ? pageFlipHotzoneRatio
        : axisDominanceRatio;
    final decisionDistance = secondTry ? jitterDistance : decisiveDistance;
    final forcedDistance = secondTry ? previewDistance : forcedDecisionDistance;
    final ratioThreshold = secondTry ? 1.0 : axisDominanceRatio;

    final locksHorizontal =
        absX >= decisionDistance && horizontalRatio >= horizontalThreshold;
    final locksVertical =
        absY >= decisionDistance && verticalRatio >= ratioThreshold;
    if (locksHorizontal || locksVertical || majorDistance >= forcedDistance) {
      return _lockIntent(
        _intentForDelta(
          _totalDelta,
          caps,
          forceDominant: majorDistance >= forcedDistance,
        ),
      );
    }

    _setPhase(ImmersiveGestureIntentPhase.previewing);
    return ImmersiveGestureIntent.undecided;
  }

  void finish({bool committed = false}) {
    final phase = _phase;
    final delta = _totalDelta;
    _resetTransient();
    if (!committed &&
        phase != ImmersiveGestureIntentPhase.idle &&
        delta.distance >= previewDistance) {
      _rememberUncommitted(delta);
    }
    notifyListeners();
  }

  void cancel() {
    finish(committed: false);
  }

  void _rememberUncommitted(Offset delta) {
    final axis = delta.dx.abs() >= delta.dy.abs()
        ? ImmersiveGestureAxis.horizontal
        : ImmersiveGestureAxis.vertical;
    _lastUncommittedAxis = axis;
    _lastUncommittedDirectionSign = axis == ImmersiveGestureAxis.horizontal
        ? delta.dx.sign.toInt()
        : delta.dy.sign.toInt();
    _lastUncommittedAt = _now();
  }

  bool _isSecondTry(Offset delta) {
    final lastAt = _lastUncommittedAt;
    final axis = _lastUncommittedAxis;
    if (lastAt == null || axis == null) {
      return false;
    }
    if (_now().difference(lastAt) > retryIntentWindow) {
      return false;
    }
    final currentAxis = delta.dx.abs() >= delta.dy.abs()
        ? ImmersiveGestureAxis.horizontal
        : ImmersiveGestureAxis.vertical;
    if (currentAxis != axis) {
      return false;
    }
    final directionSign = currentAxis == ImmersiveGestureAxis.horizontal
        ? delta.dx.sign.toInt()
        : delta.dy.sign.toInt();
    return directionSign != 0 && directionSign == _lastUncommittedDirectionSign;
  }

  ImmersiveGestureIntent _intentForDelta(
    Offset delta,
    ImmersiveGestureCapabilities caps, {
    required bool forceDominant,
  }) {
    final absX = delta.dx.abs();
    final absY = delta.dy.abs();
    final horizontalDominant = absX >= absY;
    if (horizontalDominant) {
      return _horizontalIntent(delta.dx, absX, absY, caps);
    }
    if (caps.allowVerticalSwitch) {
      return ImmersiveGestureIntent.verticalWorkSwitch;
    }
    if (forceDominant && caps.canFlipForDelta(delta.dx)) {
      return delta.dx < 0
          ? ImmersiveGestureIntent.pageFlipForward
          : ImmersiveGestureIntent.pageFlipBack;
    }
    return ImmersiveGestureIntent.rejected;
  }

  ImmersiveGestureIntent _horizontalIntent(
    double dx,
    double absX,
    double absY,
    ImmersiveGestureCapabilities caps,
  ) {
    if (caps.canFlipForDelta(dx)) {
      return dx < 0
          ? ImmersiveGestureIntent.pageFlipForward
          : ImmersiveGestureIntent.pageFlipBack;
    }
    final strongBoundary =
        _ratio(absX, absY) >= strongHorizontalBoundaryRatio ||
        !caps.allowVerticalSwitch;
    if (caps.allowBoundaryRubberBand && strongBoundary) {
      return ImmersiveGestureIntent.boundaryRubberBand;
    }
    if (caps.allowVerticalSwitch) {
      return ImmersiveGestureIntent.verticalWorkSwitch;
    }
    return ImmersiveGestureIntent.rejected;
  }

  ImmersiveGestureIntent _lockIntent(ImmersiveGestureIntent intent) {
    _lockedIntent = intent;
    _previewIntent = intent;
    _phase = intent == ImmersiveGestureIntent.rejected
        ? ImmersiveGestureIntentPhase.rejected
        : ImmersiveGestureIntentPhase.locked;
    notifyListeners();
    return intent;
  }

  void _setPreview(ImmersiveGestureIntent intent) {
    if (_previewIntent == intent) {
      return;
    }
    _previewIntent = intent;
    notifyListeners();
  }

  void _setPhase(ImmersiveGestureIntentPhase phase) {
    if (_phase == phase) {
      return;
    }
    _phase = phase;
    notifyListeners();
  }

  void _resetTransient() {
    _startPosition = null;
    _totalDelta = Offset.zero;
    _capabilities = null;
    _phase = ImmersiveGestureIntentPhase.idle;
    _lockedIntent = ImmersiveGestureIntent.undecided;
    _previewIntent = ImmersiveGestureIntent.undecided;
    _dominantAxis = null;
  }

  double _ratio(double numerator, double denominator) {
    if (denominator <= 0) {
      return double.infinity;
    }
    return numerator / denominator;
  }
}
