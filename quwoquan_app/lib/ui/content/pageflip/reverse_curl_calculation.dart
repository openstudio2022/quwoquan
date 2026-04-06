import 'dart:math' as math;
import 'dart:ui';

import 'package:flutter/animation.dart';
import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/ui/content/pageflip/geometry.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

@immutable
class ReverseFlipPose {
  const ReverseFlipPose({
    required this.progress,
    required this.emergenceProgress,
    required this.cylinderProgress,
    required this.unrollProgress,
    required this.emergenceWidth,
    required this.cylinderCenterX,
    required this.cylinderRadius,
    required this.cylinderArcWidth,
    required this.unrollWidth,
    required this.coveredWidth,
    required this.leadingEdgeX,
    required this.lift,
    required this.cornerBiasY,
  });

  final double progress;
  final double emergenceProgress;
  final double cylinderProgress;
  final double unrollProgress;
  final double emergenceWidth;
  final double cylinderCenterX;
  final double cylinderRadius;
  final double cylinderArcWidth;
  final double unrollWidth;
  final double coveredWidth;
  final double leadingEdgeX;
  final double lift;
  final double cornerBiasY;
}

double resolveReverseFlipProgress({
  required double localX,
  required double pageWidth,
}) {
  return ((pageWidth - localX) / (pageWidth * 1.1)).clamp(0.0, 1.0).toDouble();
}

ReverseFlipPose resolveReverseFlipPose({
  required Offset localPagePoint,
  required Size pageSize,
  required double progress,
  required StPageFlipCorner corner,
}) {
  final settledProgress = progress.clamp(0.0, 1.0).toDouble();
  final settledX = localPagePoint.dx
      .clamp(-pageSize.width * 0.35, pageSize.width)
      .toDouble();
  final exposureFromDrag = (pageSize.width - settledX)
      .clamp(0.0, pageSize.width * 1.25)
      .toDouble();
  final emergenceProgress = Curves.easeOutCubic.transform(
    (settledProgress / 0.28).clamp(0.0, 1.0).toDouble(),
  );
  final cylinderProgress = Curves.easeInOutCubic.transform(
    ((settledProgress - 0.18) / 0.44).clamp(0.0, 1.0).toDouble(),
  );
  final unrollProgress = Curves.easeOutCubic.transform(
    ((settledProgress - 0.62) / 0.38).clamp(0.0, 1.0).toDouble(),
  );

  final emergenceWidth =
      (lerpDouble(
                pageSize.width * 0.035,
                math.max(pageSize.width * 0.18, exposureFromDrag),
                emergenceProgress,
              ) ??
              (pageSize.width * 0.12))
          .clamp(pageSize.width * 0.035, pageSize.width * 0.9)
          .toDouble();
  final cylinderRadius =
      (lerpDouble(
                pageSize.width * 0.026,
                pageSize.width * 0.12,
                cylinderProgress,
              ) ??
              (pageSize.width * 0.06))
          .clamp(pageSize.width * 0.02, pageSize.width * 0.14)
          .toDouble();
  final unrollWidth =
      (lerpDouble(0.0, emergenceWidth * 0.72, unrollProgress) ?? 0.0)
          .clamp(0.0, emergenceWidth * 0.8)
          .toDouble();
  final cylinderArcWidth = math.max(
    cylinderRadius * 1.8,
    emergenceWidth - unrollWidth,
  );
  final coveredWidth = (unrollWidth + cylinderArcWidth)
      .clamp(pageSize.width * 0.06, pageSize.width * 0.96)
      .toDouble();
  final leadingEdgeX = (pageSize.width - coveredWidth)
      .clamp(0.0, pageSize.width * 0.94)
      .toDouble();
  final cylinderCenterX = (pageSize.width - unrollWidth - cylinderRadius * 0.82)
      .clamp(leadingEdgeX, pageSize.width)
      .toDouble();
  final lift =
      (lerpDouble(
                lerpDouble(0.52, 0.3, cylinderProgress) ?? 0.38,
                0.12,
                unrollProgress,
              ) ??
              0.22)
          .clamp(0.08, 0.6)
          .toDouble();
  final cornerBiasY = corner == StPageFlipCorner.top ? -1.0 : 1.0;

  return ReverseFlipPose(
    progress: settledProgress,
    emergenceProgress: emergenceProgress,
    cylinderProgress: cylinderProgress,
    unrollProgress: unrollProgress,
    emergenceWidth: emergenceWidth,
    cylinderCenterX: cylinderCenterX,
    cylinderRadius: cylinderRadius,
    cylinderArcWidth: cylinderArcWidth,
    unrollWidth: unrollWidth,
    coveredWidth: coveredWidth,
    leadingEdgeX: leadingEdgeX,
    lift: lift,
    cornerBiasY: cornerBiasY,
  );
}

class ReverseCurlCalculation extends StPageFlipCalculation {
  ReverseCurlCalculation({
    required super.corner,
    required super.pageWidth,
    required super.pageHeight,
  }) : super(direction: StPageFlipDirection.back);

