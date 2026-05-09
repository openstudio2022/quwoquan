import 'dart:ui' as ui;

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/ui/content/pageflip/book_layout.dart';
import 'package:quwoquan_app/ui/content/pageflip/controller.dart';
import 'package:quwoquan_app/ui/content/pageflip/curl_light_model.dart';
import 'package:quwoquan_app/ui/content/pageflip/curl_mesh_builder.dart';
import 'package:quwoquan_app/ui/content/pageflip/geometry.dart';
import 'package:quwoquan_app/ui/content/pageflip/page_surface_snapshot.dart';
import 'package:quwoquan_app/ui/content/pageflip/render_frame.dart';
import 'package:quwoquan_app/ui/content/pageflip/reverse_curl_calculation.dart';
import 'package:quwoquan_app/ui/content/pageflip/spread_model.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

void main() {
  test('BookLayout 在窄视口使用单页居中布局', () {
    final layout = computeStPageFlipLayout(
      viewportSize: const Size(430, 900),
      pageWidth: 398,
      pageHeight: 553,
      usePortrait: true,
    );

    expect(layout.orientation, StPageFlipOrientation.portrait);
    expect(layout.bounds.width, closeTo(796, 0.001));
    expect(layout.bounds.left + layout.bounds.pageWidth, closeTo(16, 0.001));
  });

  test('BookLayout 在宽视口保留对开 spread', () {
    final layout = computeStPageFlipLayout(
      viewportSize: const Size(1400, 900),
      pageWidth: 560,
      pageHeight: 778,
      usePortrait: true,
    );

    expect(layout.orientation, StPageFlipOrientation.landscape);
    expect(layout.bounds.left, closeTo(140, 0.001));
    expect(
      resolveBookPageRect(layout, isRightPage: false).left,
      closeTo(140, 0.001),
    );
    expect(
      resolveBookPageRect(layout, isRightPage: true).left,
      closeTo(700, 0.001),
    );
  });

  test('BookLayout 支持显式覆盖 single 与 spread 语义布局', () {
    final forcedSingle = computeStPageFlipLayout(
      viewportSize: const Size(1400, 900),
      pageWidth: 1240,
      pageHeight: 778,
      usePortrait: false,
      orientationOverride: StPageFlipOrientation.portrait,
    );
    final forcedSpread = computeStPageFlipLayout(
      viewportSize: const Size(430, 900),
      pageWidth: 191,
      pageHeight: 553,
      usePortrait: true,
      orientationOverride: StPageFlipOrientation.landscape,
    );

    expect(forcedSingle.orientation, StPageFlipOrientation.portrait);
    expect(
      resolveBookPageRect(forcedSingle, isRightPage: true).center.dx,
      closeTo(700, 0.001),
    );
    expect(forcedSpread.orientation, StPageFlipOrientation.landscape);
    expect(
      resolveBookPageRect(forcedSpread, isRightPage: false).left,
      lessThan(resolveBookPageRect(forcedSpread, isRightPage: true).left),
    );
  });

  test('SpreadModel 复刻 cover 与尾页单页 spread 语义', () {
    final model = StPageFlipSpreadModel(pageCount: 4, showCover: true);
    final spreads = model.spreadsFor(StPageFlipOrientation.landscape);

    expect(spreads.map((spread) => spread.pages), <List<int>>[
      <int>[0],
      <int>[1, 2],
      <int>[3],
    ]);
    expect(model.densityForPage(0), StPageFlipDensity.hard);
    expect(model.densityForPage(3), StPageFlipDensity.hard);
    expect(
      model
          .visibleSpreadForIndex(0, StPageFlipOrientation.landscape)
          .rightPageIndex,
      0,
    );
    expect(
      model
          .visibleSpreadForIndex(2, StPageFlipOrientation.landscape)
          .leftPageIndex,
      3,
    );
  });

  test('FlipController 在单页模式下完成前翻', () {
    final controller = StPageFlipController(
      spreadModel: StPageFlipSpreadModel(pageCount: 3),
      layout: computeStPageFlipLayout(
        viewportSize: const Size(430, 900),
        pageWidth: 398,
        pageHeight: 553,
        usePortrait: true,
      ),
      initialPage: 0,
    );

    final plan = controller.flipNext(StPageFlipCorner.bottom);
    expect(plan, isNotNull);

    controller.applyAnimationFrame(plan!.frames.last);
    controller.completeAnimation(plan);

    expect(controller.currentPageIndex, 1);
    expect(controller.scene.visibleSpread.rightPageIndex, 1);
  });

  test('FlipController 在对开模式下前翻到下一 spread 的首页', () {
    final controller = StPageFlipController(
      spreadModel: StPageFlipSpreadModel(pageCount: 5),
      layout: computeStPageFlipLayout(
        viewportSize: const Size(1400, 900),
        pageWidth: 560,
        pageHeight: 778,
        usePortrait: true,
      ),
      initialPage: 0,
    );

    expect(controller.scene.visibleSpread.leftPageIndex, 0);
    expect(controller.scene.visibleSpread.rightPageIndex, 1);

    final plan = controller.flipNext(StPageFlipCorner.bottom);
    expect(plan, isNotNull);

    controller.applyAnimationFrame(plan!.frames.last);
    controller.completeAnimation(plan);

    expect(controller.currentPageIndex, 2);
    expect(controller.scene.visibleSpread.leftPageIndex, 2);
    expect(controller.scene.visibleSpread.rightPageIndex, 3);
  });

  test('FlipController 在单页模式下完成回翻', () {
    final controller = StPageFlipController(
      spreadModel: StPageFlipSpreadModel(pageCount: 3),
      layout: computeStPageFlipLayout(
        viewportSize: const Size(430, 900),
        pageWidth: 398,
        pageHeight: 553,
        usePortrait: true,
      ),
      initialPage: 1,
    );

    final plan = controller.flipPrev(StPageFlipCorner.bottom);
    expect(plan, isNotNull);

    controller.applyAnimationFrame(plan!.frames.last);
    controller.completeAnimation(plan);

    expect(controller.currentPageIndex, 0);
    expect(controller.scene.visibleSpread.rightPageIndex, 0);
  });

  test('FlipController 会同步 render frame 读模型', () {
    final controller = StPageFlipController(
      spreadModel: StPageFlipSpreadModel(pageCount: 3),
      layout: computeStPageFlipLayout(
        viewportSize: const Size(430, 900),
        pageWidth: 398,
        pageHeight: 553,
        usePortrait: true,
      ),
      initialPage: 0,
    );

    expect(controller.start(const Offset(400, 650)), isTrue);
    controller.fold(const Offset(300, 620));

    final frame = controller.scene.renderFrame;
    expect(frame, isNotNull);
    expect(frame, isA<StPageFlipRenderFrame>());
    expect(frame!.direction, StPageFlipDirection.forward);
    expect(frame.renderDirection, StPageFlipDirection.forward);
    expect(frame.timeline.rollProgress, inInclusiveRange(0.0, 1.0));
    expect(frame.flippingClipArea, isNotEmpty);
    expect(frame.bottomClipArea, isNotEmpty);
  });

  test('FlipController 的前翻 renderFrame 锁定长文前翻金标准契约', () {
    final controller = StPageFlipController(
      spreadModel: StPageFlipSpreadModel(pageCount: 4),
      layout: computeStPageFlipLayout(
        viewportSize: const Size(430, 900),
        pageWidth: 398,
        pageHeight: 553,
        usePortrait: true,
      ),
      initialPage: 1,
    );

    expect(controller.start(const Offset(410, 650)), isTrue);
    controller.fold(const Offset(256, 528));

    final scene = controller.scene;
    final renderFrame = scene.renderFrame;
    expect(renderFrame, isNotNull);
    expect(renderFrame!.direction, StPageFlipDirection.forward);
    expect(renderFrame.renderDirection, StPageFlipDirection.forward);
    expect(renderFrame.reversePose, isNull);
    expect(renderFrame.backwardLeafFrame, isNull);
    expect(renderFrame.timeline.mirrored, isFalse);
    expect(scene.flippingPageIndex, 1);
    expect(scene.bottomPageIndex, 2);

    final binding = resolveArticlePageTextureBinding(
      direction: scene.direction,
      flippingPageIndex: scene.flippingPageIndex,
      bottomPageIndex: scene.bottomPageIndex,
      currentPageIndex: scene.currentPageIndex,
    );
    expect(binding, isNotNull);
    expect(binding!.rectoPageIndex, 1);
    expect(binding.versoPageIndex, 1);
    expect(binding.bottomPageIndex, 2);

    final meshFrame = const ArticlePageCurlMeshBuilder().build(
      pageRect: const Rect.fromLTWH(16, 64, 398, 553),
      pageSize: Size(398, 553),
      // 故意传入与 renderFrame 不一致的参数，锁住 mesh 必须消费 renderFrame。
      dragPoint: Offset(12, 40),
      progress: 0.92,
      direction: StPageFlipDirection.back,
      corner: StPageFlipCorner.top,
      renderFrame: renderFrame,
    );

    expect(meshFrame.frontSurface, isNotNull);
    expect(meshFrame.backSurface, isNotNull);
    const pageRect = Rect.fromLTWH(16, 64, 398, 553);
    final bottomBounds = meshFrame.bottomClipPath.getBounds();
    expect(bottomBounds.left, greaterThanOrEqualTo(pageRect.left));
    expect(bottomBounds.top, greaterThanOrEqualTo(pageRect.top));
    expect(bottomBounds.right, lessThanOrEqualTo(pageRect.right));
    expect(bottomBounds.bottom, lessThanOrEqualTo(pageRect.bottom));
    expect(
      meshFrame.rollProgress,
      closeTo(renderFrame.timeline.rollProgress, 0.0001),
    );
    expect(meshFrame.cylinderProgress, 0);
    expect(meshFrame.unfoldProgress, 0);
  });

  test('FlipController 的 portrait 回翻 render frame 会切到单一 dynamic 主线', () {
    final controller = StPageFlipController(
      spreadModel: StPageFlipSpreadModel(pageCount: 3),
      layout: computeStPageFlipLayout(
        viewportSize: const Size(430, 900),
        pageWidth: 398,
        pageHeight: 553,
        usePortrait: true,
      ),
      initialPage: 1,
    );

    expect(controller.start(const Offset(18, 650)), isTrue);
    controller.applyAnimationFrame(const Offset(120, 510));

    final frame = controller.scene.renderFrame;
    expect(frame, isNotNull);
    expect(frame!.direction, StPageFlipDirection.back);
    expect(frame.renderDirection, StPageFlipDirection.back);
    expect(frame.reversePose, isNull);
    expect(frame.timeline.rollProgress, greaterThan(0));
    expect(frame.timeline.cylinderProgress, equals(0));
    expect(frame.timeline.unfoldProgress, equals(0));
    expect(frame.timeline.mirrored, isTrue);
    expect(frame.backwardLeafFrame, isNotNull);
  });

  test('FlipController 的 portrait 回翻固定走 shared replay timeline', () {
    final controller = StPageFlipController(
      spreadModel: StPageFlipSpreadModel(pageCount: 3),
      layout: computeStPageFlipLayout(
        viewportSize: const Size(430, 900),
        pageWidth: 398,
        pageHeight: 553,
        usePortrait: true,
      ),
      initialPage: 1,
    );

    expect(controller.start(const Offset(18, 650)), isTrue);
    controller.applyAnimationFrame(const Offset(120, 510));

    final frame = controller.scene.renderFrame;
    expect(frame, isNotNull);
    expect(controller.scene.calculation, isA<StPageFlipCalculation>());
    expect(controller.scene.calculation, isNot(isA<ReverseCurlCalculation>()));
    expect(frame!.direction, StPageFlipDirection.back);
    expect(frame.renderDirection, StPageFlipDirection.back);
    expect(frame.reversePose, isNull);
    expect(frame.timeline.mirrored, isTrue);
    expect(frame.backwardLeafFrame, isNotNull);
    expect(frame.flippingClipArea, isNotEmpty);
    expect(frame.bottomClipArea, isNotEmpty);
  });

  test('CurlMeshBuilder 在 portrait 回翻时消费 dynamic replay timeline', () {
    final controller = StPageFlipController(
      spreadModel: StPageFlipSpreadModel(pageCount: 3),
      layout: computeStPageFlipLayout(
        viewportSize: const Size(430, 900),
        pageWidth: 398,
        pageHeight: 553,
        usePortrait: true,
      ),
      initialPage: 1,
    );

    expect(controller.start(const Offset(18, 650)), isTrue);
    controller.applyAnimationFrame(const Offset(120, 510));

    final renderFrame = controller.scene.renderFrame;
    expect(renderFrame, isNotNull);
    expect(renderFrame!.timeline.mirrored, isTrue);
    expect(renderFrame.backwardLeafFrame, isNotNull);

    final builder = ArticlePageCurlMeshBuilder();
    final meshFrame = builder.build(
      pageRect: const Rect.fromLTWH(16, 64, 398, 553),
      pageSize: const Size(398, 553),
      dragPoint: renderFrame.localPagePoint,
      progress: renderFrame.progress,
      direction: renderFrame.direction,
      corner: renderFrame.corner,
      renderFrame: renderFrame,
    );

    expect(meshFrame.frontSurface, isNotNull);
    expect(meshFrame.backSurface, isNotNull);
    expect(
      meshFrame.rollProgress,
      closeTo(renderFrame.timeline.rollProgress, 0.0001),
    );
    expect(meshFrame.cylinderProgress, equals(0));
    expect(meshFrame.unfoldProgress, equals(0));
  });

  test('CurlMeshBuilder 在回翻 dynamic renderFrame 下仍消费统一 timeline', () {
    final controller = StPageFlipController(
      spreadModel: StPageFlipSpreadModel(pageCount: 3),
      layout: computeStPageFlipLayout(
        viewportSize: const Size(430, 900),
        pageWidth: 398,
        pageHeight: 553,
        usePortrait: true,
      ),
      initialPage: 1,
    );

    expect(controller.start(const Offset(18, 650)), isTrue);
    controller.applyAnimationFrame(const Offset(120, 510));

    final renderFrame = controller.scene.renderFrame;
    expect(renderFrame, isNotNull);
    expect(renderFrame!.direction, StPageFlipDirection.back);
    expect(renderFrame.backwardLeafFrame, isNotNull);
    expect(renderFrame.reversePose, isNull);

    final builder = ArticlePageCurlMeshBuilder();
    final meshFrame = builder.build(
      pageRect: const Rect.fromLTWH(16, 64, 398, 553),
      pageSize: const Size(398, 553),
      dragPoint: renderFrame.localPagePoint,
      progress: renderFrame.progress,
      direction: renderFrame.direction,
      corner: renderFrame.corner,
      renderFrame: renderFrame,
    );

    expect(
      meshFrame.rollProgress,
      closeTo(renderFrame.timeline.rollProgress, 0.0001),
    );
    expect(meshFrame.cylinderProgress, equals(0));
    expect(meshFrame.unfoldProgress, equals(0));
  });

  test('FlipController 的前翻不会被 backward shared engine 污染', () {
    final controller = StPageFlipController(
      spreadModel: StPageFlipSpreadModel(pageCount: 3),
      layout: computeStPageFlipLayout(
        viewportSize: const Size(430, 900),
        pageWidth: 398,
        pageHeight: 553,
        usePortrait: true,
      ),
      initialPage: 0,
    );

    expect(controller.start(const Offset(400, 650)), isTrue);
    controller.fold(const Offset(300, 620));

    final frame = controller.scene.renderFrame;
    expect(frame, isNotNull);
    expect(controller.scene.calculation, isA<StPageFlipCalculation>());
    expect(controller.scene.calculation, isNot(isA<ReverseCurlCalculation>()));
    expect(frame!.direction, StPageFlipDirection.forward);
    expect(frame.renderDirection, StPageFlipDirection.forward);
    expect(frame.reversePose, isNull);

    final plan = controller.flipNext(StPageFlipCorner.bottom);
    expect(plan, isNotNull);
    expect(plan!.direction, StPageFlipDirection.forward);
    expect(plan.reversePoses, isNull);
  });

  test('FlipController 的前翻与回翻轨迹保持正确入场与出场边缘', () {
    final layout = computeStPageFlipLayout(
      viewportSize: const Size(430, 900),
      pageWidth: 398,
      pageHeight: 553,
      usePortrait: true,
    );
    final forwardController = StPageFlipController(
      spreadModel: StPageFlipSpreadModel(pageCount: 3),
      layout: layout,
      initialPage: 0,
    );
    final backwardController = StPageFlipController(
      spreadModel: StPageFlipSpreadModel(pageCount: 3),
      layout: layout,
      initialPage: 1,
    );

    final forwardPlan = forwardController.flipNext(StPageFlipCorner.bottom);
    final backwardPlan = backwardController.flipPrev(StPageFlipCorner.bottom);

    expect(forwardPlan, isNotNull);
    expect(backwardPlan, isNotNull);

    final centerX = layout.bounds.left + layout.bounds.width / 2;
    final rightPageRect = resolveBookPageRect(layout, isRightPage: true);
    final forwardStart = convertBookPointToViewport(
      forwardPlan!.frames.first,
      layout.bounds,
      direction: forwardPlan.direction,
    );
    final forwardEnd = convertBookPointToViewport(
      forwardPlan.frames.last,
      layout.bounds,
      direction: forwardPlan.direction,
    );
    final backwardStart = convertBookPointToViewport(
      backwardPlan!.frames.first,
      layout.bounds,
      direction: backwardPlan.direction,
    );
    final backwardEnd = convertBookPointToViewport(
      backwardPlan.frames.last,
      layout.bounds,
      direction: backwardPlan.direction,
    );

    expect(forwardStart.dx, greaterThan(centerX));
    expect(backwardStart.dx, greaterThanOrEqualTo(rightPageRect.left));
    expect(
      backwardStart.dx,
      lessThan(rightPageRect.left + (layout.bounds.pageWidth * 0.12)),
    );
    expect(forwardEnd.dx, lessThan(centerX));
    expect(backwardEnd.dx, greaterThan(centerX));
  });

  test('FlipController 的回翻自动轨迹会先在右侧卷出再推进', () {
    final controller = StPageFlipController(
      spreadModel: StPageFlipSpreadModel(pageCount: 3),
      layout: computeStPageFlipLayout(
        viewportSize: const Size(430, 900),
        pageWidth: 398,
        pageHeight: 553,
        usePortrait: true,
      ),
      initialPage: 1,
    );

    final plan = controller.flipPrev(StPageFlipCorner.bottom);
    expect(plan, isNotNull);

    final earlyFrame = plan!.frames[(plan.frames.length * 0.2).round()];
    final middleFrame = plan.frames[(plan.frames.length * 0.55).round()];
    final linearEarlyDx =
        plan.frames.first.dx +
        (plan.frames.last.dx - plan.frames.first.dx) * 0.2;
    // 回翻轨迹应先在右侧卷出（earlyFrame.dx 接近或大于线性插值），再推进
    expect(earlyFrame.dx, greaterThanOrEqualTo(linearEarlyDx - 1));
    expect(middleFrame.dx, lessThan(earlyFrame.dx));
  });

  test('ReverseCurlCalculation 会输出 emergence 到 unroll 的单调 pose', () {
    final calculation = ReverseCurlCalculation(
      corner: StPageFlipCorner.top,
      pageWidth: 398,
      pageHeight: 553,
    );
    final earlyPose = resolveReverseFlipPose(
      localPagePoint: const Offset(372, 92),
      pageSize: const Size(398, 553),
      progress: 0.14,
      corner: StPageFlipCorner.top,
    );
    final middlePose = resolveReverseFlipPose(
      localPagePoint: const Offset(286, 128),
      pageSize: const Size(398, 553),
      progress: 0.56,
      corner: StPageFlipCorner.top,
    );
    final latePose = resolveReverseFlipPose(
      localPagePoint: const Offset(188, 168),
      pageSize: const Size(398, 553),
      progress: 0.88,
      corner: StPageFlipCorner.top,
    );

    calculation.syncPose(middlePose);
    calculation.calc(const Offset(286, 128));

    expect(
      earlyPose.emergenceProgress,
      lessThanOrEqualTo(middlePose.emergenceProgress),
    );
    expect(earlyPose.cylinderProgress, lessThan(middlePose.cylinderProgress));
    expect(latePose.unrollProgress, greaterThan(middlePose.unrollProgress));
    expect(middlePose.leadingEdgeX, lessThan(earlyPose.leadingEdgeX));
    expect(calculation.getBottomClipArea().length, greaterThanOrEqualTo(4));

    final flipArea = calculation.getFlippingClipArea();
    // 新方案：回翻 clip area 从左边缘 [0] 到 coveredWidth，始终 4 点矩形。
    expect(flipArea.length, equals(4));
    // 左边缘从 0 开始
    expect(flipArea[0].dx, 0);
    // 右边缘是 coveredWidth
    expect(flipArea[1].dx, greaterThan(0));

    // 新方案：getActiveCorner 固定在左边缘
    final activeCorner = calculation.getActiveCorner();
    expect(activeCorner.dx, 0);
    expect(activeCorner.dy, 0); // corner == top

    // 新方案：getAngle 固定为 0（不旋转）
    expect(calculation.getAngle(), 0);
  });

  test('PageTextureBinding 会锁定前翻与回翻的叶片身份', () {
    final forwardBinding = resolveArticlePageTextureBinding(
      direction: StPageFlipDirection.forward,
      flippingPageIndex: 2,
      bottomPageIndex: 3,
      currentPageIndex: 2,
    );
    final backwardBinding = resolveArticlePageTextureBinding(
      direction: StPageFlipDirection.back,
      flippingPageIndex: 2,
      bottomPageIndex: 2,
      currentPageIndex: 3,
    );

    expect(forwardBinding, isNotNull);
    expect(forwardBinding!.rectoPageIndex, 2);
    expect(forwardBinding.versoPageIndex, 2);
    expect(forwardBinding.bottomPageIndex, 3);

    expect(backwardBinding, isNotNull);
    expect(backwardBinding!.rectoPageIndex, 2);
    expect(backwardBinding.versoPageIndex, 2);
    expect(backwardBinding.bottomPageIndex, 3);
  });

  test('PageTextureBinding 的前翻语义是当前页正面/当前页背面/下一页底页', () {
    final binding = resolveArticlePageTextureBinding(
      direction: StPageFlipDirection.forward,
      flippingPageIndex: 4,
      bottomPageIndex: 5,
      currentPageIndex: 4,
    );

    expect(binding, isNotNull);
    expect(binding!.rectoPageIndex, 4);
    expect(binding.versoPageIndex, 4);
    expect(binding.bottomPageIndex, 5);
    expect(binding.requiredPageIndices, equals(<int>{4, 5}));
  });

  test('BackwardPageSurfaceBinding 会区分 covered current 与 previous leaf', () {
    final binding = resolveArticleBackwardPageSurfaceBinding(
      direction: StPageFlipDirection.back,
      flippingPageIndex: 2,
      currentPageIndex: 3,
    );

    expect(binding, isNotNull);
    expect(binding!.coveredPageIndex, equals(3));
    expect(binding.leafPageIndex, equals(2));
    expect(binding.leafRectoPageIndex, equals(2));
    expect(binding.leafVersoPageIndex, equals(2));
    expect(binding.requiredPageIndices, equals(<int>{2, 3}));
  });

  test('BackwardLeafFrame 会从卷出推进到铺平', () {
    final early = resolveArticlePageBackwardLeafFrame(
      direction: StPageFlipDirection.back,
      progress: 0.08,
    );
    final middle = resolveArticlePageBackwardLeafFrame(
      direction: StPageFlipDirection.back,
      progress: 0.48,
    );
    final late = resolveArticlePageBackwardLeafFrame(
      direction: StPageFlipDirection.back,
      progress: 0.96,
    );

    expect(early, isNotNull);
    expect(middle, isNotNull);
    expect(late, isNotNull);
    expect(early!.phase, equals(ArticlePageBackwardLeafPhase.emerge));
    expect(middle!.phase, equals(ArticlePageBackwardLeafPhase.unroll));
    expect(late!.phase, equals(ArticlePageBackwardLeafPhase.settle));
    expect(
      middle.laidDownWidthNormalized,
      greaterThan(early.laidDownWidthNormalized),
    );
    expect(
      late.laidDownWidthNormalized,
      greaterThan(middle.laidDownWidthNormalized),
    );
    expect(
      middle.coveredWidthNormalized,
      greaterThan(early.coveredWidthNormalized),
    );
    expect(late.coveredWidthNormalized, closeTo(1.0, 0.08));
    expect(late.curlWidthNormalized, lessThan(middle.curlWidthNormalized));
    expect(middle.rectoRevealWidthNormalized, greaterThan(0));
    expect(early.seamXNormalized, lessThan(middle.seamXNormalized));
    expect(middle.seamXNormalized, lessThan(late.seamXNormalized));
    expect(early.versoRevealWidthNormalized, greaterThan(0));
    expect(middle.edgeBandWidthNormalized, greaterThan(0));
    expect(
      middle.totalRectoVisibleWidthNormalized,
      greaterThan(early.totalRectoVisibleWidthNormalized),
    );
    expect(
      early.currentRevealWidthNormalized,
      greaterThan(middle.currentRevealWidthNormalized),
    );
    expect(
      middle.currentRevealWidthNormalized,
      greaterThan(late.currentRevealWidthNormalized),
    );
    expect(
      middle.bottomRevealStartNormalized,
      closeTo(middle.seamXNormalized, 0.0001),
    );
  });

  test('Backward dynamic renderFrame 几何直接来自 calculation contract', () {
    final controller = StPageFlipController(
      spreadModel: StPageFlipSpreadModel(pageCount: 3),
      layout: computeStPageFlipLayout(
        viewportSize: const Size(430, 900),
        pageWidth: 398,
        pageHeight: 553,
        usePortrait: true,
      ),
      initialPage: 1,
    );

    expect(controller.start(const Offset(18, 650)), isTrue);
    controller.applyAnimationFrame(const Offset(120, 510));

    final frame = controller.scene.renderFrame;
    expect(frame, isNotNull);
    expect(frame!.direction, StPageFlipDirection.back);
    expect(frame.angle, isNot(equals(0)));
    expect(frame.shadow, isNotNull);
    expect(frame.shadow!.angle, isA<double>());
    expect(frame.shadow!.width, greaterThanOrEqualTo(0));
    expect(frame.backwardLeafFrame, isNotNull);
    expect(frame.backwardLeafFrame!.seamXNormalized, greaterThan(0));
    expect(frame.backwardLeafFrame!.versoRevealWidthNormalized, greaterThan(0));
    expect(
      frame.backwardLeafFrame!.bottomRevealStartNormalized,
      greaterThan(frame.backwardLeafFrame!.laidDownWidthNormalized),
    );
    // Backward 几何主线直接消费 BACK calculation。bottomAnchor 是 StPageFlip
    // 计算坐标中的底页位置，不再强行锁到旧镜像前翻原点。
    expect(frame.bottomAnchor.dx.isFinite, isTrue);
    expect(frame.bottomAnchor.dy, closeTo(0, 0.001));
    expect(frame.flippingClipArea.length, greaterThanOrEqualTo(3));
    expect(frame.bottomClipArea.length, greaterThanOrEqualTo(3));
    // 至少有一个 flipping 顶点在右页范围内，至少有一个在右边界附近，确认它
    // 表达的是镜像后的三角/四边形而非退化几何。
    expect(
      frame.flippingClipArea.any((p) => p.dx > 1.0 && p.dx < 397.0),
      isTrue,
    );
    expect(frame.bottomClipArea.any((p) => p.dx > 1.0 && p.dx < 397.0), isTrue);
  });

  test('Backward dynamic progress 会沿计划单调推进', () {
    final controller = StPageFlipController(
      spreadModel: StPageFlipSpreadModel(pageCount: 3),
      layout: computeStPageFlipLayout(
        viewportSize: const Size(430, 900),
        pageWidth: 398,
        pageHeight: 553,
        usePortrait: true,
      ),
      initialPage: 1,
    );

    final plan = controller.flipPrev(StPageFlipCorner.bottom);
    expect(plan, isNotNull);

    final earlyIndex = (plan!.frames.length * 0.2).round();
    final middleIndex = (plan.frames.length * 0.55).round();
    final lateIndex = (plan.frames.length * 0.9).round();

    controller.applyAnimationFrame(plan.frames[earlyIndex]);
    final earlyFrame = controller.scene.renderFrame;
    controller.applyAnimationFrame(plan.frames[middleIndex]);
    final middleFrame = controller.scene.renderFrame;
    controller.applyAnimationFrame(plan.frames[lateIndex]);
    final lateFrame = controller.scene.renderFrame;

    expect(earlyFrame, isNotNull);
    expect(middleFrame, isNotNull);
    expect(lateFrame, isNotNull);
    expect(earlyFrame!.progress, lessThan(middleFrame!.progress));
    expect(middleFrame.progress, lessThan(lateFrame!.progress));
    expect(earlyFrame.backwardLeafFrame, isNotNull);
    expect(middleFrame.backwardLeafFrame, isNotNull);
    expect(lateFrame.backwardLeafFrame, isNotNull);
    expect(
      earlyFrame.backwardLeafFrame!.laidDownWidthNormalized,
      lessThanOrEqualTo(middleFrame.backwardLeafFrame!.laidDownWidthNormalized),
    );
    expect(
      middleFrame.backwardLeafFrame!.laidDownWidthNormalized,
      lessThanOrEqualTo(lateFrame.backwardLeafFrame!.laidDownWidthNormalized),
    );
    expect(
      earlyFrame.backwardLeafFrame!.bottomRevealStartNormalized,
      lessThanOrEqualTo(
        middleFrame.backwardLeafFrame!.bottomRevealStartNormalized,
      ),
    );
    expect(
      middleFrame.backwardLeafFrame!.bottomRevealStartNormalized,
      lessThanOrEqualTo(
        lateFrame.backwardLeafFrame!.bottomRevealStartNormalized,
      ),
    );
    // 在新的纸折几何里 totalRectoVisibleWidth = covered * rectoCoverage，
    // rectoCoverage = max(2 - 1/covered, settleProgress) 严格遵循折纸物理：
    // covered ≤ 0.5 时 recto 仍未越过中线，total = 0；只有进入 unroll 后段
    // 才会涌现可见 recto。因此早/中帧不再保证 total = laidDown + rectoReveal，
    // 改为只校验 1) 单调性：middle 比 early 至少不缩小；2) total ≤ covered 且
    // ≤ bottomRevealStart（current 始终被 leaf 覆盖在 total 与 bottomReveal
    // 之间或更深），保证不会出现“正面提前盖过 current”这种翻折破绽。
    expect(
      middleFrame.backwardLeafFrame!.totalRectoVisibleWidthNormalized,
      greaterThanOrEqualTo(
        earlyFrame.backwardLeafFrame!.totalRectoVisibleWidthNormalized,
      ),
    );
    expect(
      middleFrame.backwardLeafFrame!.laidDownWidthNormalized,
      greaterThan(earlyFrame.backwardLeafFrame!.laidDownWidthNormalized),
    );
    expect(
      middleFrame.backwardLeafFrame!.rectoRevealWidthNormalized,
      greaterThan(0),
    );
    expect(
      earlyFrame.backwardLeafFrame!.totalRectoVisibleWidthNormalized,
      lessThanOrEqualTo(
        earlyFrame.backwardLeafFrame!.coveredWidthNormalized + 1e-6,
      ),
    );
    expect(
      middleFrame.backwardLeafFrame!.totalRectoVisibleWidthNormalized,
      lessThanOrEqualTo(
        middleFrame.backwardLeafFrame!.coveredWidthNormalized + 1e-6,
      ),
    );
    expect(
      earlyFrame.backwardLeafFrame!.bottomRevealStartNormalized -
          earlyFrame.backwardLeafFrame!.totalRectoVisibleWidthNormalized,
      greaterThanOrEqualTo(0),
    );
    expect(
      middleFrame.backwardLeafFrame!.bottomRevealStartNormalized -
          middleFrame.backwardLeafFrame!.totalRectoVisibleWidthNormalized,
      greaterThanOrEqualTo(0),
    );
    expect(
      earlyFrame.backwardLeafFrame!.laidDownWidthNormalized +
          earlyFrame.backwardLeafFrame!.curlWidthNormalized,
      closeTo(earlyFrame.backwardLeafFrame!.coveredWidthNormalized, 0.0001),
    );
    expect(
      middleFrame.backwardLeafFrame!.laidDownWidthNormalized +
          middleFrame.backwardLeafFrame!.curlWidthNormalized,
      closeTo(middleFrame.backwardLeafFrame!.coveredWidthNormalized, 0.0001),
    );
    // 旧的 verso + edge + recto = curl 不变量是简化模型下的近似（默认
    // versoReveal = curlWidth - edge - recto），新的纸折物理把 verso 的
    // 起点改为 covered * rectoCoverage，verso 在 covered ≤ 0.5 时等于
    // covered 自身，因此 verso + edge + recto 可能略大于 curlWidth 但仍
    // 应受 1.0（满页归一化宽度）约束，并保持 verso ≥ 0。
    expect(
      earlyFrame.backwardLeafFrame!.versoRevealWidthNormalized,
      greaterThanOrEqualTo(0),
    );
    expect(
      middleFrame.backwardLeafFrame!.versoRevealWidthNormalized,
      greaterThanOrEqualTo(0),
    );
    expect(
      earlyFrame.backwardLeafFrame!.versoRevealWidthNormalized +
          earlyFrame.backwardLeafFrame!.edgeBandWidthNormalized +
          earlyFrame.backwardLeafFrame!.rectoRevealWidthNormalized,
      lessThanOrEqualTo(1.0),
    );
    expect(
      middleFrame.backwardLeafFrame!.versoRevealWidthNormalized +
          middleFrame.backwardLeafFrame!.edgeBandWidthNormalized +
          middleFrame.backwardLeafFrame!.rectoRevealWidthNormalized,
      lessThanOrEqualTo(1.0),
    );
    expect(
      earlyFrame.backwardLeafFrame!.versoRevealWidthNormalized +
          earlyFrame.backwardLeafFrame!.edgeBandWidthNormalized,
      greaterThan(0),
    );
    expect(
      middleFrame.backwardLeafFrame!.versoRevealWidthNormalized +
          middleFrame.backwardLeafFrame!.edgeBandWidthNormalized,
      greaterThan(0),
    );
  });

  test('FlipController 的轻微回翻不会在 stopMove 阶段直接判定为已翻页', () {
    final controller = StPageFlipController(
      spreadModel: StPageFlipSpreadModel(pageCount: 3),
      layout: computeStPageFlipLayout(
        viewportSize: const Size(430, 900),
        pageWidth: 398,
        pageHeight: 553,
        usePortrait: true,
      ),
      initialPage: 1,
    );

    final bounds = controller.layout.bounds;
    final startGlobal = Offset(
      bounds.left + bounds.pageWidth + 44,
      bounds.top + bounds.height - 44,
    );
    final slightDragGlobal = Offset(startGlobal.dx + 56, startGlobal.dy - 12);

    controller.fold(startGlobal);
    controller.fold(slightDragGlobal);

    final frame = controller.scene.renderFrame;
    expect(frame, isNotNull);
    expect(frame!.direction, StPageFlipDirection.back);
    expect(frame.progress, greaterThanOrEqualTo(0));
    expect(frame.progress, lessThan(0.3));

    final plan = controller.stopMove();
    expect(plan, isNotNull);
    expect(plan!.isTurned, isFalse);
  });

  test('BackwardPageTextureBundle 会映射为 HF curl textures', () async {
    final coveredImage = await _createTestImage();
    final leafRectoImage = await _createTestImage();
    final leafVersoImage = await _createTestImage();
    addTearDown(coveredImage.dispose);
    addTearDown(leafRectoImage.dispose);
    addTearDown(leafVersoImage.dispose);

    final bundle = ArticleBackwardPageTextureBundle(
      covered: ArticlePageTextureSnapshot(
        image: coveredImage,
        logicalSize: const Size(1, 1),
        pixelRatio: 1,
      ),
      leafRecto: ArticlePageTextureSnapshot(
        image: leafRectoImage,
        logicalSize: const Size(1, 1),
        pixelRatio: 1,
      ),
      leafVerso: ArticlePageTextureSnapshot(
        image: leafVersoImage,
        logicalSize: const Size(1, 1),
        pixelRatio: 1,
      ),
    );

    final curlBundle = bundle.toCurlTextureBundle();
    expect(curlBundle.bottom.image, same(coveredImage));
    expect(curlBundle.recto.image, same(leafRectoImage));
    expect(curlBundle.verso.image, same(leafVersoImage));
  });

  test('PageTextureSession 会在纹理补齐后激活并在冻结期保持原绑定', () async {
    final binding = const ArticlePageTextureBinding(
      direction: StPageFlipDirection.back,
      rectoPageIndex: 1,
      versoPageIndex: 2,
      bottomPageIndex: 2,
    );
    final changedBinding = const ArticlePageTextureBinding(
      direction: StPageFlipDirection.back,
      rectoPageIndex: 0,
      versoPageIndex: 1,
      bottomPageIndex: 1,
    );
    final bundle = await _createTestTextureBundle();
    addTearDown(bundle.recto.dispose);
    addTearDown(bundle.verso.dispose);
    addTearDown(bundle.bottom.dispose);

    final pendingSession = resolveArticlePageTextureSession(
      existing: null,
      binding: binding,
      resolvedBundle: null,
      supportsHighFidelity: true,
      freezeBinding: true,
    );
    expect(pendingSession, isNotNull);
    expect(pendingSession!.preferHighFidelity, isFalse);
    expect(pendingSession.bundle, isNull);

    final activatedSession = resolveArticlePageTextureSession(
      existing: pendingSession,
      binding: binding,
      resolvedBundle: bundle,
      supportsHighFidelity: true,
      freezeBinding: true,
    );
    expect(activatedSession, isNotNull);
    expect(activatedSession!.preferHighFidelity, isTrue);
    expect(activatedSession.bundle, same(bundle));

    final frozenSession = resolveArticlePageTextureSession(
      existing: activatedSession,
      binding: changedBinding,
      resolvedBundle: null,
      supportsHighFidelity: true,
      freezeBinding: true,
    );
    expect(frozenSession, isNotNull);
    expect(frozenSession!.binding.matches(binding), isTrue);
    expect(frozenSession.bundle, same(bundle));

    final liveSession = resolveArticlePageTextureSession(
      existing: activatedSession,
      binding: changedBinding,
      resolvedBundle: bundle,
      supportsHighFidelity: true,
      freezeBinding: false,
    );
    expect(liveSession, isNotNull);
    expect(liveSession!.binding.matches(changedBinding), isTrue);
    expect(liveSession.bundle, same(bundle));
  });

  test('ArticlePageTextureSnapshot 会校验逻辑尺寸与像素映射', () async {
    final image = await _createTestImage(width: 4, height: 6);
    addTearDown(image.dispose);
    final snapshot = ArticlePageTextureSnapshot(
      image: image,
      logicalSize: const Size(2, 3),
      pixelRatio: 2,
    );

    expect(snapshot.pixelWidthPerLogical, closeTo(2, 0.0001));
    expect(snapshot.pixelHeightPerLogical, closeTo(2, 0.0001));
    expect(snapshot.matchesLogicalSize(const Size(2, 3)), isTrue);
    expect(snapshot.matchesLogicalSize(const Size(2.02, 3)), isFalse);
    expect(snapshot.matchesLogicalSize(const Size(2, 3.02)), isFalse);
  });

  test('CurlMeshBuilder 在前翻时生成正反两面网格并保持页内裁剪', () {
    final builder = ArticlePageCurlMeshBuilder();
    const pageRect = Rect.fromLTWH(16, 64, 398, 553);
    final clipPath = Path()..addRect(pageRect);

    final frame = builder.build(
      pageRect: pageRect,
      pageSize: const Size(398, 553),
      dragPoint: const Offset(92, 520),
      progress: 0.74,
      direction: StPageFlipDirection.forward,
      corner: StPageFlipCorner.bottom,
      bottomClipPath: clipPath,
    );

    expect(frame.frontSurface, isNotNull);
    expect(frame.backSurface, isNotNull);
    expect(frame.foldXNormalized, inInclusiveRange(0.0, 1.0));
    expect(frame.curlLift, greaterThan(0));
    expect(frame.rollProgress, closeTo(0.74, 0.0001));
    expect(frame.cylinderProgress, equals(0));
    expect(frame.unfoldProgress, equals(0));
    expect(frame.frontBounds.left, greaterThanOrEqualTo(pageRect.left));
    expect(frame.frontBounds.top, greaterThanOrEqualTo(pageRect.top));
    expect(frame.frontBounds.bottom, lessThanOrEqualTo(pageRect.bottom + 16));
    expect(frame.backBounds.width, greaterThan(8));
    expect(frame.backBounds.left, greaterThanOrEqualTo(pageRect.left));
    expect(frame.backBounds.right, lessThanOrEqualTo(pageRect.right));
    expect(frame.backBounds.left, lessThan(frame.frontBounds.right));
    final clipBounds = clipPath.getBounds();
    final resolvedBounds = frame.bottomClipPath.getBounds();
    expect(resolvedBounds.left, greaterThanOrEqualTo(clipBounds.left));
    expect(resolvedBounds.right, equals(clipBounds.right));
    expect(resolvedBounds.top, equals(clipBounds.top));
    expect(resolvedBounds.bottom, equals(clipBounds.bottom));

    final steepFrame = builder.build(
      pageRect: pageRect,
      pageSize: const Size(398, 553),
      dragPoint: const Offset(220, 300),
      progress: 0.74,
      direction: StPageFlipDirection.forward,
      corner: StPageFlipCorner.bottom,
      bottomClipPath: clipPath,
    );
    expect(steepFrame.frontSurface, isNotNull);
    expect(steepFrame.backSurface, isNotNull);
    expect(
      steepFrame.bottomClipPath.getBounds().right,
      equals(clipBounds.right),
    );
    expect(steepFrame.backBounds.width, greaterThan(8));
    expect(steepFrame.backBounds.left, greaterThanOrEqualTo(pageRect.left));
    expect(steepFrame.backBounds.right, lessThanOrEqualTo(pageRect.right));
  });

  test('CurlMeshBuilder 会保留前翻 canonical 底页可见区而不是继续缩窄', () {
    final builder = ArticlePageCurlMeshBuilder();
    const pageRect = Rect.fromLTWH(16, 64, 398, 553);
    final clipRect = Rect.fromLTRB(
      pageRect.left + 188,
      pageRect.top,
      pageRect.right,
      pageRect.bottom,
    );
    final clipPath = Path()..addRect(clipRect);

    final frame = builder.build(
      pageRect: pageRect,
      pageSize: const Size(398, 553),
      dragPoint: const Offset(148, 520),
      progress: 0.52,
      direction: StPageFlipDirection.forward,
      corner: StPageFlipCorner.bottom,
      bottomClipPath: clipPath,
    );

    final resolvedBounds = frame.bottomClipPath.getBounds();
    expect(resolvedBounds.left, closeTo(clipRect.left, 0.001));
    expect(resolvedBounds.top, closeTo(clipRect.top, 0.001));
    expect(resolvedBounds.right, closeTo(clipRect.right, 0.001));
    expect(resolvedBounds.bottom, closeTo(clipRect.bottom, 0.001));
  });

  test('CurlMeshBuilder 的前翻背面展开会消费 rigid angle', () {
    final builder = ArticlePageCurlMeshBuilder();
    const pageRect = Rect.fromLTWH(16, 64, 398, 553);
    const localPoint = Offset(188, 332);

    final shallowAngleFrame = builder.build(
      pageRect: pageRect,
      pageSize: const Size(398, 553),
      dragPoint: localPoint,
      progress: 0.72,
      direction: StPageFlipDirection.forward,
      corner: StPageFlipCorner.bottom,
      renderFrame: _forwardRenderFrame(
        localPagePoint: localPoint,
        progress: 0.72,
        angle: -0.18,
        corner: StPageFlipCorner.bottom,
      ),
    );
    final wideAngleFrame = builder.build(
      pageRect: pageRect,
      pageSize: const Size(398, 553),
      dragPoint: localPoint,
      progress: 0.72,
      direction: StPageFlipDirection.forward,
      corner: StPageFlipCorner.bottom,
      renderFrame: _forwardRenderFrame(
        localPagePoint: localPoint,
        progress: 0.72,
        angle: -1.18,
        corner: StPageFlipCorner.bottom,
      ),
    );

    expect(shallowAngleFrame.backBounds.width, greaterThan(0));
    expect(
      wideAngleFrame.backBounds.width,
      greaterThan(shallowAngleFrame.backBounds.width),
    );
    expect(wideAngleFrame.backBounds.right, lessThanOrEqualTo(pageRect.right));
  });

  test('CurlMeshBuilder 会量化前翻正反面的几何放大与溢出诊断', () {
    const samples = <({Offset dragPoint, double progress})>[
      (dragPoint: Offset(340, 520), progress: 0.18),
      (dragPoint: Offset(276, 488), progress: 0.54),
      (dragPoint: Offset(220, 300), progress: 0.74),
      (dragPoint: Offset(184, 220), progress: 0.86),
    ];

    for (final sample in samples) {
      final frame = _buildForwardMeshFrame(
        dragPoint: sample.dragPoint,
        progress: sample.progress,
      );

      final front = frame.frontDiagnostics;
      final back = frame.backDiagnostics;
      expect(front, isNotNull, reason: 'front diagnostics should exist');
      expect(back, isNotNull, reason: 'back diagnostics should exist');
      expect(front!.maxEdgeScale, lessThanOrEqualTo(1.10));
      expect(back!.maxEdgeScale, lessThanOrEqualTo(1.10));
      expect(front.maxTriangleAreaScale, lessThanOrEqualTo(1.10));
      expect(back.maxTriangleAreaScale, lessThanOrEqualTo(1.10));
      expect(front.meanEdgeScale, lessThanOrEqualTo(0.8));
      expect(back.meanEdgeScale, lessThanOrEqualTo(1.0));
      expect(front.hasOverflow, isFalse);
      expect(back.hasOverflow, isFalse);
    }
  });

  test('CurlMeshBuilder 在回翻时走 forward replay 卷曲', () {
    final builder = ArticlePageCurlMeshBuilder();
    final frame = builder.build(
      pageRect: const Rect.fromLTWH(16, 64, 398, 553),
      pageSize: const Size(398, 553),
      dragPoint: const Offset(278, 120),
      progress: 0.68,
      direction: StPageFlipDirection.back,
      corner: StPageFlipCorner.top,
    );

    expect(frame.frontSurface, isNotNull);
    expect(frame.backSurface, isNotNull);
    expect(frame.curlLift, greaterThan(0));
    expect(frame.rollProgress, greaterThan(0));
    expect(frame.cylinderProgress, equals(0));
    expect(frame.unfoldProgress, equals(0));
    expect(frame.foldXNormalized, greaterThan(0));
  });

  test('CurlMeshBuilder 在回翻多关键帧下 replay 折线从左向右移动', () {
    final builder = ArticlePageCurlMeshBuilder();
    final early = builder.build(
      pageRect: const Rect.fromLTWH(16, 64, 398, 553),
      pageSize: const Size(398, 553),
      dragPoint: const Offset(348, 120),
      progress: 0.18,
      direction: StPageFlipDirection.back,
      corner: StPageFlipCorner.top,
    );
    final middle = builder.build(
      pageRect: const Rect.fromLTWH(16, 64, 398, 553),
      pageSize: const Size(398, 553),
      dragPoint: const Offset(278, 120),
      progress: 0.58,
      direction: StPageFlipDirection.back,
      corner: StPageFlipCorner.top,
    );
    final late = builder.build(
      pageRect: const Rect.fromLTWH(16, 64, 398, 553),
      pageSize: const Size(398, 553),
      dragPoint: const Offset(198, 120),
      progress: 0.9,
      direction: StPageFlipDirection.back,
      corner: StPageFlipCorner.top,
    );

    expect(early.frontSurface, isNotNull);
    expect(middle.backSurface, isNotNull);
    expect(late.frontSurface, isNotNull);
    expect(early.foldXNormalized, lessThan(middle.foldXNormalized));
    expect(middle.foldXNormalized, lessThan(late.foldXNormalized));
    expect(early.cylinderProgress, equals(0));
    expect(middle.cylinderProgress, equals(0));
    expect(late.cylinderProgress, equals(0));
    expect(early.unfoldProgress, equals(0));
    expect(middle.unfoldProgress, equals(0));
    expect(late.unfoldProgress, equals(0));
  });

  test('CurlMeshBuilder 会消费 portrait 回翻的 replay render frame', () {
    final builder = ArticlePageCurlMeshBuilder();
    final frame = _backwardReplayRenderFrame(
      localPagePoint: const Offset(120, 132),
      progress: 0.88,
      corner: StPageFlipCorner.top,
    );

    final meshFrame = builder.build(
      pageRect: const Rect.fromLTWH(16, 64, 398, 553),
      pageSize: const Size(398, 553),
      dragPoint: frame.localPagePoint,
      progress: frame.progress,
      direction: frame.direction,
      corner: frame.corner,
      renderFrame: frame,
    );

    expect(meshFrame.frontSurface, isNotNull);
    expect(meshFrame.backSurface, isNotNull);
    expect(meshFrame.rollProgress, greaterThanOrEqualTo(0));
    expect(meshFrame.cylinderProgress, equals(0));
    expect(meshFrame.unfoldProgress, equals(0));
    expect(meshFrame.curlLift, greaterThan(0));
  });

  test('CurlMeshBuilder 的高保真回翻会锁定书脊为同一条竖线', () {
    final builder = ArticlePageCurlMeshBuilder();
    final frame = _backwardReplayRenderFrame(
      localPagePoint: const Offset(150, 140),
      progress: 0.72,
      corner: StPageFlipCorner.top,
    );

    final meshFrame = builder.build(
      pageRect: const Rect.fromLTWH(16, 64, 398, 553),
      pageSize: const Size(398, 553),
      dragPoint: frame.localPagePoint,
      progress: frame.progress,
      direction: frame.direction,
      corner: frame.corner,
      renderFrame: frame,
    );

    expect(meshFrame.alignmentDiagnostics, isNotNull);
    expect(
      meshFrame.alignmentDiagnostics!.spineDelta,
      lessThanOrEqualTo(0.001),
    );
    expect(meshFrame.alignmentDiagnostics!.seamDelta, lessThanOrEqualTo(0.001));
  });

  test('CurlMeshBuilder 的高保真回翻在不同阶段都保持书脊对齐', () {
    final builder = ArticlePageCurlMeshBuilder();
    final frames = <StPageFlipRenderFrame>[
      _backwardReplayRenderFrame(
        localPagePoint: const Offset(332, 120),
        progress: 0.18,
        corner: StPageFlipCorner.top,
      ),
      _backwardReplayRenderFrame(
        localPagePoint: const Offset(228, 140),
        progress: 0.58,
        corner: StPageFlipCorner.top,
      ),
      _backwardReplayRenderFrame(
        localPagePoint: const Offset(118, 160),
        progress: 0.9,
        corner: StPageFlipCorner.top,
      ),
    ];

    for (final frame in frames) {
      final meshFrame = builder.build(
        pageRect: const Rect.fromLTWH(16, 64, 398, 553),
        pageSize: const Size(398, 553),
        dragPoint: frame.localPagePoint,
        progress: frame.progress,
        direction: frame.direction,
        corner: frame.corner,
        renderFrame: frame,
      );
      expect(meshFrame.alignmentDiagnostics, isNotNull);
      expect(
        meshFrame.alignmentDiagnostics!.spineDelta,
        lessThanOrEqualTo(0.001),
      );
      expect(
        meshFrame.alignmentDiagnostics!.seamDelta,
        lessThanOrEqualTo(0.001),
      );
    }
  });

  test('CurlMeshBuilder 在 backward leaf contract 存在时优先 replay 主线', () {
    final builder = ArticlePageCurlMeshBuilder();
    final baseFrame = _backwardReplayRenderFrame(
      localPagePoint: const Offset(168, 148),
      progress: 0.66,
      corner: StPageFlipCorner.top,
    );
    final reversePose = resolveReverseFlipPose(
      localPagePoint: baseFrame.localPagePoint,
      pageSize: const Size(398, 553),
      progress: baseFrame.progress,
      corner: baseFrame.corner,
    );
    final frameWithCurrentPose = StPageFlipRenderFrame(
      localPagePoint: baseFrame.localPagePoint,
      progress: baseFrame.progress,
      direction: baseFrame.direction,
      renderDirection: baseFrame.renderDirection,
      corner: baseFrame.corner,
      flippingClipArea: baseFrame.flippingClipArea,
      bottomClipArea: baseFrame.bottomClipArea,
      flippingAnchor: baseFrame.flippingAnchor,
      bottomAnchor: baseFrame.bottomAnchor,
      angle: baseFrame.angle,
      shadow: baseFrame.shadow,
      timeline: baseFrame.timeline,
      reversePose: reversePose,
      backwardLeafFrame: baseFrame.backwardLeafFrame,
    );

    final meshFrame = builder.build(
      pageRect: const Rect.fromLTWH(16, 64, 398, 553),
      pageSize: const Size(398, 553),
      dragPoint: frameWithCurrentPose.localPagePoint,
      progress: frameWithCurrentPose.progress,
      direction: frameWithCurrentPose.direction,
      corner: frameWithCurrentPose.corner,
      reversePose: reversePose,
      renderFrame: frameWithCurrentPose,
    );

    expect(meshFrame.alignmentDiagnostics, isNotNull);
    expect(
      meshFrame.alignmentDiagnostics!.spineDelta,
      lessThanOrEqualTo(0.001),
    );
    expect(meshFrame.alignmentDiagnostics!.seamDelta, lessThanOrEqualTo(0.001));
    expect(
      meshFrame.foldXNormalized,
      closeTo(baseFrame.backwardLeafFrame!.seamXNormalized, 0.0001),
    );
  });

  test('resolvePageCurlTimeline 在前翻时保持更保守的几何 profile', () {
    const pageSize = Size(398, 553);
    final timeline = resolvePageCurlTimeline(
      direction: StPageFlipDirection.forward,
      renderDirection: StPageFlipDirection.forward,
      progress: 0.72,
      localPagePoint: const Offset(276, 488),
      pageSize: pageSize,
      corner: StPageFlipCorner.bottom,
      angleBand: resolveForwardCurlAngleBand(
        localPagePoint: const Offset(276, 488),
        pageSize: pageSize,
        corner: StPageFlipCorner.bottom,
      ),
    );

    expect(timeline.heightLiftBias, closeTo(0.021, 0.0001));
    expect(
      timeline.sheetShift.abs(),
      lessThanOrEqualTo(pageSize.width * 0.022),
    );
    expect(timeline.diagonalExtent, lessThanOrEqualTo(pageSize.width * 0.078));
    expect(timeline.leadingRadius, greaterThan(timeline.trailingRadius));
    expect(timeline.cylinderRadiusNormalized, greaterThan(0.06));
    expect(timeline.bottomGapNormalized, inInclusiveRange(0.0, 1.0));
  });

  test('resolveForwardCurlAngleBand 会按滑动角度分段', () {
    const pageSize = Size(398, 553);
    expect(
      resolveForwardCurlAngleBand(
        localPagePoint: const Offset(360, 540),
        pageSize: pageSize,
        corner: StPageFlipCorner.bottom,
      ),
      StPageFlipCurlAngleBand.shallow,
    );
    expect(
      resolveForwardCurlAngleBand(
        localPagePoint: const Offset(276, 488),
        pageSize: pageSize,
        corner: StPageFlipCorner.bottom,
      ),
      StPageFlipCurlAngleBand.mid,
    );
    expect(
      resolveForwardCurlAngleBand(
        localPagePoint: const Offset(220, 300),
        pageSize: pageSize,
        corner: StPageFlipCorner.bottom,
      ),
      StPageFlipCurlAngleBand.steep,
    );
  });

  test('CurlLightModel 会随卷曲进度增强投影与背页调制', () {
    final lightState = resolveArticlePageCurlLightState(
      progress: 0.72,
      foldXNormalized: 0.34,
      curlLift: 0.61,
      rollProgress: 1,
      cylinderProgress: 0.54,
      unfoldProgress: 0.52,
      cylinderRadiusNormalized: 0.18,
      unrollWidthNormalized: 0.22,
      bottomGapNormalized: 0.16,
      direction: StPageFlipDirection.forward,
      corner: StPageFlipCorner.bottom,
    );

    expect(lightState.foldXNormalized, closeTo(0.34, 0.0001));
    expect(lightState.tunnelShadowStrength, greaterThan(0.4));
    expect(lightState.bottomShadowStrength, greaterThan(0.3));
    expect(lightState.backfaceTintStrength, greaterThan(0.12));
    expect(lightState.backfaceOcclusionStrength, lessThan(0.2));
    expect(lightState.edgeHighlightStrength, greaterThan(0.25));
  });

  test('CurlLightModel 会为背页保留可读亮度下限', () {
    // In the mirrored approach, backward uses the same light model as forward.
    // The reverse* variables are all 0, so backface tint/occlusion are lower.
    final midState = resolveArticlePageCurlLightState(
      progress: 0.66,
      foldXNormalized: 0.28,
      curlLift: 0.58,
      rollProgress: 0.76,
      cylinderProgress: 0,
      unfoldProgress: 0,
      direction: StPageFlipDirection.back,
      corner: StPageFlipCorner.bottom,
    );

    expect(midState.backfaceTintStrength, inInclusiveRange(0.10, 0.22));
    expect(midState.backfaceOcclusionStrength, inInclusiveRange(0.10, 0.24));
    expect(
      midState.backfaceOcclusionStrength,
      lessThan(midState.tunnelShadowStrength),
    );
  });

  test('CurlLightModel 在回翻镜像路径下光影与前翻对称', () {
    // In the mirrored approach, backward uses the same light model as forward.
    // cylinderProgress and unfoldProgress are always 0 for backward.
    final earlyState = resolveArticlePageCurlLightState(
      progress: 0.32,
      foldXNormalized: 0.08,
      curlLift: 0.74,
      rollProgress: 0.7,
      cylinderProgress: 0,
      unfoldProgress: 0,
      direction: StPageFlipDirection.back,
      corner: StPageFlipCorner.top,
    );
    final lateState = resolveArticlePageCurlLightState(
      progress: 0.84,
      foldXNormalized: 0.22,
      curlLift: 0.54,
      rollProgress: 1.0,
      cylinderProgress: 0,
      unfoldProgress: 0,
      direction: StPageFlipDirection.back,
      corner: StPageFlipCorner.top,
    );

    // Tunnel shadow should be present in early state.
    expect(earlyState.tunnelShadowStrength, greaterThan(0));
    // Edge highlight should increase with progress.
    expect(
      lateState.edgeHighlightStrength,
      greaterThanOrEqualTo(earlyState.edgeHighlightStrength),
    );
    // Backface tint should be moderate.
    expect(lateState.backfaceTintStrength, greaterThan(0.10));
    expect(lateState.backfaceOcclusionStrength, lessThan(0.26));
  });

  test('CurlLightModel 在回翻三阶段参数下光影有层次变化', () {
    // 三阶段主线：cylinderProgress 和 unfoldProgress 非零时，
    // 光影应该比全零时有更丰富的层次。
    final zeroStageState = resolveArticlePageCurlLightState(
      progress: 0.72,
      foldXNormalized: 0.34,
      curlLift: 0.61,
      rollProgress: 1,
      cylinderProgress: 0,
      unfoldProgress: 0,
      direction: StPageFlipDirection.back,
      corner: StPageFlipCorner.bottom,
    );
    final threeStageState = resolveArticlePageCurlLightState(
      progress: 0.72,
      foldXNormalized: 0.34,
      curlLift: 0.61,
      rollProgress: 1,
      cylinderProgress: 0.54,
      unfoldProgress: 0.52,
      cylinderRadiusNormalized: 0.18,
      unrollWidthNormalized: 0.22,
      bottomGapNormalized: 0.16,
      direction: StPageFlipDirection.back,
      corner: StPageFlipCorner.bottom,
    );
    // 三阶段参数应该影响背页光影强度。
    expect(
      threeStageState.backfaceTintStrength,
      isNot(equals(zeroStageState.backfaceTintStrength)),
      reason: '三阶段参数应改变背页 tint 强度',
    );
    // 三阶段参数应该影响 spine ambient。
    expect(threeStageState.spineAmbientStrength, greaterThan(0));
  });

  test('flipPrev 产出的 AnimationPlan 不再携带 reversePoses', () {
    final controller = StPageFlipController(
      spreadModel: StPageFlipSpreadModel(pageCount: 3),
      layout: computeStPageFlipLayout(
        viewportSize: const Size(430, 900),
        pageWidth: 398,
        pageHeight: 553,
        usePortrait: true,
      ),
      initialPage: 1,
    );

    final plan = controller.flipPrev(StPageFlipCorner.bottom);
    expect(plan, isNotNull);
    expect(plan!.reversePoses, isNull);
  });

  test('flipPrev 保持 shared frame 序列而不附加 reversePoses', () {
    final controller = StPageFlipController(
      spreadModel: StPageFlipSpreadModel(pageCount: 3),
      layout: computeStPageFlipLayout(
        viewportSize: const Size(430, 900),
        pageWidth: 398,
        pageHeight: 553,
        usePortrait: true,
      ),
      initialPage: 1,
    );

    final plan = controller.flipPrev(StPageFlipCorner.bottom);
    expect(plan, isNotNull);
    expect(plan!.frames, isNotEmpty);
    expect(plan.reversePoses, isNull);
  });

  test('stopMove 回弹时也不再产出 reversePoses', () {
    final controller = StPageFlipController(
      spreadModel: StPageFlipSpreadModel(pageCount: 3),
      layout: computeStPageFlipLayout(
        viewportSize: const Size(430, 900),
        pageWidth: 398,
        pageHeight: 553,
        usePortrait: true,
      ),
      initialPage: 1,
    );
    // 开始一次回翻拖拽
    final started = controller.start(const Offset(30, 500));
    expect(started, isTrue);

    // 拖拽到中间位置（不超过阈值）
    controller.fold(const Offset(250, 480));

    // 松手回弹
    final plan = controller.stopMove();
    expect(plan, isNotNull);
    expect(plan!.reversePoses, isNull);
  });

  test('flipNext 不产出 reversePoses（前翻不受影响）', () {
    final controller = StPageFlipController(
      spreadModel: StPageFlipSpreadModel(pageCount: 3),
      layout: computeStPageFlipLayout(
        viewportSize: const Size(430, 900),
        pageWidth: 398,
        pageHeight: 553,
        usePortrait: true,
      ),
      initialPage: 0,
    );

    final plan = controller.flipNext(StPageFlipCorner.bottom);
    expect(plan, isNotNull);
    // 前翻不应产出 reversePoses
    expect(plan!.reversePoses, isNull);
  });

  test('ReverseCurlCalculation 在三阶段中产出非零角度', () {
    const pageSize = Size(398, 553);
    final calc = ReverseCurlCalculation(
      corner: StPageFlipCorner.top,
      pageWidth: pageSize.width,
      pageHeight: pageSize.height,
    );
    // 模拟 cylinder 阶段中期的 pose
    final pose = resolveReverseFlipPose(
      localPagePoint: const Offset(200, 280),
      pageSize: pageSize,
      progress: 0.55,
      corner: StPageFlipCorner.top,
    );
    calc.syncPose(pose);

    final angle = calc.getAngle();
    // 新方案：回翻角度固定为 0
    expect(angle, equals(0), reason: '回翻不旋转，角度固定为 0');
  });

  test('ReverseCurlCalculation 在 cylinder 阶段产出非矩形 clip area', () {
    const pageSize = Size(398, 553);
    final calc = ReverseCurlCalculation(
      corner: StPageFlipCorner.top,
      pageWidth: pageSize.width,
      pageHeight: pageSize.height,
    );
    // 构造一个 cylinderProgress > 0 的 pose
    final pose = resolveReverseFlipPose(
      localPagePoint: const Offset(160, 280),
      pageSize: pageSize,
      progress: 0.65,
      corner: StPageFlipCorner.top,
    );
    calc.syncPose(pose);

    final clipArea = calc.getFlippingClipArea();
    // 新方案：回翻 clip area 始终是 4 点矩形（从左边缘到 coveredWidth）。
    expect(clipArea.length, equals(4), reason: '回翻 clip area 始终是 4 点矩形');
  });

  test('ReverseCurlCalculation 的 getAngle 在 unroll 阶段趋近于零', () {
    const pageSize = Size(398, 553);
    final calc = ReverseCurlCalculation(
      corner: StPageFlipCorner.top,
      pageWidth: pageSize.width,
      pageHeight: pageSize.height,
    );
    // 构造一个接近完成的 pose（unroll 阶段末期）
    final pose = resolveReverseFlipPose(
      localPagePoint: const Offset(20, 280),
      pageSize: pageSize,
      progress: 0.98,
      corner: StPageFlipCorner.top,
    );
    calc.syncPose(pose);

    final angle = calc.getAngle();
    // unroll 末期角度应该很小（页面几乎摊平）
    expect(angle.abs(), lessThan(0.3), reason: 'unroll 末期角度应趋近于零');
  });
}

