import 'dart:math' as math;
import 'dart:ui';

import 'package:quwoquan_app/ui/content/pageflip/types.dart';

List<Offset> interpolatePoints(Offset start, Offset end) {
  final sizeX = (start.dx - end.dx).abs();
  final sizeY = (start.dy - end.dy).abs();
  final length = math.max(sizeX, sizeY).round().clamp(1, 100000);
  final points = <Offset>[start];
  double resolveCoord(
    double from,
    double to,
    double size,
    int index,
  ) {
    if (to > from) {
      return from + (index * (size / length));
    }
    if (to < from) {
      return from - (index * (size / length));
    }
    return from;
  }

  for (var index = 1; index <= length; index += 1) {
    points.add(
      Offset(
        resolveCoord(start.dx, end.dx, sizeX, index),
        resolveCoord(start.dy, end.dy, sizeY, index),
      ),
    );
  }
  return points;
}

double distanceBetweenPoints(Offset? a, Offset? b) {
  if (a == null || b == null) {
    return double.infinity;
  }
  return math.sqrt(
    math.pow(b.dx - a.dx, 2).toDouble() +
        math.pow(b.dy - a.dy, 2).toDouble(),
  );
}

Offset rotatePoint(Offset transformedPoint, Offset startPoint, double angle) {
  return Offset(
    transformedPoint.dx * math.cos(angle) +
        transformedPoint.dy * math.sin(angle) +
        startPoint.dx,
    transformedPoint.dy * math.cos(angle) -
        transformedPoint.dx * math.sin(angle) +
        startPoint.dy,
  );
}

double angleBetweenLines(List<Offset> line1, List<Offset> line2) {
  final a1 = line1[0].dy - line1[1].dy;
  final a2 = line2[0].dy - line2[1].dy;
  final b1 = line1[1].dx - line1[0].dx;
  final b2 = line2[1].dx - line2[0].dx;
  final numerator = (a1 * a2) + (b1 * b2);
  final denominator = math.sqrt((a1 * a1) + (b1 * b1)) *
      math.sqrt((a2 * a2) + (b2 * b2));
  if (denominator == 0) {
    return 0;
  }
  return math.acos((numerator / denominator).clamp(-1.0, 1.0).toDouble());
}

Offset? pointInRect(Rect rect, Offset? point) {
  if (point == null) {
    return null;
  }
  if (point.dx >= rect.left &&
      point.dx <= rect.left + rect.width &&
      point.dy >= rect.top &&
      point.dy <= rect.top + rect.height) {
    return point;
  }
  return null;
}

Offset limitPointToCircle(
  Offset startPoint,
  double radius,
  Offset limitedPoint,
) {
  if (distanceBetweenPoints(startPoint, limitedPoint) <= radius) {
    return limitedPoint;
  }

  final a = startPoint.dx;
  final b = startPoint.dy;
  final n = limitedPoint.dx;
  final m = limitedPoint.dy;

  var x = math.sqrt(
        (math.pow(radius, 2) * math.pow(a - n, 2)) /
            (math.pow(a - n, 2) + math.pow(b - m, 2)),
      ) +
      a;
  if (limitedPoint.dx < 0) {
    x *= -1;
  }

  var y = ((x - a) * (b - m)) / (a - n) + b;
  if (a - n + b == 0) {
    y = radius;
  }

  return Offset(x.toDouble(), y.toDouble());
}

Offset? intersectLines(List<Offset> one, List<Offset> two) {
  final a1 = one[0].dy - one[1].dy;
  final a2 = two[0].dy - two[1].dy;
  final b1 = one[1].dx - one[0].dx;
  final b2 = two[1].dx - two[0].dx;
  final c1 = one[0].dx * one[1].dy - one[1].dx * one[0].dy;
  final c2 = two[0].dx * two[1].dy - two[1].dx * two[0].dy;
  final denominator = (a1 * b2) - (a2 * b1);

  final x = -((c1 * b2 - c2 * b1) / denominator);
  final y = -((a1 * c2 - a2 * c1) / denominator);

  if (x.isFinite && y.isFinite) {
    return Offset(x.toDouble(), y.toDouble());
  }

  final det1 = (a1 * c2) - (a2 * c1);
  final det2 = (b1 * c2) - (b2 * c1);
  if ((det1 - det2).abs() < 0.1) {
    throw StateError('Segment included');
  }

  return null;
}

Offset? intersectSegmentsWithinRect(
  Rect rect,
  List<Offset> one,
  List<Offset> two,
) {
  return pointInRect(rect, intersectLines(one, two));
}

class StPageFlipCalculation {
  StPageFlipCalculation({
    required this.direction,
    required this.corner,
    required this.pageWidth,
    required this.pageHeight,
  });

