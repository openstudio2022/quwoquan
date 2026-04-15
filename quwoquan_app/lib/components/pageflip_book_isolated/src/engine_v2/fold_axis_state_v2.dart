import 'dart:math' as math;
import 'dart:ui';

import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/contracts/pageflip_book_contracts.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/engine_v2/page_touch_state_v2.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

@immutable
class FoldAxisStateV2 {
  const FoldAxisStateV2({
    required this.touchState,
    required this.position,
    required this.angle,
    required this.rectPoints,
    required this.activeCorner,
    required this.flippingClipPoints,
    required this.bottomClipPoints,
    required this.progress,
    required this.shadowStartPoint,
    required this.shadowAngle,
  });

  final PageTouchStateV2 touchState;
  final Offset position;
  final double angle;
  final StPageFlipRectPoints rectPoints;
  final Offset activeCorner;
  final List<Offset> flippingClipPoints;
  final List<Offset> bottomClipPoints;
  final double progress;
  final Offset shadowStartPoint;
  final double shadowAngle;

  Path get flippingClipPath => _pathFromPolygon(flippingClipPoints);

  Path get bottomClipPath => _pathFromPolygon(bottomClipPoints);
}

FoldAxisStateV2 resolveFoldAxisStateV2({
  required PageTouchStateV2 touchState,
  required Size pageSize,
}) {
  return _FoldAxisCalculationV2(
    touchState: touchState,
    pageWidth: pageSize.width,
    pageHeight: pageSize.height,
  ).resolve();
}

class _FoldAxisCalculationV2 {
  _FoldAxisCalculationV2({
    required this.touchState,
    required this.pageWidth,
    required this.pageHeight,
  });

  final PageTouchStateV2 touchState;
  final double pageWidth;
  final double pageHeight;

  late double _angle;
  late Offset _position;
  late StPageFlipRectPoints _rect;
  Offset? _topIntersectPoint;
  Offset? _sideIntersectPoint;
  Offset? _bottomIntersectPoint;

  PageflipBookIsolatedCorner get corner => touchState.corner;

  FoldAxisStateV2 resolve() {
    _position = _resolveAngleAndPosition(touchState.workingPagePoint);
    _calculateIntersectPoints(_position);
    final progress =
        (((_position.dx - pageWidth) / (2 * pageWidth)) * 100)
            .abs()
            .clamp(0.0, 100.0)
            .toDouble() /
        100;
    return FoldAxisStateV2(
      touchState: touchState,
      position: _position,
      angle: _angle,
      rectPoints: _rect,
      activeCorner: _rect.topLeft,
      flippingClipPoints: _buildFlippingClipPoints(),
      bottomClipPoints: _buildBottomClipPoints(),
      progress: progress,
      shadowStartPoint: _resolveShadowStartPoint(),
      shadowAngle: _resolveShadowAngle(),
    );
  }

  Offset _resolveAngleAndPosition(Offset point) {
    var result = point;
    _updateAngleAndGeometry(result);
    result = corner == PageflipBookIsolatedCorner.top
        ? _checkPositionAtCenterLine(result, Offset.zero, Offset(0, pageHeight))
        : _checkPositionAtCenterLine(
            result,
            Offset(0, pageHeight),
            Offset.zero,
          );
    if ((result.dx - pageWidth).abs() < 1 && result.dy.abs() < 1) {
      final safeY = corner == PageflipBookIsolatedCorner.bottom
          ? pageHeight - 1
          : 1.0;
      result = Offset(pageWidth - 1, safeY);
      _updateAngleAndGeometry(result);
    }
    return result;
  }

  void _updateAngleAndGeometry(Offset point) {
    _angle = _calculateAngle(point);
    _rect = _resolvePageRect(point);
  }

  double _calculateAngle(Offset point) {
    final left = pageWidth - point.dx + 1;
    final top = corner == PageflipBookIsolatedCorner.bottom
        ? pageHeight - point.dy
        : point.dy;
    var angle =
        2 *
        math.acos(
          (left / math.sqrt((top * top) + (left * left)))
              .clamp(-1.0, 1.0)
              .toDouble(),
        );
    if (top < 0) {
      angle = -angle;
    }
    final delta = math.pi - angle;
    if (!angle.isFinite || (delta >= 0 && delta < 0.003)) {
      throw StateError('The G point is too small');
    }
    if (corner == PageflipBookIsolatedCorner.bottom) {
      angle = -angle;
    }
    return angle;
  }

