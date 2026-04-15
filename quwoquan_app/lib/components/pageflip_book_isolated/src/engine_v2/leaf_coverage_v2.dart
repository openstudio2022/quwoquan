import 'dart:ui';

import 'package:flutter/foundation.dart';

@immutable
class LeafRangeV2 {
  const LeafRangeV2(this.start, this.end);

  final double start;
  final double end;
}

@immutable
class LeafCoverageV2 {
  const LeafCoverageV2({
    required this.leafSilhouettePath,
    required this.leafClipPath,
    required this.bottomClipPath,
    required this.leafBounds,
  });

  final Path leafSilhouettePath;
  final Path leafClipPath;
  final Path bottomClipPath;
  final Rect leafBounds;
}
