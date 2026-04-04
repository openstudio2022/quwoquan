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
      progress: _resolveProgress(_localPagePoint.dx),
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
    final foldX = currentPose.leadingEdgeX;
    final foldInset = currentPose.cylinderRadius * 0.42;
    final ridgeY = pageHeight * (0.24 + currentPose.lift * 0.2);
    if (corner == StPageFlipCorner.top) {
      return <Offset>[
        Offset.zero,
        Offset(foldX, 0),
        Offset((foldX + foldInset).clamp(0.0, pageWidth), ridgeY),
        Offset(foldX, pageHeight),
        Offset.zero,
      ];
    }
    return <Offset>[
      Offset.zero,
      Offset(foldX, 0),
      Offset((foldX + foldInset).clamp(0.0, pageWidth), pageHeight - ridgeY),
      Offset(foldX, pageHeight),
      Offset.zero,
    ];
  }

  /// 回翻叶片的裁剪多边形。
  ///
  /// 坐标系与前翻 [StPageFlipCalculation.getFlippingClipArea] 一致：
  /// 原点在页面左上角，x 向右，y 向下。
  /// [_buildSoftPageLayer] 会通过 [_localPolygonFromArea] 把这些点
  /// 相对于 [getActiveCorner] 做平移 + [getAngle] 旋转，
  /// 所以这里返回的是 **未变换的页内绝对坐标**。
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
    // 用 _reverseAngle 和 _reverseActiveCorner 推导出的折线，
    // 构造一个与前翻 getFlippingClipArea 等价的旋转矩形 + 交点多边形。
    // 简化方案：直接用 leadingEdgeX 作为折线 x，构造右侧矩形。
    final foldX = currentPose.leadingEdgeX;
    return <Offset>[
      Offset(foldX, 0),
      Offset(pageWidth, 0),
      Offset(pageWidth, pageHeight),
      Offset(foldX, pageHeight),
    ];
  }

  /// 动态铰链锚点：折线与页边的交点，随 [ReverseFlipPose.leadingEdgeX] 移动。
  ///
  /// 前翻时 [StPageFlipCalculation.getActiveCorner] 返回 `_rect.topLeft`（动态），
  /// 后翻对称地返回折线在页顶/底边的交点。
  /// [_buildSoftPageLayer] 用此点做 `Positioned` 定位 + `_localPolygonFromArea` 平移原点。
  @override
  Offset getActiveCorner() {
    final currentPose = _pose;
    if (currentPose == null) {
      return corner == StPageFlipCorner.top
          ? Offset(pageWidth, 0)
          : Offset(pageWidth, pageHeight);
    }
    return corner == StPageFlipCorner.top
        ? Offset(currentPose.leadingEdgeX, 0)
        : Offset(currentPose.leadingEdgeX, pageHeight);
  }

  /// 折线倾斜角，与前翻 [StPageFlipCalculation.getAngle] 对称。
  ///
  /// 前翻返回 `-_angle`（负值，页面顺时针折起）；
  /// 后翻返回正值，让 [Transform.rotate] 产生逆时针折起的视觉。
  /// 角度来自 `leadingEdgeX` 到页面右边缘的距离与页高的比值，
  /// 模拟前翻 `_calculateAngle` 中 `left / sqrt(top^2 + left^2)` 的逻辑。
  @override
  double getAngle() {
    final currentPose = _pose;
    if (currentPose == null) {
      return 0;
    }
    final foldX = currentPose.leadingEdgeX;
    // 折页「露出宽度」：从折线到页面右边缘
    final exposedWidth = pageWidth - foldX;
    if (exposedWidth <= 0) {
      return 0;
    }
    // 用与前翻 _calculateAngle 同构的公式：
    // 前翻: angle = 2 * acos(left / sqrt(top^2 + left^2))
    // 这里 left = exposedWidth, top = pageHeight/2（折线中点到角的距离）
    final halfHeight = pageHeight / 2;
    final hypotenuse = math.sqrt(
      exposedWidth * exposedWidth + halfHeight * halfHeight,
    );
    if (hypotenuse < 1) {
      return 0;
    }
    final rawAngle = 2 *
        math.acos(
          (exposedWidth / hypotenuse).clamp(-1.0, 1.0).toDouble(),
        );
    // 后翻角度为正值（与前翻的负值镜像），并按 corner 翻转符号
    return corner == StPageFlipCorner.top ? rawAngle : -rawAngle;
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

  double _resolveProgress(double localX) {
    return ((pageWidth - localX) / (pageWidth * 1.1))
        .clamp(0.0, 1.0)
        .toDouble();
  }
}