  ReverseFlipPose? _pose;
  Offset _localPagePoint = Offset.zero;

  ReverseFlipPose? get pose => _pose;

  void syncPose(ReverseFlipPose pose) {
    _pose = pose;
  }

  @override
  bool calc(Offset localPos) {
    _localPagePoint = Offset(
      localPos.dx.clamp(-pageWidth * 0.35, pageWidth).toDouble(),
      localPos.dy.clamp(0.0, pageHeight).toDouble(),
    );
    _pose ??= resolveReverseFlipPose(
      localPagePoint: _localPagePoint,
      pageSize: Size(pageWidth, pageHeight),
      progress: resolveReverseFlipProgress(
        localX: _localPagePoint.dx,
        pageWidth: pageWidth,
      ),
      corner: corner,
    );
    return true;
  }

  @override
  Offset getPosition() => _localPagePoint;

  @override
  double getFlippingProgress() => (_pose?.progress ?? 0.0) * 100;

  @override
  Offset getBottomPagePosition() => Offset.zero;

  @override
  List<Offset> getBottomClipArea() {
    final currentPose = _pose;
    if (currentPose == null) {
      return <Offset>[
        Offset.zero,
        Offset(pageWidth, 0),
        Offset(pageWidth, pageHeight),
        Offset.zero,
      ];
    }
    // 底页（旧页面）的可见区域：从展开边界到右边缘。
    // 随着回翻推进，展开边界向右移动，底页可见区域缩小。
    final expandedWidth = currentPose.coveredWidth.clamp(0.0, pageWidth);
    return <Offset>[
      Offset(expandedWidth, 0),
      Offset(pageWidth, 0),
      Offset(pageWidth, pageHeight),
      Offset(expandedWidth, pageHeight),
    ];
  }

  /// 回翻叶片的裁剪多边形。
  ///
  /// 回翻是前翻的逆向过程：页面从左边缘开始展开，向右铺开。
  /// 裁剪区域从 [0, 0] 到 [coveredWidth, pageHeight]，
  /// 随 progress 增大，coveredWidth 从 0 增大到 pageWidth。
  @override
  List<Offset> getFlippingClipArea() {
    final currentPose = _pose;
    if (currentPose == null) {
      return <Offset>[
        Offset.zero,
        Offset(pageWidth, 0),
        Offset(pageWidth, pageHeight),
        Offset(0, pageHeight),
      ];
    }
    // coveredWidth 表示已展开的宽度，从右边缘算起。
    // 回翻是从左边缘展开，所以裁剪区域是 [0, 0] 到 [coveredWidth, pageHeight]。
    final expandedWidth = currentPose.coveredWidth.clamp(0.0, pageWidth);
    return <Offset>[
      Offset.zero,
      Offset(expandedWidth, 0),
      Offset(expandedWidth, pageHeight),
      Offset(0, pageHeight),
    ];
  }

  /// 回翻锚点：固定在页面左上角或左下角。
  ///
  /// 回翻是从左边缘展开，锚点固定在左边缘，
  /// 让 [_buildSoftPageLayer] 的 Positioned 从页面左边缘开始定位。
  @override
  Offset getActiveCorner() {
    return corner == StPageFlipCorner.top
        ? Offset.zero
        : Offset(0, pageHeight);
  }

  /// 回翻角度：固定为 0（不旋转）。
  ///
  /// 回翻是前翻的逆向过程，低保真路径用裁剪区域从左向右扩大来表达展开，
  /// 不需要旋转。旋转只会让叶片偏离正确位置。
  @override
  double getAngle() {
    return 0;
  }

  @override
  Offset getShadowStartPoint() {
    final currentPose = _pose;
    if (currentPose == null) {
      return Offset(pageWidth, corner == StPageFlipCorner.top ? 0 : pageHeight);
    }
    final y = corner == StPageFlipCorner.top
        ? pageHeight * 0.18
        : pageHeight * 0.82;
    return Offset(currentPose.cylinderCenterX, y);
  }

  @override
  double getShadowAngle() {
    final currentPose = _pose;
    if (currentPose == null) {
      return math.pi * 0.92;
    }
    final settle = currentPose.unrollProgress;
    return lerpDouble(math.pi * 0.98, math.pi * 0.78, settle) ?? math.pi * 0.9;
  }

  Path buildBottomClipPath(Rect pageRect) {
    final area = getBottomClipArea();
    final path = Path()
      ..moveTo(pageRect.left + area.first.dx, pageRect.top + area.first.dy);
    for (final point in area.skip(1)) {
      path.lineTo(pageRect.left + point.dx, pageRect.top + point.dy);
    }
    path.close();
    return Path.combine(
      PathOperation.intersect,
      Path()..addRect(pageRect),
      path,
    );
  }

  void clearPose() {
    _pose = null;
  }
}