  StPageFlipRectPoints _resolvePageRect(Offset point) {
    final basePoints = corner == PageflipBookIsolatedCorner.top
        ? <Offset>[
            Offset.zero,
            Offset(pageWidth, 0),
            Offset(0, pageHeight),
            Offset(pageWidth, pageHeight),
          ]
        : <Offset>[
            Offset(0, -pageHeight),
            Offset(pageWidth, -pageHeight),
            Offset.zero,
            Offset(pageWidth, 0),
          ];
    return StPageFlipRectPoints(
      topLeft: _rotatePoint(basePoints[0], point, _angle),
      topRight: _rotatePoint(basePoints[1], point, _angle),
      bottomLeft: _rotatePoint(basePoints[2], point, _angle),
      bottomRight: _rotatePoint(basePoints[3], point, _angle),
    );
  }

  void _calculateIntersectPoints(Offset point) {
    final bounds = Rect.fromLTWH(-1, -1, pageWidth + 2, pageHeight + 2);
    if (corner == PageflipBookIsolatedCorner.top) {
      _topIntersectPoint = _intersectSegmentsWithinRect(
        bounds,
        <Offset>[point, _rect.topRight],
        <Offset>[Offset.zero, Offset(pageWidth, 0)],
      );
      _sideIntersectPoint = _intersectSegmentsWithinRect(
        bounds,
        <Offset>[point, _rect.bottomLeft],
        <Offset>[Offset(pageWidth, 0), Offset(pageWidth, pageHeight)],
      );
      _bottomIntersectPoint = _intersectSegmentsWithinRect(
        bounds,
        <Offset>[_rect.bottomLeft, _rect.bottomRight],
        <Offset>[Offset(0, pageHeight), Offset(pageWidth, pageHeight)],
      );
    } else {
      _topIntersectPoint = _intersectSegmentsWithinRect(
        bounds,
        <Offset>[_rect.topLeft, _rect.topRight],
        <Offset>[Offset.zero, Offset(pageWidth, 0)],
      );
      _sideIntersectPoint = _intersectSegmentsWithinRect(
        bounds,
        <Offset>[point, _rect.topLeft],
        <Offset>[Offset(pageWidth, 0), Offset(pageWidth, pageHeight)],
      );
      _bottomIntersectPoint = _intersectSegmentsWithinRect(
        bounds,
        <Offset>[_rect.bottomLeft, _rect.bottomRight],
        <Offset>[Offset(0, pageHeight), Offset(pageWidth, pageHeight)],
      );
    }
  }

  List<Offset> _buildFlippingClipPoints() {
    final points = <Offset>[_rect.topLeft];
    if (_topIntersectPoint != null) {
      points.add(_topIntersectPoint!);
    }
    var clipBottom = false;
    if (_sideIntersectPoint == null) {
      clipBottom = true;
    } else {
      points.add(_sideIntersectPoint!);
      if (_bottomIntersectPoint == null) {
        clipBottom = false;
      }
    }
    if (_bottomIntersectPoint != null) {
      points.add(_bottomIntersectPoint!);
    }
    if (clipBottom || corner == PageflipBookIsolatedCorner.bottom) {
      points.add(_rect.bottomLeft);
    }
    return points;
  }

  List<Offset> _buildBottomClipPoints() {
    final points = <Offset>[];
    if (_topIntersectPoint != null) {
      points.add(_topIntersectPoint!);
    }
    if (corner == PageflipBookIsolatedCorner.top) {
      points.add(Offset(pageWidth, 0));
    } else {
      if (_topIntersectPoint != null) {
        points.add(Offset(pageWidth, 0));
      }
      points.add(Offset(pageWidth, pageHeight));
    }
    if (_sideIntersectPoint != null) {
      if (_distanceBetweenPoints(_sideIntersectPoint, _topIntersectPoint) >=
          10) {
        points.add(_sideIntersectPoint!);
      }
    } else if (corner == PageflipBookIsolatedCorner.top) {
      points.add(Offset(pageWidth, pageHeight));
    }
    if (_bottomIntersectPoint != null) {
      points.add(_bottomIntersectPoint!);
    }
    if (_topIntersectPoint != null) {
      points.add(_topIntersectPoint!);
    }
    return points;
  }

  Offset _resolveShadowStartPoint() {
    if (corner == PageflipBookIsolatedCorner.top) {
      return _topIntersectPoint ?? Offset.zero;
    }
    if (_sideIntersectPoint != null) {
      return _sideIntersectPoint!;
    }
    return _topIntersectPoint ?? Offset.zero;
  }

  double _resolveShadowAngle() {
    final shadowLine = <Offset>[
      _resolveShadowStartPoint(),
      _sideIntersectPoint != null &&
              _resolveShadowStartPoint() != _sideIntersectPoint
          ? _sideIntersectPoint!
          : (_bottomIntersectPoint ?? _resolveShadowStartPoint()),
    ];
    return _angleBetweenLines(shadowLine, <Offset>[
      Offset.zero,
      Offset(pageWidth, 0),
    ]);
  }

