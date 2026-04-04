import 'dart:ui' as ui;

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/ui/content/pageflip/book_layout.dart';
import 'package:quwoquan_app/ui/content/pageflip/controller.dart';
import 'package:quwoquan_app/ui/content/pageflip/curl_light_model.dart';
import 'package:quwoquan_app/ui/content/pageflip/curl_mesh_builder.dart';
import 'package:quwoquan_app/ui/content/pageflip/page_surface_snapshot.dart';
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
    expect(backwardStart.dx, lessThan(centerX));
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
    expect(flipArea.length, 4);
    // 右侧矩形：从 leadingEdgeX 到 pageWidth
    expect(flipArea[0].dx, middlePose.leadingEdgeX);
    expect(flipArea[1].dx, 398);

    // getActiveCorner 应随 leadingEdgeX 动态变化，不再固定为 pageWidth
    final activeCorner = calculation.getActiveCorner();
    expect(activeCorner.dx, middlePose.leadingEdgeX);
    expect(activeCorner.dy, 0); // corner == top

    // getAngle 应为正值（后翻 top corner），不再为 0
    expect(calculation.getAngle(), greaterThan(0));
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

  test('CurlLightModel 会随卷曲进度增强投影与背页调制', () {
    final lightState = resolveArticlePageCurlLightState(
      progress: 0.72,
      foldXNormalized: 0.34,
      curlLift: 0.61,
      rollProgress: 1,
      cylinderProgress: 0,
      unfoldProgress: 0.52,
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
