// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-002

import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/home_feed_video_focus_coordinator.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/home_multi_form_feed.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/public/home_feed_video_autoplay_policy.dart';

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';

class _ScrollSignal extends ValueNotifier<HomeFeedVideoScrollSignalForTesting> {
  _ScrollSignal() : super(HomeFeedVideoScrollSignalForTesting.initial());

  int listeners = 0;
  int reads = 0;

  @override
  HomeFeedVideoScrollSignalForTesting get value {
    reads++;
    return super.value;
  }

  @override
  void addListener(VoidCallback listener) {
    listeners++;
    super.addListener(listener);
  }

  @override
  void removeListener(VoidCallback listener) {
    listeners--;
    super.removeListener(listener);
  }

  void send({bool scrolling = false, DateTime? highVelocityAt}) {
    final previous = super.value;
    value = previous.copyWith(
      isDragging: scrolling,
      isScrolling: scrolling,
      velocityPxPerSecond: scrolling ? 1400 : 0,
      lastHighVelocityAt: highVelocityAt,
    );
  }
}

class _FocusCoordinator extends HomeFeedVideoFocusCoordinator {
  int listeners = 0;
  int reports = 0;

  @override
  void addListener(VoidCallback listener) {
    listeners++;
    super.addListener(listener);
  }

  @override
  void removeListener(VoidCallback listener) {
    listeners--;
    super.removeListener(listener);
  }

  @override
  void report(String id, double visibleFraction) {
    reports++;
    super.report(id, visibleFraction);
  }
}

class _PlaybackProbe {
  bool initialize = false;
  bool autoPlay = false;
  int builds = 0;

  Widget build(bool initialize, bool autoPlay) {
    this.initialize = initialize;
    this.autoPlay = autoPlay;
    builds++;
    return const SizedBox.expand();
  }
}

// 在稳定 slot 之间转移同一个真实 gate，检查点位于 donor 离树后、
// receiver 重挂载前；不直接调用 State 生命周期来伪造 inactive 状态。
class _MoveHarness extends StatefulWidget {
  const _MoveHarness({super.key, required this.gate, this.sibling});

  final Widget gate;
  final Widget? sibling;

  @override
  State<_MoveHarness> createState() => _MoveHarnessState();
}

class _MoveHarnessState extends State<_MoveHarness> {
  int slot = 0;
  VoidCallback? checkpoint;
  bool checkpointInLayout = false;

  void move(int next, {VoidCallback? during, bool inLayout = false}) {
    setState(() {
      slot = next;
      checkpoint = during;
      checkpointInLayout = inLayout;
    });
  }

  Widget _checkpoint(int index) {
    if (index == (slot > 0 ? slot - 1 : 0)) {
      final callback = checkpoint;
      checkpoint = null;
      callback?.call();
    }
    return const SizedBox.shrink();
  }

  @override
  Widget build(BuildContext context) => Column(
    children: [
      for (var index = 0; index < 4; index++) ...[
        SizedBox(
          height: 120,
          child: Builder(
            builder: (_) => slot == index ? widget.gate : const SizedBox(),
          ),
        ),
        if (checkpointInLayout)
          LayoutBuilder(builder: (_, _) => _checkpoint(index))
        else
          Builder(builder: (_) => _checkpoint(index)),
      ],
      if (widget.sibling != null) SizedBox(height: 120, child: widget.sibling),
    ],
  );
}

Future<void> _mount(
  WidgetTester tester, {
  required GlobalKey<_MoveHarnessState> host,
  required GlobalKey gateKey,
  required _ScrollSignal signal,
  required _FocusCoordinator focus,
  required _PlaybackProbe playback,
  Widget? sibling,
}) => tester.pumpWidget(
  ProviderScope(
    overrides: sealedCloudBoundaryOverrides(),
    child: Directionality(
      textDirection: TextDirection.ltr,
      child: MediaQuery(
        data: const MediaQueryData(size: Size(800, 600)),
        child: _MoveHarness(
          key: host,
          gate: homeFeedVideoAutoPlayGateForTesting(
            key: gateKey,
            videoId: 'a',
            scrollSignal: signal,
            coordinator: focus,
            now: tester.binding.clock.now,
            builder: playback.build,
          ),
          sibling: sibling,
        ),
      ),
    ),
  ),
);

