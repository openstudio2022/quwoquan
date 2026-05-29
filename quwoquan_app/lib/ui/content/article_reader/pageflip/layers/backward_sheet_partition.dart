import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/layers/article_reader_soft_page_geometry.dart';

typedef BackwardPageLine = (Offset, Offset);

enum BackwardCanonicalSheetFailureReason {
  none,
  foldMissing,
  freeEdgeMissing,
  sheetDegenerate,
}

enum BackwardCanonicalFaceFailureReason {
  none,
  sheetDegenerate,
  foldMissing,
  freeEdgeMissing,
  faceEmpty,
  faceAreaFiltered,
}

@immutable
class BackwardCanonicalSheetInput {
  const BackwardCanonicalSheetInput({
    required this.pageSize,
    required this.sheetLocalPolygon,
    required this.sheetAreaPolygon,
    required this.sheetLocalFoldLine,
    required this.sheetLocalFreeEdgeLine,
    required this.currentResidualPagePolygon,
  });

  final Size pageSize;
  final List<Offset> sheetLocalPolygon;
  final List<Offset> sheetAreaPolygon;
  final BackwardPageLine? sheetLocalFoldLine;
  final BackwardPageLine? sheetLocalFreeEdgeLine;
  final List<Offset> currentResidualPagePolygon;
}

@immutable
class BackwardCanonicalSheetFaces {
  const BackwardCanonicalSheetFaces({
    required this.sheetLocalPolygon,
    required this.sheetAreaPolygon,
    required this.previousFrontRevealPagePolygon,
    required this.previousBackVersoSheetPolygon,
    required this.previousBackVersoSheetAreaPolygon,
    required this.previousFrontRectoLocalPolygon,
    required this.previousFrontRectoAreaPolygon,
    required this.previousBackVersoLocalPolygon,
    required this.previousBackVersoAreaPolygon,
    required this.paintedUnionLocalPolygon,
    required this.paintedUnionAreaPolygon,
    required this.currentResidualPagePolygon,
    required this.sheetLocalFoldLine,
    required this.sheetLocalFreeEdgeLine,
    required this.rectoArea,
    required this.versoArea,
    required this.rectoVersoOverlap,
    required this.failureReason,
    required this.rectoFailureReason,
    required this.versoFailureReason,
  });

  final List<Offset> sheetLocalPolygon;
  final List<Offset> sheetAreaPolygon;
  final List<Offset> previousFrontRevealPagePolygon;
  final List<Offset> previousBackVersoSheetPolygon;
  final List<Offset> previousBackVersoSheetAreaPolygon;
  final List<Offset> previousFrontRectoLocalPolygon;
  final List<Offset> previousFrontRectoAreaPolygon;
  final List<Offset> previousBackVersoLocalPolygon;
  final List<Offset> previousBackVersoAreaPolygon;
  final List<Offset> paintedUnionLocalPolygon;
  final List<Offset> paintedUnionAreaPolygon;
  final List<Offset> currentResidualPagePolygon;
  final BackwardPageLine? sheetLocalFoldLine;
  final BackwardPageLine? sheetLocalFreeEdgeLine;
  final double rectoArea;
  final double versoArea;
  final double rectoVersoOverlap;
  final BackwardCanonicalSheetFailureReason failureReason;
  final BackwardCanonicalFaceFailureReason rectoFailureReason;
  final BackwardCanonicalFaceFailureReason versoFailureReason;
}

List<Offset> resolveBackwardPreviousFrontRevealPagePolygon({
  required Size pageSize,
  required List<Offset> currentResidualPagePolygon,
}) {
  final pageRect = Offset.zero & pageSize;
  final residualBounds = polygonBounds(currentResidualPagePolygon);
  if (residualBounds == null || residualBounds.isEmpty) {
    return <Offset>[
      pageRect.topLeft,
      pageRect.topRight,
      pageRect.bottomRight,
      pageRect.bottomLeft,
    ];
  }
  final left = residualBounds.left.clamp(0.0, pageSize.width).toDouble();
  final top = residualBounds.top.clamp(0.0, pageSize.height).toDouble();
  if (left <= 0.5 && top <= 0.5) {
    return const <Offset>[];
  }
  return <Offset>[
    Offset.zero,
    Offset(pageSize.width, 0),
    Offset(pageSize.width, top),
    Offset(left, top),
    Offset(left, pageSize.height),
    Offset(0, pageSize.height),
  ];
}