StPageFlipRenderFrame _backwardReplayRenderFrame({
  required Offset localPagePoint,
  required double progress,
  required StPageFlipCorner corner,
}) {
  const pageSize = Size(398, 553);
  final replayLocalPoint = resolveBackwardReplayLocalPagePoint(
    localPagePoint: localPagePoint,
    pageSize: pageSize,
  );
  final timeline = resolvePageCurlTimeline(
    direction: StPageFlipDirection.back,
    renderDirection: StPageFlipDirection.back,
    progress: progress,
    localPagePoint: localPagePoint,
    pageSize: pageSize,
    corner: corner,
    angleBand: resolveForwardCurlAngleBand(
      localPagePoint: replayLocalPoint,
      pageSize: pageSize,
      corner: corner,
    ),
  );
  return StPageFlipRenderFrame(
    localPagePoint: localPagePoint,
    progress: progress,
    direction: StPageFlipDirection.back,
    renderDirection: StPageFlipDirection.back,
    corner: corner,
    flippingClipArea: const <Offset>[
      Offset(148, 0),
      Offset(398, 0),
      Offset(398, 553),
      Offset(148, 553),
    ],
    bottomClipArea: const <Offset>[
      Offset.zero,
      Offset(148, 0),
      Offset(172, 92),
      Offset(148, 553),
      Offset.zero,
    ],
    flippingAnchor: Offset(148, corner == StPageFlipCorner.top ? 0 : 553),
    bottomAnchor: const Offset(398, 0),
    angle: corner == StPageFlipCorner.top ? 0.42 : -0.42,
    shadow: null,
    timeline: timeline,
    backwardLeafFrame: resolveArticlePageBackwardLeafFrame(
      direction: StPageFlipDirection.back,
      progress: progress,
    ),
  );
}

