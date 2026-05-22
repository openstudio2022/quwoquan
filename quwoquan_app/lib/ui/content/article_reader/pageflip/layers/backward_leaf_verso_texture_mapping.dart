import 'package:flutter/widgets.dart';

const String backwardVersoTextureMappingStrategy =
    'semanticBackSnapshotUvLocalClamped';

Offset backwardVersoTexturePoint({
  required Size pageSize,
  required Offset localPoint,
}) {
  if (pageSize.isEmpty) {
    return localPoint;
  }
  return Offset(
    localPoint.dx.clamp(0.0, pageSize.width).toDouble(),
    localPoint.dy.clamp(0.0, pageSize.height).toDouble(),
  );
}