BackwardCanonicalSheetFaces resolveBackwardCanonicalSheetFaces(
  BackwardCanonicalSheetInput input,
) {
  final currentResidualPagePolygon = _safePolygon(
    input.currentResidualPagePolygon,
  );

  BackwardCanonicalSheetFaces empty({
    required BackwardCanonicalSheetFailureReason failureReason,
  }) {
    final faceFailure = switch (failureReason) {
      BackwardCanonicalSheetFailureReason.none =>
        BackwardCanonicalFaceFailureReason.none,
      BackwardCanonicalSheetFailureReason.foldMissing =>
        BackwardCanonicalFaceFailureReason.foldMissing,
      BackwardCanonicalSheetFailureReason.freeEdgeMissing =>
        BackwardCanonicalFaceFailureReason.freeEdgeMissing,
      BackwardCanonicalSheetFailureReason.sheetDegenerate =>
        BackwardCanonicalFaceFailureReason.sheetDegenerate,
    };
    return BackwardCanonicalSheetFaces(
      sheetLocalPolygon: const <Offset>[],
      sheetAreaPolygon: const <Offset>[],
      previousFrontRevealPagePolygon: resolveBackwardPreviousFrontRevealPagePolygon(
        pageSize: input.pageSize,
        currentResidualPagePolygon: currentResidualPagePolygon,
      ),
      previousBackVersoSheetPolygon: const <Offset>[],
      previousBackVersoSheetAreaPolygon: const <Offset>[],
      previousFrontRectoLocalPolygon: const <Offset>[],
      previousFrontRectoAreaPolygon: const <Offset>[],
      previousBackVersoLocalPolygon: const <Offset>[],
      previousBackVersoAreaPolygon: const <Offset>[],
      paintedUnionLocalPolygon: const <Offset>[],
      paintedUnionAreaPolygon: const <Offset>[],
      currentResidualPagePolygon: currentResidualPagePolygon,
      sheetLocalFoldLine: input.sheetLocalFoldLine,
      sheetLocalFreeEdgeLine: input.sheetLocalFreeEdgeLine,
      rectoArea: 0,
      versoArea: 0,
      rectoVersoOverlap: 0,
      failureReason: failureReason,
      rectoFailureReason: faceFailure,
      versoFailureReason: faceFailure,
    );
  }

  if (input.pageSize.isEmpty || input.sheetLocalPolygon.length < 3) {
    return empty(
      failureReason: BackwardCanonicalSheetFailureReason.sheetDegenerate,
    );
  }
  final foldLine = input.sheetLocalFoldLine;
  if (foldLine == null) {
    return empty(
      failureReason: BackwardCanonicalSheetFailureReason.foldMissing,
    );
  }
  final rawFreeEdgeLine = input.sheetLocalFreeEdgeLine;
  if (rawFreeEdgeLine == null) {
    return empty(
      failureReason: BackwardCanonicalSheetFailureReason.freeEdgeMissing,
    );
  }

  final pairedSheet = _sortPairedPolygonClockwise(
    localPolygon: input.sheetLocalPolygon,
    areaPolygon: input.sheetAreaPolygon,
  );
  final sheetLocalPolygon = List<Offset>.unmodifiable(pairedSheet.localPolygon);
  final sheetAreaPolygon = List<Offset>.unmodifiable(pairedSheet.areaPolygon);
  final splitLine = _resolveCanonicalFaceSplitLine(
    sheetLocalPolygon: sheetLocalPolygon,
    foldLine: foldLine,
    freeEdgeLine: rawFreeEdgeLine,
  );
  final versoProbe = _farthestSheetPointTowardFree(
    sheetLocalPolygon: sheetLocalPolygon,
    foldLine: foldLine,
    freeEdgeLine: rawFreeEdgeLine,
  );
  final keepVersoSide = lineSide(splitLine, versoProbe) >= 0;

  final recto = _clipPairedPolygonByLine(
    localPolygon: sheetLocalPolygon,
    areaPolygon: sheetAreaPolygon,
    line: splitLine,
    keepPositiveSide: !keepVersoSide,
  );
  final verso = _clipPairedPolygonByLine(
    localPolygon: sheetLocalPolygon,
    areaPolygon: sheetAreaPolygon,
    line: splitLine,
    keepPositiveSide: keepVersoSide,
  );

  final rectoFailure = _isVisibleFace(recto.localPolygon)
      ? BackwardCanonicalFaceFailureReason.none
      : BackwardCanonicalFaceFailureReason.faceEmpty;
  final versoFailure = _isVisibleFace(verso.localPolygon)
      ? BackwardCanonicalFaceFailureReason.none
      : BackwardCanonicalFaceFailureReason.faceEmpty;
  final paintedUnion =
      recto.localPolygon.isNotEmpty || verso.localPolygon.isNotEmpty
      ? sheetLocalPolygon
      : const <Offset>[];
  final paintedUnionArea =
      recto.areaPolygon.isNotEmpty || verso.areaPolygon.isNotEmpty
      ? sheetAreaPolygon
      : const <Offset>[];

  return BackwardCanonicalSheetFaces(
    sheetLocalPolygon: sheetLocalPolygon,
    sheetAreaPolygon: sheetAreaPolygon,
    previousFrontRevealPagePolygon: resolveBackwardPreviousFrontRevealPagePolygon(
      pageSize: input.pageSize,
      currentResidualPagePolygon: currentResidualPagePolygon,
    ),
    previousBackVersoSheetPolygon: List<Offset>.unmodifiable(
      verso.localPolygon,
    ),
    previousBackVersoSheetAreaPolygon: List<Offset>.unmodifiable(
      verso.areaPolygon,
    ),
    previousFrontRectoLocalPolygon: List<Offset>.unmodifiable(
      recto.localPolygon,
    ),
    previousFrontRectoAreaPolygon: List<Offset>.unmodifiable(recto.areaPolygon),
    previousBackVersoLocalPolygon: List<Offset>.unmodifiable(
      verso.localPolygon,
    ),
    previousBackVersoAreaPolygon: List<Offset>.unmodifiable(verso.areaPolygon),
    paintedUnionLocalPolygon: List<Offset>.unmodifiable(paintedUnion),
    paintedUnionAreaPolygon: List<Offset>.unmodifiable(paintedUnionArea),
    currentResidualPagePolygon: currentResidualPagePolygon,
    sheetLocalFoldLine: foldLine,
    sheetLocalFreeEdgeLine: rawFreeEdgeLine,
    rectoArea: _polygonArea(recto.localPolygon),
    versoArea: _polygonArea(verso.localPolygon),
    rectoVersoOverlap: _polygonIntersectionArea(
      recto.localPolygon,
      verso.localPolygon,
    ),
    failureReason: BackwardCanonicalSheetFailureReason.none,
    rectoFailureReason: rectoFailure,
    versoFailureReason: versoFailure,
  );
}

