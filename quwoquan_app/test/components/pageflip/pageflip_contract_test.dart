import 'dart:ui';

import 'package:flutter/gestures.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/pageflip/pageflip.dart';
import 'package:quwoquan_app/ui/content/pageflip/backward_render_frame_builder.dart';
import 'package:quwoquan_app/ui/content/pageflip/curl_mesh_builder.dart';
import 'package:quwoquan_app/ui/content/pageflip/geometry.dart';
import 'package:quwoquan_app/ui/content/pageflip/render_frame.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

void main() {
  group('Pageflip', () {
    test(
      'single-page role resolver maps turning and covered pages by direction',
      () {
        const resolver = PageflipSinglePageRoleResolver();

        final forward = resolver.resolve(
          mode: PageflipMode.single,
          direction: PageflipDirection.forward,
          currentPageIndex: 2,
          pageCount: 5,
        );
        final backward = resolver.resolve(
          mode: PageflipMode.single,
          direction: PageflipDirection.back,
          currentPageIndex: 2,
          pageCount: 5,
        );

        expect(forward.underlayPageIndex, 3);
        expect(backward.underlayPageIndex, 2);
        expect(forward.turningPageIndex, 2);
        expect(backward.turningPageIndex, 1);
        expect(forward.coveredPageIndex, 2);
        expect(backward.coveredPageIndex, 2);
      },
    );

    test('forward render frame matches long-form canonical angle', () {
      final engine = PageflipEngine(pageCount: 5, initialPage: 2);
      engine.updateViewport(
        stageSize: const Size(900, 1200),
        pageSize: const Size(420, 584),
      );

      final layout = engine.buildScene(const Size(900, 1200))!.layout;
      final pageRect = layout.resolvePageRect(isRightPage: true);
      expect(
        engine.start(Offset(pageRect.right - 18, pageRect.bottom - 18)),
        isTrue,
      );
      engine.fold(Offset(pageRect.center.dx + 48, pageRect.center.dy));

      final scene = engine.buildScene(const Size(900, 1200));
      expect(scene, isNotNull);
      final renderFrame = scene!.renderFrame;
      expect(renderFrame, isNotNull);
      expect(renderFrame!.direction, PageflipDirection.forward);

      final canonical = StPageFlipCalculation(
        direction: StPageFlipDirection.forward,
        corner: renderFrame.canonicalFrame.corner,
        pageWidth: 420,
        pageHeight: 584,
      );
      expect(canonical.calc(renderFrame.canonicalFrame.localPagePoint), isTrue);
      expect(renderFrame.angle, closeTo(canonical.getAngle(), 1e-9));
      expect(
        renderFrame.canonicalFrame.timeline.diagonalExtent,
        lessThanOrEqualTo(420 * 0.078),
      );
      expect(
        renderFrame.canonicalFrame.timeline.sheetShift.abs(),
        lessThanOrEqualTo(420 * 0.02),
      );
      expect(
        renderFrame.canonicalFrame.timeline.leadingRadius,
        greaterThan(renderFrame.canonicalFrame.timeline.trailingRadius),
      );
      expect(
        renderFrame.canonicalFrame.timeline.heightLiftBias,
        lessThan(0.08),
      );
      expect(renderFrame.canonicalFrame.flippingClipArea, isNotEmpty);
      expect(renderFrame.canonicalFrame.bottomClipArea, isNotEmpty);
      expect(
        renderFrame.canonicalFrame.bottomClipArea.any(
          (point) => point.dx >= 420 - 0.001,
        ),
        isTrue,
      );
    });

    test('reverse render frame uses shared backward replay contract', () {
      final engine = PageflipEngine(pageCount: 5, initialPage: 2);
      engine.updateViewport(
        stageSize: const Size(900, 1200),
        pageSize: const Size(420, 584),
      );

      final layout = engine.buildScene(const Size(900, 1200))!.layout;
      final y = layout.bounds.top + (layout.bounds.height / 2);
      expect(engine.start(Offset(layout.bounds.left + 12, y)), isTrue);
      engine.fold(Offset(layout.bounds.left + 42, y));

      final scene = engine.buildScene(const Size(900, 1200));
      expect(scene, isNotNull);
      final renderFrame = scene!.renderFrame;
      expect(renderFrame, isNotNull);
      expect(renderFrame!.direction, PageflipDirection.back);
      expect(renderFrame.canonicalFrame.reversePose, isNull);
      // backwardLeafFrame is retained for diagnostics/timeline use only and is
      // no longer the source of geometry. Keep the existence check so we know
      // the timeline pipeline still runs.
      expect(renderFrame.canonicalFrame.backwardLeafFrame, isNotNull);
      expect(scene.turningPageIndex, 1);
      expect(scene.underlayPageIndex, 2);
      expect(scene.coveredPageIndex, 2);
      expect(scene.turningPageIndex, isNot(scene.underlayPageIndex));
      // Backward 主线统一：polygon 来自前翻 StPageFlipCalculation 的镜像输出，
      // 形状随手势从 3 顶点（最初的小三角）到 4/5 顶点（含 page 上侧/底侧
      // 交点）变化。这里只断言 polygon 至少形成一个有效面，并且 spine 一侧
      // 的 anchor 锁在 x=0（镜像后从前翻 W → 0）。
      expect(
        renderFrame.canonicalFrame.flippingClipArea.length,
        greaterThanOrEqualTo(3),
      );
      expect(
        renderFrame.canonicalFrame.bottomClipArea.length,
        greaterThanOrEqualTo(3),
      );
      // flippingAnchor 来自前翻 _rect.topLeft 的镜像 → 旋转后的页面平移基准
      // 点（一般会落到 spine 之外，是用来配合 polygon 渲染的位置）。这里
      // 只断言 bottomAnchor 仍锚定在 spine 原点，并且角度非零。
      expect(renderFrame.canonicalFrame.bottomAnchor, Offset.zero);
      expect(renderFrame.canonicalFrame.angle.abs(), greaterThan(0.0));
      final replayLocalPoint = resolveBackwardReplayLocalPagePoint(
        localPagePoint: renderFrame.canonicalFrame.localPagePoint,
        pageSize: const Size(420, 584),
      );
      expect(
        renderFrame.canonicalFrame.timeline.curlAngleBand,
        resolveForwardCurlAngleBand(
          localPagePoint: replayLocalPoint,
          pageSize: const Size(420, 584),
          corner: renderFrame.canonicalFrame.corner,
        ),
      );
    });

    test('backward dynamic render frame mirrors forward geometry contract', () {
      const pageSize = Size(420, 584);
      const localPagePoint = Offset(-96, 496);
      final replayLocalPoint = resolveBackwardReplayLocalPagePoint(
        localPagePoint: localPagePoint,
        pageSize: pageSize,
      );
      final forwardCalculation = StPageFlipCalculation(
        direction: StPageFlipDirection.forward,
        corner: StPageFlipCorner.bottom,
        pageWidth: pageSize.width,
        pageHeight: pageSize.height,
      );
      expect(replayLocalPoint.dx, closeTo(324, 0.001));
      expect(forwardCalculation.calc(replayLocalPoint), isTrue);

      final frame = buildBackwardDynamicRenderFrame(
        BackwardRenderFrameData(
          localPagePoint: localPagePoint,
          progress: 0.42,
          orientation: StPageFlipOrientation.portrait,
          corner: StPageFlipCorner.bottom,
          pageSize: pageSize,
          flippingClipArea: const <Offset>[],
          bottomClipArea: const <Offset>[],
          flippingAnchor: Offset.zero,
          bottomAnchor: Offset.zero,
          angle: 0,
          maxShadowOpacity: 0.2,
        ),
      );

      expect(frame.direction, StPageFlipDirection.back);
      expect(frame.renderDirection, StPageFlipDirection.back);
      expect(
        frame.flippingClipArea,
        _mirroredPolygon(
          forwardCalculation.getFlippingClipArea(),
          pageSize.width,
        ),
      );
      expect(
        frame.bottomClipArea,
        _mirroredPolygon(
          forwardCalculation.getBottomClipArea(),
          pageSize.width,
        ),
      );
      expect(frame.flippingAnchor, Offset.zero);
      expect(frame.bottomAnchor, Offset.zero);
      expect(frame.angle, closeTo(-forwardCalculation.getAngle(), 1e-9));
      final forwardFoldGeometry = forwardCalculation.getForwardFoldGeometry();
      expect(forwardFoldGeometry, isNotNull);
      final projectedFrame = frame.backwardProjectedFrame;
      expect(projectedFrame, isNotNull);
      expect(projectedFrame!.previousBackPolygon, frame.flippingClipArea);
      expect(
        projectedFrame.foldLine,
        _mirroredLine(forwardFoldGeometry!.foldLine, pageSize.width),
      );
      expect(projectedFrame.foldLineSource, 'forwardRealGeometryMirrored');
      expect(projectedFrame.edgeLineSource, 'reflectedOriginalRightEdge');
      expect(projectedFrame.previousBackVertexCount, greaterThanOrEqualTo(3));
      expect(
        _linesAreParallel(
          projectedFrame.foldLine,
          projectedFrame.projectedRightEdgeLine,
        ),
        isFalse,
      );
      expect(
        projectedFrame.currentResidualPolygon.length,
        greaterThanOrEqualTo(3),
      );
    });

    test('backward mesh keeps spine and seam vertically aligned', () {
      final engine = PageflipEngine(pageCount: 5, initialPage: 2);
      engine.updateViewport(
        stageSize: const Size(900, 1200),
        pageSize: const Size(420, 584),
      );

      final layout = engine.buildScene(const Size(900, 1200))!.layout;
      final pageRect = layout.resolvePageRect(isRightPage: true);
      final startPoint = Offset(pageRect.left + pageRect.width * 0.18, 600);
      expect(engine.start(startPoint), isTrue);
      engine.fold(Offset(startPoint.dx + 120, startPoint.dy - 36));

      final scene = engine.buildScene(const Size(900, 1200));
      expect(scene, isNotNull);
      final renderFrame = scene!.renderFrame;
      expect(renderFrame, isNotNull);
      expect(renderFrame!.direction, PageflipDirection.back);

      const builder = ArticlePageCurlMeshBuilder();
      final meshFrame = builder.build(
        pageRect: scene.pageRect,
        pageSize: scene.pageSize,
        dragPoint: renderFrame.canonicalFrame.localPagePoint,
        progress: renderFrame.progress,
        direction: StPageFlipDirection.back,
        corner: renderFrame.canonicalFrame.corner,
        renderFrame: renderFrame.canonicalFrame,
        deriveBottomClipPathFromMesh: true,
      );

      expect(meshFrame.alignmentDiagnostics, isNotNull);
      expect(
        meshFrame.alignmentDiagnostics!.spineTopX,
        closeTo(scene.pageRect.left, 0.5),
      );
      expect(
        meshFrame.alignmentDiagnostics!.spineBottomX,
        closeTo(scene.pageRect.left, 0.5),
      );
      expect(
        meshFrame.alignmentDiagnostics!.spineDelta,
        lessThanOrEqualTo(0.01),
      );
      expect(
        meshFrame.alignmentDiagnostics!.seamDelta,
        lessThanOrEqualTo(0.01),
      );
      expect(meshFrame.frontDiagnostics, isNotNull);
      expect(meshFrame.backDiagnostics, isNotNull);
      expect(meshFrame.frontDiagnostics!.hasOverflow, isFalse);
      expect(meshFrame.backDiagnostics!.hasOverflow, isFalse);
    });

    test('backward seam moves monotonically from spine toward page edge', () {
      final engine = PageflipEngine(pageCount: 5, initialPage: 2);
      engine.updateViewport(
        stageSize: const Size(900, 1200),
        pageSize: const Size(420, 584),
      );

      final layout = engine.buildScene(const Size(900, 1200))!.layout;
      final pageRect = layout.resolvePageRect(isRightPage: true);
      final startPoint = Offset(pageRect.left + pageRect.width * 0.18, 600);
      expect(engine.start(startPoint), isTrue);

      const sampleMoves = <Offset>[
        Offset(42, -12),
        Offset(140, -24),
        Offset(248, -36),
      ];
      final seamTopXs = <double>[];
      final seamBottomXs = <double>[];
      const builder = ArticlePageCurlMeshBuilder();

      for (final move in sampleMoves) {
        engine.fold(Offset(startPoint.dx + move.dx, startPoint.dy + move.dy));
        final scene = engine.buildScene(const Size(900, 1200));
        expect(scene, isNotNull);
        final renderFrame = scene!.renderFrame;
        expect(renderFrame, isNotNull);
        final meshFrame = builder.build(
          pageRect: scene.pageRect,
          pageSize: scene.pageSize,
          dragPoint: renderFrame!.canonicalFrame.localPagePoint,
          progress: renderFrame.progress,
          direction: StPageFlipDirection.back,
          corner: renderFrame.canonicalFrame.corner,
          renderFrame: renderFrame.canonicalFrame,
          deriveBottomClipPathFromMesh: true,
        );
        expect(meshFrame.alignmentDiagnostics, isNotNull);
        seamTopXs.add(meshFrame.alignmentDiagnostics!.seamTopX);
        seamBottomXs.add(meshFrame.alignmentDiagnostics!.seamBottomX);
      }

      expect(seamTopXs, orderedEquals([...seamTopXs]..sort()));
      expect(seamBottomXs, orderedEquals([...seamBottomXs]..sort()));
      expect(seamTopXs.first, greaterThanOrEqualTo(pageRect.left));
      expect(seamTopXs.last, lessThanOrEqualTo(pageRect.right + 0.5));
      expect(seamBottomXs.first, greaterThanOrEqualTo(pageRect.left));
      expect(seamBottomXs.last, lessThanOrEqualTo(pageRect.right + 0.5));
    });

    test('backward stopMove commits to previous page', () {
      final engine = PageflipEngine(pageCount: 5, initialPage: 2);
      engine.updateViewport(
        stageSize: const Size(900, 1200),
        pageSize: const Size(420, 584),
      );

      final layout = engine.buildScene(const Size(900, 1200))!.layout;
      final y = layout.bounds.top + (layout.bounds.height / 2);
      expect(engine.start(Offset(layout.bounds.left + 12, y)), isTrue);
      engine.fold(Offset(layout.bounds.left + 8, y));

      final plan = engine.stopMove(
        Velocity(pixelsPerSecond: const Offset(-480, 0)),
      );

      expect(plan.commitsTurn, isTrue);
      expect(plan.direction, PageflipDirection.back);
      expect(engine.currentPageIndex, 1);
    });

    test('single-page backward can start from the visible page left half', () {
      final engine = PageflipEngine(pageCount: 5, initialPage: 3);
      engine.updateViewport(
        stageSize: const Size(900, 1200),
        pageSize: const Size(420, 584),
      );

      final layout = engine.buildScene(const Size(900, 1200))!.layout;
      final pageRect = layout.resolvePageRect(isRightPage: true);
      final startPoint = Offset(
        pageRect.left + pageRect.width * 0.18,
        pageRect.bottom - 24,
      );
      expect(engine.start(startPoint), isTrue);
      engine.fold(Offset(startPoint.dx + 120, startPoint.dy - 36));

      final scene = engine.buildScene(const Size(900, 1200));
      expect(scene, isNotNull);
      expect(scene!.direction, PageflipDirection.back);
      expect(scene.turningPageIndex, 2);
      expect(scene.underlayPageIndex, 3);
      expect(scene.coveredPageIndex, 3);

      final plan = engine.stopMove(
        const Velocity(pixelsPerSecond: Offset(420, 0)),
      );
      expect(plan.commitsTurn, isTrue);
      expect(plan.direction, PageflipDirection.back);
      expect(engine.currentPageIndex, 2);
    });

    test('scene buildBottomClipPath returns full page rect', () {
      const layoutResolver = PageflipLayoutResolver();
      final layout = layoutResolver.resolve(
        viewportSize: const Size(900, 1200),
        pageWidth: 420,
        pageHeight: 584,
        mode: PageflipMode.single,
      );
      const pageRect = Rect.fromLTWH(240, 308, 420, 584);
      final scene = PageflipScene(
        stageSize: const Size(900, 1200),
        pageRect: pageRect,
        pageSize: const Size(420, 584),
        layout: layout,
        state: const PageflipState(
          mode: PageflipMode.single,
          currentPageIndex: 2,
        ),
      );

      final clipPath = scene.buildBottomClipPath();
      expect(clipPath.getBounds().width, equals(pageRect.width));
      expect(clipPath.getBounds().height, equals(pageRect.height));
    });
  });
}

Offset _mirrorX(Offset point, double width) =>
    Offset(width - point.dx, point.dy);

List<Offset> _mirroredPolygon(List<Offset> polygon, double width) {
  return polygon.map((point) => _mirrorX(point, width)).toList(growable: false);
}

(Offset, Offset) _mirroredLine((Offset, Offset) line, double width) {
  return (_mirrorX(line.$1, width), _mirrorX(line.$2, width));
}

bool _linesAreParallel((Offset, Offset) a, (Offset, Offset) b) {
  final ax = a.$2.dx - a.$1.dx;
  final ay = a.$2.dy - a.$1.dy;
  final bx = b.$2.dx - b.$1.dx;
  final by = b.$2.dy - b.$1.dy;
  return (ax * by - ay * bx).abs() < 0.01;
}