  final StPageFlipDirection direction;
  final StPageFlipCorner corner;
  final double pageWidth;
  final double pageHeight;

  double _angle = 0;
  Offset _position = Offset.zero;
  StPageFlipRectPoints _rect = const StPageFlipRectPoints(
    topLeft: Offset.zero,
    topRight: Offset.zero,
    bottomLeft: Offset.zero,
    bottomRight: Offset.zero,
  );
  Offset? _topIntersectPoint;
  Offset? _sideIntersectPoint;
  Offset? _bottomIntersectPoint;

  bool calc(Offset localPos) {
    try {
      _position = _calcAngleAndPosition(localPos);
      _calculateIntersectPoint(_position);
      return true;
    } catch (_) {
      return false;
    }
  }

  List<Offset> getFlippingClipArea() {
    final result = <Offset>[_rect.topLeft];
    if (_topIntersectPoint != null) {
      result.add(_topIntersectPoint!);
    }
    var clipBottom = false;

    if (_sideIntersectPoint == null) {
      clipBottom = true;
    } else {
      result.add(_sideIntersectPoint!);
      if (_bottomIntersectPoint == null) {
        clipBottom = false;
      }
    }

    if (_bottomIntersectPoint != null) {
      result.add(_bottomIntersectPoint!);
    }

    if (clipBottom || corner == StPageFlipCorner.bottom) {
      result.add(_rect.bottomLeft);
    }
    return result;
  }

  List<Offset> getBottomClipArea() {
    final result = <Offset>[];
    if (_topIntersectPoint != null) {
      result.add(_topIntersectPoint!);
    }

    if (corner == StPageFlipCorner.top) {
      result.add(Offset(pageWidth, 0));
    } else {
      if (_topIntersectPoint != null) {
        result.add(Offset(pageWidth, 0));
      }
      result.add(Offset(pageWidth, pageHeight));
    }

    if (_sideIntersectPoint != null) {
      if (distanceBetweenPoints(_sideIntersectPoint, _topIntersectPoint) >= 10) {
        result.add(_sideIntersectPoint!);
      }
    } else if (corner == StPageFlipCorner.top) {
      result.add(Offset(pageWidth, pageHeight));
    }

    if (_bottomIntersectPoint != null) {
      result.add(_bottomIntersectPoint!);
    }
    if (_topIntersectPoint != null) {
      result.add(_topIntersectPoint!);
    }
    return result;
  }

  double getAngle() {
    if (direction == StPageFlipDirection.forward) {
      return -_angle;
    }
    return _angle;
  }

  StPageFlipRectPoints getRect() => _rect;

  Offset getPosition() => _position;

  Offset getActiveCorner() {
    if (direction == StPageFlipDirection.forward) {
      return _rect.topLeft;
    }
    return _rect.topRight;
  }

  double getFlippingProgress() {
    return (((_position.dx - pageWidth) / (2 * pageWidth)) * 100).abs();
  }

  Offset getBottomPagePosition() {
    if (direction == StPageFlipDirection.back) {
      return Offset(pageWidth, 0);
    }
    return Offset.zero;
  }

  Offset getShadowStartPoint() {
    if (corner == StPageFlipCorner.top) {
      return _topIntersectPoint ?? Offset.zero;
    }
    if (_sideIntersectPoint != null) {
      return _sideIntersectPoint!;
    }
    return _topIntersectPoint ?? Offset.zero;
  }

  double getShadowAngle() {
    final angle = angleBetweenLines(
      _segmentToShadowLine(),
      <Offset>[Offset.zero, Offset(pageWidth, 0)],
    );
    if (direction == StPageFlipDirection.forward) {
      return angle;
    }
    return math.pi - angle;
  }

  Offset _calcAngleAndPosition(Offset pos) {
    var result = pos;
    _updateAngleAndGeometry(result);

    if (corner == StPageFlipCorner.top) {
      result = _checkPositionAtCenterLine(
        result,
        Offset.zero,
        Offset(0, pageHeight),
      );
    } else {
      result = _checkPositionAtCenterLine(
        result,
        Offset(0, pageHeight),
        Offset.zero,
      );
    }

    if ((result.dx - pageWidth).abs() < 1 && result.dy.abs() < 1) {
      throw StateError('Point is too small');
    }

    return result;
  }

  void _updateAngleAndGeometry(Offset pos) {
    _angle = _calculateAngle(pos);
    _rect = _getPageRect(pos);
  }

