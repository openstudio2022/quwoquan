import 'package:flutter/widgets.dart';

enum TabSwipeDirection { previous, next }

extension TabSwipeDirectionX on TabSwipeDirection {
  int get delta => this == TabSwipeDirection.next ? 1 : -1;
}

class TabSwipeSwitchRegion extends StatelessWidget {
  const TabSwipeSwitchRegion({
    super.key,
    required this.child,
    required this.onSwipe,
    this.enabled = true,
    this.minFlingVelocity = 280,
    this.behavior = HitTestBehavior.translucent,
  });

  final Widget child;
  final ValueChanged<TabSwipeDirection> onSwipe;
  final bool enabled;
  final double minFlingVelocity;
  final HitTestBehavior behavior;

  static TabSwipeDirection? directionFromDragEnd(
    DragEndDetails details, {
    double minFlingVelocity = 280,
  }) {
    final velocity =
        details.primaryVelocity ?? details.velocity.pixelsPerSecond.dx;
    if (velocity.abs() < minFlingVelocity) {
      return null;
    }
    return velocity < 0 ? TabSwipeDirection.next : TabSwipeDirection.previous;
  }

  @override
  Widget build(BuildContext context) {
    if (!enabled) {
      return child;
    }
    return GestureDetector(
      behavior: behavior,
      onHorizontalDragEnd: (details) {
        final direction = TabSwipeSwitchRegion.directionFromDragEnd(
          details,
          minFlingVelocity: minFlingVelocity,
        );
        if (direction == null) {
          return;
        }
        onSwipe(direction);
      },
      child: child,
    );
  }
}