bool backwardPartitionContainsPoint({
  required List<Offset> polygon,
  required Offset point,
}) {
  if (polygon.length < 3) {
    return false;
  }
  var inside = false;
  for (var i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    final pi = polygon[i];
    final pj = polygon[j];
    final intersects =
        ((pi.dy > point.dy) != (pj.dy > point.dy)) &&
        point.dx <
            (pj.dx - pi.dx) * (point.dy - pi.dy) / (pj.dy - pi.dy) + pi.dx;
    if (intersects) {
      inside = !inside;
    }
  }
  return inside;
}

BackwardPageLine _resolveCanonicalFaceSplitLine({
  required List<Offset> sheetLocalPolygon,
  required BackwardPageLine foldLine,
  required BackwardPageLine freeEdgeLine,
}) {
  final bounds = polygonBounds(sheetLocalPolygon);
  if (bounds == null || bounds.width <= 0.0001 || bounds.height <= 0.0001) {
    return foldLine;
  }
  final freeSignedDistance = _signedDistanceToLine(
    line: foldLine,
    point: _midPoint(freeEdgeLine),
  );
  final freeDirection = freeSignedDistance >= 0 ? 1.0 : -1.0;
  final projectedDistances = sheetLocalPolygon
      .map(
        (point) =>
            _signedDistanceToLine(line: foldLine, point: point) * freeDirection,
      )
      .toList(growable: false);
  var minDistance = projectedDistances.first;
  var maxDistance = projectedDistances.first;
  for (final distance in projectedDistances.skip(1)) {
    minDistance = math.min(minDistance, distance);
    maxDistance = math.max(maxDistance, distance);
  }
  final span = maxDistance - minDistance;
  if (span <= 0.0001) {
    return foldLine;
  }
  final splitDistance = ((minDistance + maxDistance) / 2)
      .clamp(minDistance, maxDistance)
      .toDouble();
  return _offsetLineToward(
    line: foldLine,
    towardPoint: _midPoint(freeEdgeLine),
    distance: splitDistance.toDouble(),
  );
}