  Offset _checkPositionAtCenterLine(
    Offset point,
    Offset centerOne,
    Offset centerTwo,
  ) {
    var result = point;
    final limitedToWidth = _limitPointToCircle(centerOne, pageWidth, result);
    if (result != limitedToWidth) {
      result = limitedToWidth;
      _updateAngleAndGeometry(result);
    }
    final diagonalRadius = math.sqrt(
      math.pow(pageWidth, 2) + math.pow(pageHeight, 2),
    );
    var checkPointOne = _rect.bottomRight;
    var checkPointTwo = _rect.topLeft;
    if (corner == PageflipBookIsolatedCorner.bottom) {
      checkPointOne = _rect.topRight;
      checkPointTwo = _rect.bottomLeft;
    }
    if (checkPointOne.dx <= 0) {
      final bottomPoint = _limitPointToCircle(
        centerTwo,
        diagonalRadius,
        checkPointTwo,
      );
      if (bottomPoint != result) {
        result = bottomPoint;
        _updateAngleAndGeometry(result);
      }
    }
    return result;
  }
}

Path _pathFromPolygon(List<Offset> polygon) {
  if (polygon.length < 3) {
    return Path();
  }
  final path = Path()..moveTo(polygon.first.dx, polygon.first.dy);
  for (final point in polygon.skip(1)) {
    path.lineTo(point.dx, point.dy);
  }
  path.close();
  return path;
}

double _distanceBetweenPoints(Offset? a, Offset? b) {
  if (a == null || b == null) {
    return double.infinity;
  }
  return math.sqrt(
    math.pow(b.dx - a.dx, 2).toDouble() + math.pow(b.dy - a.dy, 2).toDouble(),
  );
}

Offset _rotatePoint(Offset transformedPoint, Offset startPoint, double angle) {
  return Offset(
    transformedPoint.dx * math.cos(angle) +
        transformedPoint.dy * math.sin(angle) +
        startPoint.dx,
    transformedPoint.dy * math.cos(angle) -
        transformedPoint.dx * math.sin(angle) +
        startPoint.dy,
  );
}

double _angleBetweenLines(List<Offset> line1, List<Offset> line2) {
  final a1 = line1[0].dy - line1[1].dy;
  final a2 = line2[0].dy - line2[1].dy;
  final b1 = line1[1].dx - line1[0].dx;
  final b2 = line2[1].dx - line2[0].dx;
  final numerator = (a1 * a2) + (b1 * b2);
  final denominator =
      math.sqrt((a1 * a1) + (b1 * b1)) * math.sqrt((a2 * a2) + (b2 * b2));
  if (denominator == 0) {
    return 0;
  }
  return math.acos((numerator / denominator).clamp(-1.0, 1.0).toDouble());
}

Offset _limitPointToCircle(Offset center, double radius, Offset point) {
  if (_distanceBetweenPoints(center, point) <= radius) {
    return point;
  }
  final dx = point.dx - center.dx;
  final dy = point.dy - center.dy;
  final distance = math.sqrt(dx * dx + dy * dy);
  if (distance <= 0.0001) {
    return Offset(center.dx + radius, center.dy);
  }
  final scale = radius / distance;
  return Offset(center.dx + dx * scale, center.dy + dy * scale);
}

Offset? _intersectLines(List<Offset> one, List<Offset> two) {
  final a1 = one[0].dy - one[1].dy;
  final a2 = two[0].dy - two[1].dy;
  final b1 = one[1].dx - one[0].dx;
  final b2 = two[1].dx - two[0].dx;
  final c1 = one[0].dx * one[1].dy - one[1].dx * one[0].dy;
  final c2 = two[0].dx * two[1].dy - two[1].dx * two[0].dy;
  final denominator = (a1 * b2) - (a2 * b1);
  if (denominator.abs() < 0.0001) {
    return null;
  }
  final x = -((c1 * b2 - c2 * b1) / denominator);
  final y = -((a1 * c2 - a2 * c1) / denominator);
  if (x.isFinite && y.isFinite) {
    return Offset(x.toDouble(), y.toDouble());
  }
  return null;
}

Offset? _intersectSegmentsWithinRect(
  Rect rect,
  List<Offset> one,
  List<Offset> two,
) {
  final point = _intersectLines(one, two);
  if (point == null) {
    return null;
  }
  if (point.dx >= rect.left &&
      point.dx <= rect.right &&
      point.dy >= rect.top &&
      point.dy <= rect.bottom) {
    return point;
  }
  return null;
}
