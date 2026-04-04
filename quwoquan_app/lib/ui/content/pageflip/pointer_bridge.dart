import 'dart:async';
import 'dart:ui';

import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

@immutable
class StPageFlipSwipeResult {
  const StPageFlipSwipeResult({
    required this.corner,
    required this.direction,
  });

  final StPageFlipCorner corner;
  final StPageFlipDirection direction;
}

class StPageFlipPointerBridge {
  StPageFlipPointerBridge({
    this.swipeTimeout = const Duration(milliseconds: 250),
    this.swipeDistance = 30,
    this.moveStartDistance = 10,
  });

  final Duration swipeTimeout;
  final double swipeDistance;
  final double moveStartDistance;

  Offset? _touchPoint;
  DateTime? _touchStartedAt;
  Timer? _deferredTouchTimer;
  bool _touchStarted = false;

  void dispose() {
    cancel();
  }

  void handleTouchStart(Offset position, VoidCallback onDeferredStart) {
    cancel();
    _touchPoint = position;
    _touchStartedAt = DateTime.now();
    _deferredTouchTimer = Timer(swipeTimeout, () {
      _touchStarted = true;
      onDeferredStart();
    });
  }

  bool handleTouchMove(Offset position, VoidCallback onImmediateStart) {
    final touchPoint = _touchPoint;
    if (touchPoint == null) {
      return false;
    }
    if (!_touchStarted &&
        ((touchPoint.dx - position.dx).abs() > moveStartDistance ||
            (touchPoint.dy - position.dy).abs() > moveStartDistance)) {
      _deferredTouchTimer?.cancel();
      _touchStarted = true;
      onImmediateStart();
    }
    return _touchStarted;
  }

  StPageFlipSwipeResult? handleTouchEnd(
    Offset position, {
    required double pageHeight,
  }) {
    final touchPoint = _touchPoint;
    final startedAt = _touchStartedAt;
    if (touchPoint == null || startedAt == null) {
      cancel();
      return null;
    }

    final dx = position.dx - touchPoint.dx;
    final distY = (position.dy - touchPoint.dy).abs();
    final result =
        dx.abs() > swipeDistance &&
            distY < swipeDistance * 2 &&
            DateTime.now().difference(startedAt) < swipeTimeout
        ? StPageFlipSwipeResult(
            corner: touchPoint.dy < pageHeight / 2
                ? StPageFlipCorner.top
                : StPageFlipCorner.bottom,
            direction: dx > 0
                ? StPageFlipDirection.back
                : StPageFlipDirection.forward,
          )
        : null;
    cancel();
    return result;
  }

  void cancel() {
    _deferredTouchTimer?.cancel();
    _deferredTouchTimer = null;
    _touchPoint = null;
    _touchStartedAt = null;
    _touchStarted = false;
  }
}