BackwardPageLine _offsetLineToward({
  required BackwardPageLine line,
  required Offset towardPoint,
  required double distance,
}) {
  final dx = line.$2.dx - line.$1.dx;
  final dy = line.$2.dy - line.$1.dy;
  final length = math.sqrt(dx * dx + dy * dy);
  if (length <= 0.000001) {
    return line;
  }
  final normal = Offset(-dy / length, dx / length);
  final direction = lineSide(line, towardPoint) >= 0 ? 1.0 : -1.0;
  final delta = normal * direction * distance;
  return (line.$1 + delta, line.$2 + delta);
}

Offset _farthestSheetPointTowardFree({
  required List<Offset> sheetLocalPolygon,
  required BackwardPageLine foldLine,
  required BackwardPageLine freeEdgeLine,
}) {
  final freeSignedDistance = _signedDistanceToLine(
    line: foldLine,
    point: _midPoint(freeEdgeLine),
  );
  final freeDirection = freeSignedDistance >= 0 ? 1.0 : -1.0;
  var bestPoint = sheetLocalPolygon.first;
  var bestDistance =
      _signedDistanceToLine(line: foldLine, point: bestPoint) * freeDirection;
  for (final point in sheetLocalPolygon.skip(1)) {
    final distance =
        _signedDistanceToLine(line: foldLine, point: point) * freeDirection;
    if (distance > bestDistance) {
      bestDistance = distance;
      bestPoint = point;
    }
  }
  return bestPoint;
}

double _signedDistanceToLine({
  required BackwardPageLine line,
  required Offset point,
}) {
  final dx = line.$2.dx - line.$1.dx;
  final dy = line.$2.dy - line.$1.dy;
  final length = math.sqrt(dx * dx + dy * dy);
  if (length <= 0.000001) {
    return 0;
  }
  return lineSide(line, point) / length;
}

({List<Offset> localPolygon, List<Offset> areaPolygon})
_clipPairedPolygonByLine({
  required List<Offset> localPolygon,
  required List<Offset> areaPolygon,
  required BackwardPageLine line,
  required bool keepPositiveSide,
}) {
  if (localPolygon.length < 3 || areaPolygon.length != localPolygon.length) {
    return _emptyPaired();
  }
  final localResult = <Offset>[];
  final areaResult = <Offset>[];
  for (var index = 0; index < localPolygon.length; index += 1) {
    final currentLocal = localPolygon[index];
    final nextLocal = localPolygon[(index + 1) % localPolygon.length];
    final currentArea = areaPolygon[index];
    final nextArea = areaPolygon[(index + 1) % areaPolygon.length];
    final currentSide = lineSide(line, currentLocal);
    final nextSide = lineSide(line, nextLocal);
    final currentInside = keepPositiveSide
        ? currentSide >= -0.0001
        : currentSide <= 0.0001;
    final nextInside = keepPositiveSide
        ? nextSide >= -0.0001
        : nextSide <= 0.0001;
    if (currentInside) {
      localResult.add(currentLocal);
      areaResult.add(currentArea);
    }
    if (currentInside != nextInside) {
      final denominator = currentSide - nextSide;
      if (denominator.abs() > 0.000001) {
        final t = (currentSide / denominator).clamp(0.0, 1.0).toDouble();
        localResult.add(Offset.lerp(currentLocal, nextLocal, t)!);
        areaResult.add(Offset.lerp(currentArea, nextArea, t)!);
      }
    }
  }
  return (
    localPolygon: _dedupePolygon(localResult),
    areaPolygon: _dedupePolygon(areaResult),
  );
}