  double _calculateAngle(Offset pos) {
    final left = pageWidth - pos.dx + 1;
    final top = corner == StPageFlipCorner.bottom
        ? pageHeight - pos.dy
        : pos.dy;

    var angle = 2 *
        math.acos(
          (left / math.sqrt((top * top) + (left * left)))
              .clamp(-1.0, 1.0)
              .toDouble(),
        );
    if (top < 0) {
      angle = -angle;
    }

    final da = math.pi - angle;
    if (!angle.isFinite || (da >= 0 && da < 0.003)) {
      throw StateError('The G point is too small');
    }
    if (corner == StPageFlipCorner.bottom) {
      angle = -angle;
    }
    return angle;
  }

  StPageFlipRectPoints _getPageRect(Offset localPos) {
    if (corner == StPageFlipCorner.top) {
      return _rectFromBasePoint(
        <Offset>[
          Offset.zero,
          Offset(pageWidth, 0),
          Offset(0, pageHeight),
          Offset(pageWidth, pageHeight),
        ],
        localPos,
      );
    }
    return _rectFromBasePoint(
      <Offset>[
        Offset(0, -pageHeight),
        Offset(pageWidth, -pageHeight),
        Offset.zero,
        Offset(pageWidth, 0),
      ],
      localPos,
    );
  }

  StPageFlipRectPoints _rectFromBasePoint(
    List<Offset> points,
    Offset localPos,
  ) {
    return StPageFlipRectPoints(
      topLeft: _rotatedPoint(points[0], localPos),
      topRight: _rotatedPoint(points[1], localPos),
      bottomLeft: _rotatedPoint(points[2], localPos),
      bottomRight: _rotatedPoint(points[3], localPos),
    );
  }

  Offset _rotatedPoint(Offset transformedPoint, Offset startPoint) {
    return rotatePoint(transformedPoint, startPoint, _angle);
  }

  void _calculateIntersectPoint(Offset pos) {
    final bounds = Rect.fromLTWH(-1, -1, pageWidth + 2, pageHeight + 2);
    if (corner == StPageFlipCorner.top) {
      _topIntersectPoint = intersectSegmentsWithinRect(
        bounds,
        <Offset>[pos, _rect.topRight],
        <Offset>[Offset.zero, Offset(pageWidth, 0)],
      );
      _sideIntersectPoint = intersectSegmentsWithinRect(
        bounds,
        <Offset>[pos, _rect.bottomLeft],
        <Offset>[Offset(pageWidth, 0), Offset(pageWidth, pageHeight)],
      );
      _bottomIntersectPoint = intersectSegmentsWithinRect(
        bounds,
        <Offset>[_rect.bottomLeft, _rect.bottomRight],
        <Offset>[Offset(0, pageHeight), Offset(pageWidth, pageHeight)],
      );
    } else {
      _topIntersectPoint = intersectSegmentsWithinRect(
        bounds,
        <Offset>[_rect.topLeft, _rect.topRight],
        <Offset>[Offset.zero, Offset(pageWidth, 0)],
      );
      _sideIntersectPoint = intersectSegmentsWithinRect(
        bounds,
        <Offset>[pos, _rect.topLeft],
        <Offset>[Offset(pageWidth, 0), Offset(pageWidth, pageHeight)],
      );
      _bottomIntersectPoint = intersectSegmentsWithinRect(
        bounds,
        <Offset>[_rect.bottomLeft, _rect.bottomRight],
        <Offset>[Offset(0, pageHeight), Offset(pageWidth, pageHeight)],
      );
    }
  }

  Offset _checkPositionAtCenterLine(
    Offset checkedPos,
    Offset centerOne,
    Offset centerTwo,
  ) {
    var result = checkedPos;
    final limited = limitPointToCircle(centerOne, pageWidth, result);
    if (limited != result) {
      result = limited;
      _updateAngleAndGeometry(result);
    }

    final radius = math.sqrt((pageWidth * pageWidth) + (pageHeight * pageHeight));
    var checkPointOne = _rect.bottomRight;
    var checkPointTwo = _rect.topLeft;
    if (corner == StPageFlipCorner.bottom) {
      checkPointOne = _rect.topRight;
      checkPointTwo = _rect.bottomLeft;
    }

    if (checkPointOne.dx <= 0) {
      final bottomPoint = limitPointToCircle(centerTwo, radius, checkPointTwo);
      if (bottomPoint != result) {
        result = bottomPoint;
        _updateAngleAndGeometry(result);
      }
    }

    return result;
  }

  List<Offset> _segmentToShadowLine() {
    final first = getShadowStartPoint();
    final second =
        first != _sideIntersectPoint && _sideIntersectPoint != null
        ? _sideIntersectPoint!
        : (_bottomIntersectPoint ?? first);
    return <Offset>[first, second];
  }
}