ArticlePageCurlFrame _buildForwardMeshFrame({
  required Offset dragPoint,
  required double progress,
  StPageFlipCorner corner = StPageFlipCorner.bottom,
}) {
  const pageRect = Rect.fromLTWH(16, 64, 398, 553);
  return const ArticlePageCurlMeshBuilder().build(
    pageRect: pageRect,
    pageSize: pageRect.size,
    dragPoint: dragPoint,
    progress: progress,
    direction: StPageFlipDirection.forward,
    corner: corner,
  );
}

StPageFlipRenderFrame _forwardRenderFrame({
  required Offset localPagePoint,
  required double progress,
  required double angle,
  required StPageFlipCorner corner,
}) {
  const pageSize = Size(398, 553);
  final timeline = resolvePageCurlTimeline(
    direction: StPageFlipDirection.forward,
    renderDirection: StPageFlipDirection.forward,
    progress: progress,
    localPagePoint: localPagePoint,
    pageSize: pageSize,
    corner: corner,
    angleBand: resolveForwardCurlAngleBand(
      localPagePoint: localPagePoint,
      pageSize: pageSize,
      corner: corner,
    ),
  );
  return StPageFlipRenderFrame(
    localPagePoint: localPagePoint,
    progress: progress,
    direction: StPageFlipDirection.forward,
    renderDirection: StPageFlipDirection.forward,
    corner: corner,
    flippingClipArea: const <Offset>[],
    bottomClipArea: const <Offset>[],
    flippingAnchor: Offset(
      localPagePoint.dx,
      corner == StPageFlipCorner.top ? 0 : pageSize.height,
    ),
    bottomAnchor: Offset.zero,
    angle: angle,
    shadow: null,
    timeline: timeline,
  );
}

Future<ArticlePageTextureBundle> _createTestTextureBundle() async {
  return ArticlePageTextureBundle(
    recto: ArticlePageTextureSnapshot(
      image: await _createTestImage(),
      logicalSize: const Size(1, 1),
      pixelRatio: 1,
    ),
    verso: ArticlePageTextureSnapshot(
      image: await _createTestImage(),
      logicalSize: const Size(1, 1),
      pixelRatio: 1,
    ),
    bottom: ArticlePageTextureSnapshot(
      image: await _createTestImage(),
      logicalSize: const Size(1, 1),
      pixelRatio: 1,
    ),
  );
}

Future<ui.Image> _createTestImage({int width = 1, int height = 1}) async {
  final recorder = ui.PictureRecorder();
  final canvas = Canvas(recorder);
  canvas.drawRect(
    Rect.fromLTWH(0, 0, width.toDouble(), height.toDouble()),
    Paint()..color = const Color(0xFFFFFFFF),
  );
  final picture = recorder.endRecording();
  final image = await picture.toImage(width, height);
  picture.dispose();
  return image;
}
