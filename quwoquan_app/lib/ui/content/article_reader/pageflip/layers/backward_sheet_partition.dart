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

  final sheetLocalPolygon = List<Offset>.unmodifiable(input.sheetLocalPolygon);
  final sheetAreaPolygon =
      input.sheetAreaPolygon.length == input.sheetLocalPolygon.length
      ? List<Offset>.unmodifiable(input.sheetAreaPolygon)
      : sheetLocalPolygon;
  final splitX = _resolveCanonicalFaceSplitX(
    sheetLocalPolygon: sheetLocalPolygon,
    foldLine: foldLine,
    freeEdgeLine: rawFreeEdgeLine,
    pageSize: input.pageSize,
  );

  final recto = _clipPairedPolygonToXRange(
    localPolygon: sheetLocalPolygon,
    areaPolygon: sheetAreaPolygon,
    minX: splitX,
    maxX: double.infinity,
  );
  final verso = _clipPairedPolygonToXRange(
    localPolygon: sheetLocalPolygon,
    areaPolygon: sheetAreaPolygon,
    minX: double.negativeInfinity,
    maxX: splitX,
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

double _resolveCanonicalFaceSplitX({
  required List<Offset> sheetLocalPolygon,
  required BackwardPageLine foldLine,
  required BackwardPageLine freeEdgeLine,
  required Size pageSize,
}) {
  final bounds = polygonBounds(sheetLocalPolygon);
  if (bounds == null || bounds.width <= 0.0001) {
    return _midPoint(foldLine).dx;
  }
  final minFaceWidth = math.min(
    math.max(1.0, math.min(pageSize.width, bounds.width) * 0.08),
    bounds.width / 2,
  );
  final foldMidX = _midPoint(foldLine).dx;
  final freeMidX = _midPoint(freeEdgeLine).dx;
  final foldInsideX = foldMidX.clamp(bounds.left, bounds.right).toDouble();
  final freeInsideX = freeMidX.clamp(bounds.left, bounds.right).toDouble();
  final rawSplit = (foldInsideX * 0.82 + freeInsideX * 0.18).clamp(
    bounds.left + minFaceWidth,
    bounds.right - minFaceWidth,
  );
  return rawSplit.toDouble();
}

({List<Offset> localPolygon, List<Offset> areaPolygon})
_clipPairedPolygonToXRange({
  required List<Offset> localPolygon,
  required List<Offset> areaPolygon,
  required double minX,
  required double maxX,
}) {
  var result = (localPolygon: localPolygon, areaPolygon: areaPolygon);
  if (minX.isFinite) {
    result = _clipPairedPolygonByLine(
      localPolygon: result.localPolygon,
      areaPolygon: result.areaPolygon,
      line: (Offset(minX, 0), Offset(minX, 1)),
      keepPositiveSide: false,
    );
  }
  if (maxX.isFinite) {
    result = _clipPairedPolygonByLine(
      localPolygon: result.localPolygon,
      areaPolygon: result.areaPolygon,
      line: (Offset(maxX, 0), Offset(maxX, 1)),
      keepPositiveSide: true,
    );
  }
  return result;
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