({List<Offset> localPolygon, List<Offset> areaPolygon})
_sortPairedPolygonClockwise({
  required List<Offset> localPolygon,
  required List<Offset> areaPolygon,
}) {
  if (localPolygon.length < 3) {
    return _emptyPaired();
  }
  final pairedArea = areaPolygon.length == localPolygon.length
      ? areaPolygon
      : localPolygon;
  final center =
      localPolygon.fold(Offset.zero, (sum, point) => sum + point) /
      localPolygon.length.toDouble();
  final indexed = <({Offset local, Offset area, double angle})>[
    for (var index = 0; index < localPolygon.length; index += 1)
      (
        local: localPolygon[index],
        area: pairedArea[index],
        angle: math.atan2(
          localPolygon[index].dy - center.dy,
          localPolygon[index].dx - center.dx,
        ),
      ),
  ]..sort((a, b) => a.angle.compareTo(b.angle));
  return (
    localPolygon: indexed.map((entry) => entry.local).toList(growable: false),
    areaPolygon: indexed.map((entry) => entry.area).toList(growable: false),
  );
}

List<Offset> _dedupePolygon(List<Offset> polygon) {
  if (polygon.isEmpty) {
    return const <Offset>[];
  }
  final result = <Offset>[];
  for (final point in polygon) {
    if (result.isEmpty || (result.last - point).distance > 0.001) {
      result.add(point);
    }
  }
  if (result.length > 1 && (result.first - result.last).distance <= 0.001) {
    result.removeLast();
  }
  return result.length >= 3 ? result : const <Offset>[];
}

List<Offset> _safePolygon(List<Offset> polygon) {
  return polygon.length < 3
      ? const <Offset>[]
      : List<Offset>.unmodifiable(polygon);
}

bool _isVisibleFace(List<Offset> polygon) {
  return polygon.length >= 3 && polygonHasVisibleArea(polygon);
}

bool _looksLikeWholeSheet(List<Offset> polygon, List<Offset> sheet) {
  final polygonBoundsValue = polygonBounds(polygon);
  final sheetBounds = polygonBounds(sheet);
  if (polygonBoundsValue == null || sheetBounds == null) {
    return false;
  }
  return polygonBoundsValue.width >= sheetBounds.width * 0.92 &&
      polygonBoundsValue.height >= sheetBounds.height * 0.92;
}

Offset _midPoint(BackwardPageLine line) {
  return Offset((line.$1.dx + line.$2.dx) / 2, (line.$1.dy + line.$2.dy) / 2);
}

({List<Offset> localPolygon, List<Offset> areaPolygon}) _emptyPaired() {
  return (localPolygon: const <Offset>[], areaPolygon: const <Offset>[]);
}

double _polygonArea(List<Offset> polygon) {
  if (polygon.length < 3) {
    return 0;
  }
  var doubledArea = 0.0;
  for (var index = 0; index < polygon.length; index += 1) {
    final current = polygon[index];
    final next = polygon[(index + 1) % polygon.length];
    doubledArea += current.dx * next.dy - next.dx * current.dy;
  }
  return doubledArea.abs() / 2;
}

double _polygonIntersectionArea(List<Offset> a, List<Offset> b) {
  if (!_isVisibleFace(a) || !_isVisibleFace(b)) {
    return 0;
  }
  var clipped = a;
  final keepPositiveSide = _signedPolygonArea(b) >= 0;
  for (var index = 0; index < b.length; index += 1) {
    clipped = clipPolygonByLine(
      polygon: clipped,
      line: (b[index], b[(index + 1) % b.length]),
      keepPositiveSide: keepPositiveSide,
    );
    if (!_isVisibleFace(clipped)) {
      return 0;
    }
  }
  return _polygonArea(clipped);
}

double _signedPolygonArea(List<Offset> polygon) {
  var doubledArea = 0.0;
  for (var index = 0; index < polygon.length; index += 1) {
    final current = polygon[index];
    final next = polygon[(index + 1) % polygon.length];
    doubledArea += current.dx * next.dy - next.dx * current.dy;
  }
  return doubledArea / 2;
}
