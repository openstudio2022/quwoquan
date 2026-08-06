import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/gestures/immersive_gesture_intent_controller.dart';

ImmersiveGestureCapabilities _caps({
  int pageCount = 3,
  int currentPageIndex = 1,
  bool canFlipForward = true,
  bool canFlipBack = true,
  bool allowVerticalSwitch = true,
  bool allowBoundaryRubberBand = true,
}) {
  return ImmersiveGestureCapabilities(
    pageCount: pageCount,
    currentPageIndex: currentPageIndex,
    canFlipForward: canFlipForward,
    canFlipBack: canFlipBack,
    allowVerticalSwitch: allowVerticalSwitch,
    allowBoundaryRubberBand: allowBoundaryRubberBand,
  );
}

void main() {
  test('6px 内只过滤手指抖动，不锁定任何方向', () {
    final controller = ImmersiveGestureIntentController();
    controller.begin(position: Offset.zero, capabilities: _caps());

    final intent = controller.update(
      position: const Offset(4, 3),
      capabilities: _caps(),
    );

    expect(intent, ImmersiveGestureIntent.undecided);
    expect(controller.phase, ImmersiveGestureIntentPhase.tracking);
    expect(controller.shouldHoldVerticalScroll, isFalse);
  });

  test('12px 后横向斜拖可翻时锁定前翻并冻结竖向滚动', () {
    final controller = ImmersiveGestureIntentController();
    controller.begin(position: Offset.zero, capabilities: _caps());

    final intent = controller.update(
      position: const Offset(-18, -12),
      capabilities: _caps(),
    );

    expect(intent, ImmersiveGestureIntent.pageFlipForward);
    expect(controller.phase, ImmersiveGestureIntentPhase.locked);
    expect(controller.shouldHoldVerticalScroll, isTrue);
  });

  test('前后翻方向只由累计 dx 决定，左滑前翻、右滑后翻', () {
    final leftSwipe = ImmersiveGestureIntentController();
    leftSwipe.begin(position: const Offset(240, 300), capabilities: _caps());
    expect(
      leftSwipe.update(position: const Offset(218, 298), capabilities: _caps()),
      ImmersiveGestureIntent.pageFlipForward,
    );

    final rightSwipe = ImmersiveGestureIntentController();
    rightSwipe.begin(position: const Offset(240, 300), capabilities: _caps());
    expect(
      rightSwipe.update(
        position: const Offset(262, 302),
        capabilities: _caps(),
      ),
      ImmersiveGestureIntent.pageFlipBack,
    );
  });

  test('preview 阶段不冻结父级竖向滚动，避免斜向慢拖误以为页面卡死', () {
    final controller = ImmersiveGestureIntentController();
    controller.begin(position: Offset.zero, capabilities: _caps());

    final intent = controller.update(
      position: const Offset(-9, -7),
      capabilities: _caps(),
    );

    expect(intent, ImmersiveGestureIntent.undecided);
    expect(controller.phase, ImmersiveGestureIntentPhase.previewing);
    expect(controller.previewIntent, ImmersiveGestureIntent.pageFlipForward);
    expect(controller.shouldHoldVerticalScroll, isFalse);
  });

  test('纵向优势斜拖锁定上下切换，不允许子级翻页继续抢跑', () {
    final controller = ImmersiveGestureIntentController();
    controller.begin(position: Offset.zero, capabilities: _caps());

    final intent = controller.update(
      position: const Offset(-12, -18),
      capabilities: _caps(),
    );

    expect(intent, ImmersiveGestureIntent.verticalWorkSwitch);
    expect(controller.isVerticalLocked, isTrue);
    expect(controller.shouldIgnorePageFlipInput, isTrue);
    expect(controller.shouldHoldVerticalScroll, isFalse);
  });

  test('超过 18px 的模糊拖动按优势轴兜底，不让页面看起来卡死', () {
    final controller = ImmersiveGestureIntentController();
    controller.begin(position: Offset.zero, capabilities: _caps());

    final intent = controller.update(
      position: const Offset(-23, -22),
      capabilities: _caps(),
    );

    expect(intent, ImmersiveGestureIntent.pageFlipForward);
    expect(controller.phase, ImmersiveGestureIntentPhase.locked);
  });

  test('不可翻方向默认让位给上下切换', () {
    final controller = ImmersiveGestureIntentController();
    final caps = _caps(
      pageCount: 1,
      currentPageIndex: 0,
      canFlipForward: false,
      canFlipBack: false,
    );
    controller.begin(position: Offset.zero, capabilities: caps);

    final intent = controller.update(
      position: const Offset(-18, -12),
      capabilities: caps,
    );

    expect(intent, ImmersiveGestureIntent.verticalWorkSwitch);
    expect(controller.shouldIgnorePageFlipInput, isTrue);
  });

  test('强横向边界手势保留边界回弹并冻结竖向滚动', () {
    final controller = ImmersiveGestureIntentController();
    final caps = _caps(canFlipForward: false, allowVerticalSwitch: true);
    controller.begin(position: Offset.zero, capabilities: caps);

    final intent = controller.update(
      position: const Offset(-40, -10),
      capabilities: caps,
    );

    expect(intent, ImmersiveGestureIntent.boundaryRubberBand);
    expect(controller.shouldHoldVerticalScroll, isTrue);
  });

  test('一次未提交后，1.2s 内同方向第二次拖动会更快锁定', () {
    var now = DateTime(2026, 7, 1, 12);
    final controller = ImmersiveGestureIntentController(now: () => now);
    controller.begin(position: Offset.zero, capabilities: _caps());
    controller.update(position: const Offset(-8, -7), capabilities: _caps());
    controller.finish();

    now = now.add(const Duration(milliseconds: 600));
    controller.begin(position: Offset.zero, capabilities: _caps());
    final intent = controller.update(
      position: const Offset(-7, -7),
      capabilities: _caps(),
    );

    expect(intent, ImmersiveGestureIntent.pageFlipForward);
    expect(controller.phase, ImmersiveGestureIntentPhase.locked);
  });
}
