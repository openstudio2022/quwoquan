import 'package:flutter/widgets.dart';

@immutable
class ImmersivePointerGestureStart {
  const ImmersivePointerGestureStart({
    required this.pointer,
    required this.localPosition,
    required this.globalPosition,
    required this.timeStamp,
  });

  final int pointer;
  final Offset localPosition;
  final Offset globalPosition;
  final Duration timeStamp;
}

@immutable
class ImmersivePointerGestureUpdate {
  const ImmersivePointerGestureUpdate({
    required this.pointer,
    required this.startLocalPosition,
    required this.localPosition,
    required this.globalPosition,
    required this.delta,
    required this.totalDelta,
    required this.velocityDx,
    required this.timeStamp,
  });

  final int pointer;
  final Offset startLocalPosition;
  final Offset localPosition;
  final Offset globalPosition;
  final Offset delta;
  final Offset totalDelta;
  final double velocityDx;
  final Duration timeStamp;
}

@immutable
class ImmersivePointerGestureEnd {
  const ImmersivePointerGestureEnd({
    required this.pointer,
    required this.startLocalPosition,
    required this.localPosition,
    required this.globalPosition,
    required this.totalDelta,
    required this.velocityDx,
    required this.timeStamp,
  });

  final int pointer;
  final Offset startLocalPosition;
  final Offset localPosition;
  final Offset globalPosition;
  final Offset totalDelta;
  final double velocityDx;
  final Duration timeStamp;
}

@immutable
class ImmersivePointerGestureCancel {
  const ImmersivePointerGestureCancel({
    required this.pointer,
    required this.startLocalPosition,
    required this.localPosition,
    required this.globalPosition,
    required this.totalDelta,
    required this.timeStamp,
  });

  final int pointer;
  final Offset startLocalPosition;
  final Offset localPosition;
  final Offset globalPosition;
  final Offset totalDelta;
  final Duration timeStamp;
}

typedef ImmersivePointerGestureStartCallback =
    void Function(ImmersivePointerGestureStart event);
typedef ImmersivePointerGestureUpdateCallback =
    void Function(ImmersivePointerGestureUpdate event);
typedef ImmersivePointerGestureEndCallback =
    void Function(ImmersivePointerGestureEnd event);
typedef ImmersivePointerGestureCancelCallback =
    void Function(ImmersivePointerGestureCancel event);

/// Shared pointer-level gesture sampler for immersive media surfaces.
///
/// It deliberately owns only single-pointer tracking, delta and horizontal
/// velocity sampling. Pageflip intent arbitration, boundary behavior and
/// rendering remain in the image/article hosts.
class ImmersivePointerGestureLayer extends StatefulWidget {
  const ImmersivePointerGestureLayer({
    super.key,
    required this.child,
    this.behavior = HitTestBehavior.translucent,
    this.onStart,
    this.onUpdate,
    this.onEnd,
    this.onCancel,
  });

  final Widget child;
  final HitTestBehavior behavior;
  final ImmersivePointerGestureStartCallback? onStart;
  final ImmersivePointerGestureUpdateCallback? onUpdate;
  final ImmersivePointerGestureEndCallback? onEnd;
  final ImmersivePointerGestureCancelCallback? onCancel;

  @override
  State<ImmersivePointerGestureLayer> createState() =>
      _ImmersivePointerGestureLayerState();
}

class _ImmersivePointerGestureLayerState
    extends State<ImmersivePointerGestureLayer> {
  int? _activePointer;
  Offset? _startLocalPosition;
  Duration? _lastTimestamp;
  double _velocityDx = 0;

  @override
  Widget build(BuildContext context) {
    return Listener(
      behavior: widget.behavior,
      onPointerDown: _handlePointerDown,
      onPointerMove: _handlePointerMove,
      onPointerUp: _handlePointerUp,
      onPointerCancel: _handlePointerCancel,
      child: widget.child,
    );
  }

  void _handlePointerDown(PointerDownEvent event) {
    if (_activePointer != null) {
      return;
    }
    _activePointer = event.pointer;
    _startLocalPosition = event.localPosition;
    _lastTimestamp = event.timeStamp;
    _velocityDx = 0;
    widget.onStart?.call(
      ImmersivePointerGestureStart(
        pointer: event.pointer,
        localPosition: event.localPosition,
        globalPosition: event.position,
        timeStamp: event.timeStamp,
      ),
    );
  }

  void _handlePointerMove(PointerMoveEvent event) {
    if (_activePointer != event.pointer) {
      return;
    }
    final start = _startLocalPosition;
    if (start == null) {
      return;
    }
    final lastTimestamp = _lastTimestamp;
    if (lastTimestamp != null) {
      final dtSeconds =
          (event.timeStamp - lastTimestamp).inMicroseconds / 1000000;
      if (dtSeconds > 0) {
        _velocityDx = event.delta.dx / dtSeconds;
      } else if (event.delta.dx != 0) {
        _velocityDx = event.delta.dx * 60;
      }
    }
    _lastTimestamp = event.timeStamp;
    widget.onUpdate?.call(
      ImmersivePointerGestureUpdate(
        pointer: event.pointer,
        startLocalPosition: start,
        localPosition: event.localPosition,
        globalPosition: event.position,
        delta: event.delta,
        totalDelta: event.localPosition - start,
        velocityDx: _velocityDx,
        timeStamp: event.timeStamp,
      ),
    );
  }

  void _handlePointerUp(PointerUpEvent event) {
    if (_activePointer != event.pointer) {
      return;
    }
    final start = _startLocalPosition ?? event.localPosition;
    widget.onEnd?.call(
      ImmersivePointerGestureEnd(
        pointer: event.pointer,
        startLocalPosition: start,
        localPosition: event.localPosition,
        globalPosition: event.position,
        totalDelta: event.localPosition - start,
        velocityDx: _velocityDx,
        timeStamp: event.timeStamp,
      ),
    );
    _clear();
  }

  void _handlePointerCancel(PointerCancelEvent event) {
    if (_activePointer != event.pointer) {
      return;
    }
    final start = _startLocalPosition ?? event.localPosition;
    widget.onCancel?.call(
      ImmersivePointerGestureCancel(
        pointer: event.pointer,
        startLocalPosition: start,
        localPosition: event.localPosition,
        globalPosition: event.position,
        totalDelta: event.localPosition - start,
        timeStamp: event.timeStamp,
      ),
    );
    _clear();
  }

  void _clear() {
    _activePointer = null;
    _startLocalPosition = null;
    _lastTimestamp = null;
    _velocityDx = 0;
  }
}
