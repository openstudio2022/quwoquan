import 'package:flutter/widgets.dart';

String articleDiagnosticOffsetSignature(Offset? offset) {
  if (offset == null) {
    return 'none';
  }
  return [offset.dx.toStringAsFixed(1), offset.dy.toStringAsFixed(1)].join(',');
}

String articleDiagnosticRectSignature(Rect? rect) {
  if (rect == null) {
    return 'none';
  }
  return [
    rect.left.toStringAsFixed(1),
    rect.top.toStringAsFixed(1),
    rect.right.toStringAsFixed(1),
    rect.bottom.toStringAsFixed(1),
  ].join(',');
}

String articleDiagnosticPolygonSignature(List<Offset> polygon) {
  if (polygon.isEmpty) {
    return 'none';
  }
  return polygon.map(articleDiagnosticOffsetSignature).join(';');
}

double articleDiagnosticPolygonArea(List<Offset>? polygon) {
  if (polygon == null || polygon.length < 3) {
    return 0;
  }
  var twiceArea = 0.0;
  for (var i = 0; i < polygon.length; i += 1) {
    final current = polygon[i];
    final next = polygon[(i + 1) % polygon.length];
    twiceArea += current.dx * next.dy - next.dx * current.dy;
  }
  return twiceArea.abs() / 2;
}