Future<void> _qualify(WidgetTester tester) async {
  await tester.pump(homeFeedVideoAutoPlayMinStableVisibleDuration);
  await tester.pump();
}

void main() {
  testWidgets('deactivate 未 dispose 时滚动通知不读取 inactive renderObject', (
    tester,
  ) async {
    final host = GlobalKey<_MoveHarnessState>();
    final gateKey = GlobalKey();
    final signal = _ScrollSignal();
    final focus = _FocusCoordinator();
    final playback = _PlaybackProbe();
    await _mount(
      tester,
      host: host,
      gateKey: gateKey,
      signal: signal,
      focus: focus,
      playback: playback,
    );
    final state = gateKey.currentState!;
    var sawInactive = false;
    host.currentState!.move(
      -1,
      inLayout: true,
      during: () {
        expect(state.mounted, isTrue);
        expect((gateKey.currentContext! as Element).debugIsActive, isFalse);
        sawInactive = true;
        signal.send(scrolling: true);
        expect(signal.listeners, 0);
        expect(focus.listeners, 0);
        expect(focus.candidateCount, 0);
      },
    );
    await tester.pump();
    expect(sawInactive, isTrue);
    expect(tester.takeException(), isNull);
    expect(state.mounted, isFalse);
    await tester.pump(const Duration(seconds: 1));
    expect(focus.candidateCount, 0);
    signal.dispose();
    focus.dispose();
  });

  testWidgets('同 State 重挂载恢复单份订阅且连续驻留从零开始', (tester) async {
    final host = GlobalKey<_MoveHarnessState>();
    final gateKey = GlobalKey();
    final signal = _ScrollSignal();
    final focus = _FocusCoordinator();
    final playback = _PlaybackProbe();
    await _mount(
      tester,
      host: host,
      gateKey: gateKey,
      signal: signal,
      focus: focus,
      playback: playback,
    );
    await _qualify(tester);
    expect(playback.autoPlay, isTrue);
    final state = gateKey.currentState!;
    for (final slot in [1, 2, 3]) {
      host.currentState!.move(
        slot,
        during: () {
          expect((gateKey.currentContext! as Element).debugIsActive, isFalse);
          expect(state.mounted, isTrue);
          expect(signal.listeners, 0);
          expect(focus.listeners, 0);
          expect(focus.candidateCount, 0);
          signal.send();
        },
      );
      await tester.pump();
      expect(gateKey.currentState, same(state));
      expect(signal.listeners, 1);
      expect(focus.listeners, 1);
      expect(playback.autoPlay, isFalse);
      await tester.pump(
        homeFeedVideoAutoPlayMinStableVisibleDuration -
            const Duration(milliseconds: 1),
      );
      expect(focus.candidateCount, 0);
      await tester.pump(const Duration(milliseconds: 1));
      await tester.pump();
      expect(playback.autoPlay, isTrue);
      expect(focus.candidateCount, 1);
      expect(tester.takeException(), isNull);
    }
    await tester.pumpWidget(const SizedBox());
    expect(signal.listeners, 0);
    expect(focus.listeners, 0);
    signal.dispose();
    focus.dispose();
  });

  testWidgets('旧驻留 timer 和排队帧测量不能跨重挂载 generation', (tester) async {
    final host = GlobalKey<_MoveHarnessState>();
    final gateKey = GlobalKey();
    final signal = _ScrollSignal();
    final focus = _FocusCoordinator();
    final playback = _PlaybackProbe();
    await _mount(
      tester,
      host: host,
      gateKey: gateKey,
      signal: signal,
      focus: focus,
      playback: playback,
    );
    await tester.pump(const Duration(milliseconds: 100));
    signal.send(); // 旧 generation 的测量已排队。
    final reads = signal.reads;
    host.currentState!.move(1);
    await tester.pump();
    expect(signal.reads, reads + 1, reason: '只有新 generation 的合并测量执行，旧帧回调无权读取');
    await tester.pump(const Duration(milliseconds: 60));
    await tester.pump();
    expect(focus.candidateCount, 0, reason: '离树前的 100ms 驻留和 timer 不得授予新代播放资格');
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pump();
    expect(playback.autoPlay, isTrue);
    signal.send(highVelocityAt: tester.binding.clock.now());
    await tester.pump();
    host.currentState!.move(-1);
    await tester.pump();
    final reports = focus.reports;
    await tester.pump(homeFeedVideoFastScrollCooldown);
    await tester.pump();
    expect(focus.reports, reports);
    expect(focus.candidateCount, 0);
    expect(tester.takeException(), isNull);
    signal.dispose();
    focus.dispose();
  });

  testWidgets('滚动信号合并帧后测量且开始滚动的暂停不等测量', (tester) async {
    final host = GlobalKey<_MoveHarnessState>();
    final gateKey = GlobalKey();
    final signal = _ScrollSignal();
    final focus = _FocusCoordinator();
    final playback = _PlaybackProbe();
    await _mount(
      tester,
      host: host,
      gateKey: gateKey,
      signal: signal,
      focus: focus,
      playback: playback,
    );
    await _qualify(tester);
    expect(playback.autoPlay, isTrue);
    final reports = focus.reports;
    for (var i = 0; i < 5; i++) {
      signal.send(scrolling: true);
    }
    expect(focus.reports, reports, reason: '滚动通知不得同步测量并重新申报几何');
    await tester.pump();
    expect(
      playback.autoPlay,
      isFalse,
      reason: '首个 build 已消费暂停，不能等帧后测量才 setState',
    );
    expect(focus.reports, reports + 1);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
    signal.dispose();
    focus.dispose();
  });

  testWidgets('deactivate 焦点撤回同步通知兄弟但不在 build 更新播放态', (tester) async {
    final host = GlobalKey<_MoveHarnessState>();
    final gateKey = GlobalKey();
    final signal = _ScrollSignal();
    final focus = _FocusCoordinator();
    final playback = _PlaybackProbe();
    final sibling = _PlaybackProbe();
    await _mount(
      tester,
      host: host,
      gateKey: gateKey,
      signal: signal,
      focus: focus,
      playback: playback,
      sibling: homeFeedVideoAutoPlayGateForTesting(
        key: GlobalKey(),
        videoId: 'b',
        scrollSignal: signal,
        coordinator: focus,
        now: tester.binding.clock.now,
        builder: sibling.build,
      ),
    );
    await _qualify(tester);
    expect(focus.activeId, 'a');
    expect(focus.candidateCount, 2);
    expect(playback.autoPlay, isTrue);
    expect(sibling.autoPlay, isFalse);
    host.currentState!.move(-1);
    await tester.pump();
    expect(tester.takeException(), isNull);
    expect(focus.activeId, 'b');
    await tester.pump();
    expect(sibling.autoPlay, isTrue);
    expect(focus.candidateCount, 1);
    expect(signal.listeners, 1);
    expect(focus.listeners, 1);
    await tester.pumpWidget(const SizedBox());
    expect(focus.candidateCount, 0);
    signal.dispose();
    focus.dispose();
  });

  testWidgets('layout 中焦点交接不触发 setState during layout', (tester) async {
    final host = GlobalKey<_MoveHarnessState>();
    final gateKey = GlobalKey();
    final signal = _ScrollSignal();
    final focus = _FocusCoordinator();
    final playback = _PlaybackProbe();
    await _mount(
      tester,
      host: host,
      gateKey: gateKey,
      signal: signal,
      focus: focus,
      playback: playback,
    );
    await _qualify(tester);
    expect(playback.autoPlay, isTrue);
    host.currentState!.move(
      0,
      inLayout: true,
      during: () {
        focus.withdraw('a');
        signal.send(scrolling: true);
      },
    );
    await tester.pump();
    expect(tester.takeException(), isNull);
    await tester.pump();
    expect(playback.autoPlay, isFalse);
    await tester.pumpWidget(const SizedBox());
    signal.dispose();
    focus.dispose();
  });
}
