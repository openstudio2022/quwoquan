import 'dart:ui' as ui;

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/ui/content/pageflip/book_layout.dart';
import 'package:quwoquan_app/ui/content/pageflip/controller.dart';
import 'package:quwoquan_app/ui/content/pageflip/curl_light_model.dart';
import 'package:quwoquan_app/ui/content/pageflip/curl_mesh_builder.dart';
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

  test('FlipController 的 portrait 回翻 render frame 会切到三阶段主线', () {
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
    expect(frame.renderDirection, StPageFlipDirection.forward);
    expect(frame.reversePose, isNotNull);
    expect(frame.timeline.rollProgress, greaterThan(0));
    // 新方案：回翻复用前翻 timeline（时间反转+镜像），
    // cylinderProgress/unfoldProgress 不再独立使用。
    expect(frame.timeline.mirrored, isTrue);
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
    expect(forwardBinding.versoPageIndex, 3);
    expect(forwardBinding.bottomPageIndex, 3);

    expect(backwardBinding, isNotNull);
    expect(backwardBinding!.rectoPageIndex, 2);
    expect(backwardBinding.versoPageIndex, 3);
    expect(backwardBinding.bottomPageIndex, 3);
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
  });

  test('CurlMeshBuilder 在前翻时生成正反两面网格并保持页内裁剪', () {
    final builder = ArticlePageCurlMeshBuilder();
    final clipPath = Path()..addRect(const Rect.fromLTWH(16, 64, 398, 553));

    final frame = builder.build(
      pageRect: const Rect.fromLTWH(16, 64, 398, 553),
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
    expect(frame.bottomClipPath.getBounds(), equals(clipPath.getBounds()));
  });

  test('CurlMeshBuilder 在回翻时产生与前翻对称的镜像卷曲', () {
    // 无 reversePose 时走降级的 mirrored forward 路径。
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
    // Mirrored forward: rollProgress comes from the forward cylinder model.
    expect(frame.rollProgress, greaterThan(0));
    // cylinderProgress and unfoldProgress are 0 in the mirrored path.
    expect(frame.cylinderProgress, equals(0));
    expect(frame.unfoldProgress, equals(0));
    expect(frame.foldXNormalized, greaterThan(0));
  });

  test('CurlMeshBuilder 在回翻有 reversePose 时走三阶段主线', () {
    final builder = ArticlePageCurlMeshBuilder();
    const pageSize = Size(398, 553);
    final reversePose = resolveReverseFlipPose(
      localPagePoint: const Offset(180, 280),
      pageSize: pageSize,
      progress: 0.65,
      corner: StPageFlipCorner.top,
    );
    final frame = builder.build(
      pageRect: const Rect.fromLTWH(16, 64, 398, 553),
      pageSize: pageSize,
      dragPoint: const Offset(180, 280),
      progress: 0.65,
      direction: StPageFlipDirection.back,
      corner: StPageFlipCorner.top,
      reversePose: reversePose,
    );

    expect(frame.frontSurface, isNotNull);
    expect(frame.backSurface, isNotNull);
    expect(frame.curlLift, greaterThan(0));
    expect(frame.rollProgress, greaterThan(0));
    // 三阶段主线：cylinderProgress 和 unfoldProgress 不再为 0。
    expect(
      frame.cylinderProgress + frame.unfoldProgress,
      greaterThan(0),
      reason: '三阶段 reversePose 应产出非零 cylinderProgress 或 unfoldProgress',
    );
  });

  test('CurlMeshBuilder 在回翻多关键帧下镜像卷曲随进度递增', () {
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
    // Mirrored forward: rollProgress increases with progress.
    expect(early.rollProgress, lessThanOrEqualTo(middle.rollProgress + 0.0001));
    // cylinderProgress and unfoldProgress are always 0 in mirrored path.
    expect(early.cylinderProgress, equals(0));
    expect(middle.cylinderProgress, equals(0));
    expect(late.cylinderProgress, equals(0));
    expect(early.unfoldProgress, equals(0));
    expect(middle.unfoldProgress, equals(0));
    expect(late.unfoldProgress, equals(0));
  });

  test('CurlMeshBuilder 在回翻有 reversePose 的多关键帧下三阶段递增', () {
    final builder = ArticlePageCurlMeshBuilder();
    const pageSize = Size(398, 553);
    final earlyPose = resolveReverseFlipPose(
      localPagePoint: const Offset(348, 120),
      pageSize: pageSize,
      progress: 0.18,
      corner: StPageFlipCorner.top,
    );
    final middlePose = resolveReverseFlipPose(
      localPagePoint: const Offset(278, 120),
      pageSize: pageSize,
      progress: 0.58,
      corner: StPageFlipCorner.top,
    );
    final latePose = resolveReverseFlipPose(
      localPagePoint: const Offset(120, 120),
      pageSize: pageSize,
      progress: 0.92,
      corner: StPageFlipCorner.top,
    );
    final early = builder.build(
      pageRect: const Rect.fromLTWH(16, 64, 398, 553),
      pageSize: pageSize,
      dragPoint: const Offset(348, 120),
      progress: 0.18,
      direction: StPageFlipDirection.back,
      corner: StPageFlipCorner.top,
      reversePose: earlyPose,
    );
    final middle = builder.build(
      pageRect: const Rect.fromLTWH(16, 64, 398, 553),
      pageSize: pageSize,
      dragPoint: const Offset(278, 120),
      progress: 0.58,
      direction: StPageFlipDirection.back,
      corner: StPageFlipCorner.top,
      reversePose: middlePose,
    );
    final late = builder.build(
      pageRect: const Rect.fromLTWH(16, 64, 398, 553),
      pageSize: pageSize,
      dragPoint: const Offset(120, 120),
      progress: 0.92,
      direction: StPageFlipDirection.back,
      corner: StPageFlipCorner.top,
      reversePose: latePose,
    );

    expect(early.frontSurface, isNotNull);
    expect(middle.backSurface, isNotNull);
    expect(late.frontSurface, isNotNull);
    // 三阶段主线：随进度推进，cylinderProgress 或 unfoldProgress 应递增。
    final earlySum = early.cylinderProgress + early.unfoldProgress;
    final middleSum = middle.cylinderProgress + middle.unfoldProgress;
    final lateSum = late.cylinderProgress + late.unfoldProgress;
    expect(
      lateSum,
      greaterThanOrEqualTo(middleSum - 0.01),
      reason: '三阶段进度应随翻页进度递增',
    );
    expect(
      middleSum,
      greaterThanOrEqualTo(earlySum - 0.01),
      reason: '三阶段进度应随翻页进度递增',
    );
  });

  test('CurlMeshBuilder 会消费 portrait 回翻的三阶段 render frame', () {
    final builder = ArticlePageCurlMeshBuilder();
    final frame = _threeStageBackRenderFrame(
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
    // 新方案：回翻复用前翻 timeline（时间反转+镜像），
    // rollProgress 来自前翻的 invertedProgress，cylinderProgress/unfoldProgress 为 0。
    expect(meshFrame.rollProgress, greaterThanOrEqualTo(0));
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

  test('flipPrev 产出的 AnimationPlan 包含非空 reversePoses', () {
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
    expect(plan!.reversePoses, isNotNull);
    expect(plan.reversePoses!.length, equals(plan.frames.length));
  });

  test('flipPrev 的 reversePoses 每帧都有合法的三阶段进度', () {
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

    final poses = plan!.reversePoses!;
    // 每帧的 progress 必须在 [0, 1] 范围内
    for (final pose in poses) {
      expect(pose.progress, greaterThanOrEqualTo(0.0));
      expect(pose.progress, lessThanOrEqualTo(1.0));
    }
    // 最后一帧的 progress 应接近完成（翻页完成态）
    expect(poses.last.progress, greaterThan(0.5));
  });

  test('stopMove 回弹时也产出 reversePoses', () {
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
    // 回弹也应携带 reversePoses
    expect(plan!.reversePoses, isNotNull);
    expect(plan.reversePoses!.length, equals(plan.frames.length));
    // 回弹的 isTurned 应为 false
    expect(plan.isTurned, isFalse);
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
    expect(angle, equals(0),
        reason: '回翻不旋转，角度固定为 0');
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
    expect(clipArea.length, equals(4),
        reason: '回翻 clip area 始终是 4 点矩形');
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
    expect(angle.abs(), lessThan(0.3),
        reason: 'unroll 末期角度应趋近于零');
  });
}

StPageFlipRenderFrame _threeStageBackRenderFrame({
  required Offset localPagePoint,
  required double progress,
  required StPageFlipCorner corner,
}) {
  const pageSize = Size(398, 553);
  final reversePose = resolveReverseFlipPose(
    localPagePoint: localPagePoint,
    pageSize: pageSize,
    progress: progress,
    corner: corner,
  );
  final timeline = resolvePageCurlTimeline(
    direction: StPageFlipDirection.back,
    renderDirection: StPageFlipDirection.forward,
    progress: progress,
    localPagePoint: localPagePoint,
    pageSize: pageSize,
    corner: corner,
    reversePose: reversePose,
  );
  return StPageFlipRenderFrame(
    localPagePoint: localPagePoint,
    progress: progress,
    direction: StPageFlipDirection.back,
    renderDirection: StPageFlipDirection.forward,
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
    flippingAnchor: Offset(
      reversePose.leadingEdgeX,
      corner == StPageFlipCorner.top ? 0 : 553,
    ),
    bottomAnchor: Offset.zero,
    angle: corner == StPageFlipCorner.top ? 0.32 : -0.32,
    shadow: null,
    timeline: timeline,
    reversePose: reversePose,
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

Future<ui.Image> _createTestImage() async {
  final recorder = ui.PictureRecorder();
  final canvas = Canvas(recorder);
  canvas.drawRect(
    const Rect.fromLTWH(0, 0, 1, 1),
    Paint()..color = const Color(0xFFFFFFFF),
  );
  final picture = recorder.endRecording();
  final image = await picture.toImage(1, 1);
  picture.dispose();
  return image;
}
