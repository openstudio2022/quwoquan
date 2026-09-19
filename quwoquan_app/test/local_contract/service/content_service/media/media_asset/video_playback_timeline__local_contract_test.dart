import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/video_playback_session.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/video_playback_timeline.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:video_player/video_player.dart';
import 'package:video_player_platform_interface/video_player_platform_interface.dart';

import '../../../../../support/runtime/platform/media/fake_video_player_platform.dart';

void main() {
  late VideoPlayerPlatform originalPlatform;
  late FakeVideoPlayerPlatform fakePlatform;

  setUp(() {
    originalPlatform = VideoPlayerPlatform.instance;
    fakePlatform = FakeVideoPlayerPlatform();
    VideoPlayerPlatform.instance = fakePlatform;
  });

  tearDown(() {
    VideoPlayerPlatform.instance = originalPlatform;
  });

  // spec_ref: specs/feature-tree/discovery-content/content-display-consistency/video-display-journey/spec.md#gwt-004
  for (final milliseconds in [0, 29999, 30000, 30001]) {
    testWidgets('时间轴阈值 $milliseconds 与触摸停止五秒', (tester) async {
      fakePlatform = FakeVideoPlayerPlatform(
        duration: Duration(milliseconds: milliseconds),
      );
      VideoPlayerPlatform.instance = fakePlatform;
      final controller = (await tester.runAsync(_initializedController))!;
      final session = VideoPlaybackSession()..attach(controller);
      await tester.pumpWidget(
        _TimelineHarness(
          timeline: VideoPlaybackTimeline(
            session: session,
            profile: VideoPlaybackTimelineProfile.workBrowser,
          ),
        ),
      );
      final visual = find.byKey(
        const ValueKey('video-playback-timeline-visibility'),
      );
      final hit = find.byKey(
        const ValueKey('video-playback-timeline-hit-area'),
      );
      expect(tester.getSize(hit).height, greaterThanOrEqualTo(44));
      expect(
        tester.widget<Opacity>(visual).opacity,
        milliseconds > 30000 ? 1 : 0,
      );
      final gesture = await tester.startGesture(tester.getCenter(hit));
      await tester.pump();
      expect(tester.widget<Opacity>(visual).opacity, 1);
      await gesture.moveBy(const Offset(80, 0));
      await tester.pump(const Duration(seconds: 6));
      expect(tester.widget<Opacity>(visual).opacity, 1);
      expect(fakePlatform.seekTargets, isEmpty);
      await gesture.up();
      await tester.pump();
      expect(fakePlatform.seekTargets.length, milliseconds == 0 ? 0 : 1);
      await tester.pump(const Duration(milliseconds: 4999));
      expect(tester.widget<Opacity>(visual).opacity, 1);
      await tester.pump(const Duration(milliseconds: 1));
      expect(
        tester.widget<Opacity>(visual).opacity,
        milliseconds > 30000 ? 1 : 0,
      );
      await tester.pumpWidget(const SizedBox.shrink());
      session
        ..detach(controller)
        ..dispose();
      await tester.runAsync(controller.dispose);
    });
  }

  // spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-024
  testWidgets('横向短视频时间轴服从宿主显隐且不显示常驻时间', (tester) async {
    fakePlatform = FakeVideoPlayerPlatform(
      duration: const Duration(seconds: 20),
    );
    VideoPlayerPlatform.instance = fakePlatform;
    final controller = (await tester.runAsync(_initializedController))!;
    final session = VideoPlaybackSession();
    expect(session.snapshot.mediaAspectRatio, isNull);
    session.attach(controller);
    expect(
      session.snapshot.mediaAspectRatio,
      fakePlatform.size.width / fakePlatform.size.height,
    );
    await tester.pumpWidget(
      _TimelineHarness(
        timeline: VideoPlaybackTimeline(
          session: session,
          profile: VideoPlaybackTimelineProfile.workBrowser,
          externallyControlledVisibility: true,
          showDuration: false,
        ),
      ),
    );
    final visual = find.byKey(
      const ValueKey('video-playback-timeline-visibility'),
    );
    expect(tester.widget<Opacity>(visual).opacity, 1);
    await tester.pump(const Duration(seconds: 6));
    expect(tester.widget<Opacity>(visual).opacity, 1);
    expect(
      find.byKey(const ValueKey('works-video-transient-duration')),
      findsNothing,
    );
    await tester.pumpWidget(const SizedBox.shrink());
    session
      ..detach(controller)
      ..dispose();
    await tester.runAsync(controller.dispose);
  });

  // spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-025
  testWidgets('旋转九十度后真实拖动按局部横轴提交一次seek', (tester) async {
    final controller = (await tester.runAsync(_initializedController))!;
    final session = VideoPlaybackSession()..attach(controller);
    await tester.pumpWidget(
      MaterialApp(
        home: Center(
          child: SizedBox(
            width: 100,
            height: 360,
            child: RotatedBox(
              quarterTurns: 1,
              child: VideoPlaybackTimeline(
                session: session,
                profile: VideoPlaybackTimelineProfile.workBrowser,
                externallyControlledVisibility: true,
                showDuration: false,
              ),
            ),
          ),
        ),
      ),
    );
    final hit = tester.getRect(
      find.byKey(const ValueKey('video-playback-timeline-hit-area')),
    );
    final gesture = await tester.startGesture(
      Offset(hit.center.dx, hit.top + hit.height * 0.2),
    );
    await gesture.moveBy(Offset(0, hit.height * 0.5));
    await tester.pump();
    expect(session.snapshot.isScrubbing, isTrue);
    expect(fakePlatform.seekTargets, isEmpty);
    await gesture.up();
    await tester.pump();
    expect(fakePlatform.seekTargets, hasLength(1));
    await tester.pumpWidget(const SizedBox.shrink());
    session
      ..detach(controller)
      ..dispose();
    await tester.runAsync(controller.dispose);
  });

  testWidgets('纵向不seek、取消不提交、换会话不继承显隐计时器', (tester) async {
    fakePlatform = FakeVideoPlayerPlatform(
      duration: const Duration(seconds: 30),
    );
    VideoPlayerPlatform.instance = fakePlatform;
    final firstController = (await tester.runAsync(_initializedController))!;
    final secondController = (await tester.runAsync(_initializedController))!;
    final first = VideoPlaybackSession()..attach(firstController);
    final second = VideoPlaybackSession()..attach(secondController);
    Future<void> mount(VideoPlaybackSession session) => tester.pumpWidget(
      _TimelineHarness(
        timeline: VideoPlaybackTimeline(
          session: session,
          profile: VideoPlaybackTimelineProfile.workBrowser,
        ),
      ),
    );
    await mount(first);
    final hit = find.byKey(const ValueKey('video-playback-timeline-hit-area'));
    final visual = find.byKey(
      const ValueKey('video-playback-timeline-visibility'),
    );
    var gesture = await tester.startGesture(tester.getCenter(hit));
    await gesture.moveBy(const Offset(0, -100));
    await gesture.up();
    await tester.pump();
    expect(fakePlatform.seekTargets, isEmpty);
    gesture = await tester.startGesture(tester.getCenter(hit));
    await gesture.moveBy(const Offset(-80, 0));
    await tester.pump();
    expect(first.snapshot.isScrubbing, isTrue);
    await gesture.cancel();
    await tester.pump();
    expect(first.snapshot.isScrubbing, isFalse);
    expect(fakePlatform.seekTargets, isEmpty);
    await mount(second);
    expect(tester.widget<Opacity>(visual).opacity, 0);
    await tester.pump(const Duration(seconds: 6));
    expect(tester.widget<Opacity>(visual).opacity, 0);
    await tester.pumpWidget(const SizedBox.shrink());
    first
      ..detach(firstController)
      ..dispose();
    second
      ..detach(secondController)
      ..dispose();
    await tester.runAsync(() async {
      await firstController.dispose();
      await secondController.dispose();
    });
  });

  testWidgets('current position 消费 effectivePosition 且取消 scrub 回稳定态', (
    tester,
  ) async {
    fakePlatform = FakeVideoPlayerPlatform(
      duration: const Duration(seconds: 125),
    );
    VideoPlayerPlatform.instance = fakePlatform;
    final controller = (await tester.runAsync(_initializedController))!;
    final session = VideoPlaybackSession()..attach(controller);
    addTearDown(() async {
      session
        ..detach(controller)
        ..dispose();
      await controller.dispose();
    });
    await session.beginScrub();
    session.updateScrubTarget(const Duration(seconds: 47));
    expect(session.snapshot.effectivePosition, const Duration(seconds: 47));
    expect(
      formatVideoPlaybackDuration(session.snapshot.effectivePosition),
      '0:47',
    );
    await session.endScrub(commit: false);
    expect(session.snapshot.isScrubbing, isFalse);
    expect(session.snapshot.effectivePosition, session.snapshot.position);
    expect(fakePlatform.seekTargets, isEmpty);
  });

  // spec_ref: specs/feature-tree/discovery-content/content-display-consistency/video-display-journey/spec.md#gwt-004
  testWidgets('长作品 idle 零进度无亮线圆点，playing/paused 均低亮度', (tester) async {
    final controller = (await tester.runAsync(_initializedController))!;
    final session = VideoPlaybackSession()..attach(controller);
    await tester.pumpWidget(
      _TimelineHarness(
        timeline: VideoPlaybackTimeline(
          session: session,
          profile: VideoPlaybackTimelineProfile.workBrowser,
          showDuration: false,
        ),
      ),
    );
    final track = find.byKey(const ValueKey('video-playback-timeline-track'));
    final progress = find.byKey(
      const ValueKey('video-playback-timeline-progress'),
    );
    final handle = find.byKey(const ValueKey('video-playback-timeline-handle'));
    double alpha(Finder finder) =>
        (tester.widget<AnimatedContainer>(finder).decoration! as BoxDecoration)
            .color!
            .a;
    expect(alpha(track), closeTo(0.20, 0.01));
    expect(progress, findsNothing);
    expect(handle, findsNothing);
    await tester.runAsync(
      () => session.seekRelative(const Duration(seconds: 25)),
    );
    for (final playing in [true, false]) {
      await tester.runAsync(playing ? session.playByUser : session.pauseByUser);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 200));
      expect(session.snapshot.isPlaying, playing);
      expect(alpha(track), closeTo(0.20, 0.01));
      expect(alpha(progress), closeTo(0.38, 0.01));
      expect(handle, findsNothing);
      final gesture = await tester.startGesture(tester.getCenter(track));
      await tester.pump();
      expect(
        alpha(progress),
        closeTo(0.38, 0.01),
        reason: '触摸揭示不得恢复旧高亮 paused token。',
      );
      await gesture.cancel();
      await tester.pump();
    }
    await tester.pumpWidget(const SizedBox.shrink());
    session
      ..detach(controller)
      ..dispose();
    await tester.runAsync(controller.dispose);
  });

  // spec_ref: specs/feature-tree/discovery-content/content-display-consistency/video-display-journey/spec.md#gwt-004
  for (final milliseconds in [30000, 30001]) {
    for (final playing in [false, true]) {
      for (final commit in [false, true]) {
        testWidgets(
          'chrome 同源隐藏恢复 ${milliseconds}ms playing=$playing end=$commit',
          (tester) async {
            fakePlatform = FakeVideoPlayerPlatform(
              duration: Duration(milliseconds: milliseconds),
            );
            VideoPlayerPlatform.instance = fakePlatform;
            final controller = (await tester.runAsync(_initializedController))!;
            final session = VideoPlaybackSession()..attach(controller);
            await tester.runAsync(
              playing ? session.playByUser : session.pauseByUser,
            );
            final originalIntent = session.snapshot.intent;
            final semantics = tester.ensureSemantics();
            var semanticsDisposed = false;
            addTearDown(() async {
              if (!semanticsDisposed) semantics.dispose();
              session
                ..detach(controller)
                ..dispose();
              await controller.dispose();
            });
            bool hasAttachedLabel(String label) {
              bool containsLabel(SemanticsNode node) {
                if (node.getSemanticsData().label == label) return true;
                var found = false;
                node.visitChildren((child) {
                  found = containsLabel(child);
                  return !found;
                });
                return found;
              }

              final root = tester
                  .binding
                  .renderViews
                  .first
                  .owner
                  ?.semanticsOwner
                  ?.rootSemanticsNode;
              return root != null && containsLabel(root);
            }

            final slots = [
              'caption',
              'currentTime',
              'associations',
              'intersection',
            ];
            var taps = 0;
            await tester.pumpWidget(
              MaterialApp(
                home: Scaffold(
                  body: Center(
                    child: SizedBox(
                      width: 320,
                      child: ListenableBuilder(
                        listenable: session,
                        builder: (context, _) => Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            for (final slot in slots)
                              VideoPlaybackChromeVisibility(
                                key: ValueKey('chrome-$slot'),
                                snapshot: session.snapshot,
                                child: GestureDetector(
                                  onTap: () => taps++,
                                  child: Semantics(
                                    label: slot,
                                    excludeSemantics: true,
                                    child: SizedBox(
                                      width: 320,
                                      height: 40,
                                      child: Text(slot),
                                    ),
                                  ),
                                ),
                              ),
                            VideoPlaybackTimeline(
                              session: session,
                              profile: VideoPlaybackTimelineProfile.workBrowser,
                              showDuration: false,
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            );
            final rectangles = {
              for (final slot in slots)
                slot: tester.getRect(find.byKey(ValueKey('chrome-$slot'))),
            };
            final hit = find.byKey(
              const ValueKey('video-playback-timeline-hit-area'),
            );
            final hitRect = tester.getRect(hit);
            final gesture = await tester.startGesture(
              Offset(hitRect.left + 32, hitRect.center.dy),
            );
            await gesture.moveBy(const Offset(150, 0));
            await tester.pump();
            await tester.pump(const Duration(milliseconds: 200));
            expect(session.snapshot.isScrubbing, isTrue);
            expect(fakePlatform.seekTargets, isEmpty);
            for (final slot in slots) {
              final visibility = tester.widget<Visibility>(
                find.descendant(
                  of: find.byKey(ValueKey('chrome-$slot')),
                  matching: find.byType(Visibility),
                ),
              );
              expect(visibility.visible, isFalse);
              expect(visibility.maintainSemantics, isFalse);
              expect(visibility.maintainInteractivity, isFalse);
              expect(
                tester.getRect(find.byKey(ValueKey('chrome-$slot'))),
                rectangles[slot],
              );
              expect(hasAttachedLabel(slot), isFalse);
              await tester.tapAt(rectangles[slot]!.center);
              expect(taps, 0);
            }
            final track = find.byKey(
              const ValueKey('video-playback-timeline-track'),
            );
            final handle = find.byKey(
              const ValueKey('video-playback-timeline-handle'),
            );
            final progress = find.byKey(
              const ValueKey('video-playback-timeline-progress'),
            );
            final label = tester.widget<Opacity>(
              find.byKey(const ValueKey('video-playback-scrub-time-label')),
            );
            expect(
              (label.child! as Text).style!.fontSize,
              milliseconds > 30000 ? AppTypography.lg : AppTypography.base,
            );
            expect(
              tester.getSize(track).height,
              milliseconds > 30000 ? AppSpacing.sm : AppSpacing.six,
            );
            expect(
              tester.getSize(handle).height,
              milliseconds > 30000 ? AppSpacing.md : AppSpacing.interGroupSm,
            );
            expect(tester.getRect(track).left, hitRect.left);
            expect(tester.getRect(track).right, hitRect.right);
            if (milliseconds > 30000) {
              final expectedVisualCenter =
                  hitRect.bottom - tester.getSize(handle).height / 2;
              expect(
                tester.getCenter(track).dy,
                closeTo(expectedVisualCenter, 0.01),
              );
              expect(
                tester.getCenter(progress).dy,
                closeTo(expectedVisualCenter, 0.01),
              );
              expect(
                tester.getCenter(handle).dy,
                closeTo(expectedVisualCenter, 0.01),
              );
            }
            if (commit) {
              await gesture.up();
            } else {
              await gesture.cancel();
            }
            await tester.pump();
            await tester.pump(const Duration(milliseconds: 200));
            expect(session.snapshot.isScrubbing, isFalse);
            expect(fakePlatform.seekTargets, hasLength(commit ? 1 : 0));
            expect(session.snapshot.intent, originalIntent);
            expect(session.snapshot.isPlaying, playing);
            if (!commit) {
              expect(session.snapshot.effectivePosition, Duration.zero);
            }
            for (final slot in slots) {
              final visibility = tester.widget<Visibility>(
                find.descendant(
                  of: find.byKey(ValueKey('chrome-$slot')),
                  matching: find.byType(Visibility),
                ),
              );
              expect(visibility.visible, isTrue);
              expect(hasAttachedLabel(slot), isTrue);
              expect(
                tester.getRect(find.byKey(ValueKey('chrome-$slot'))),
                rectangles[slot],
              );
            }
            if (milliseconds > 30000) {
              expect(
                (tester.widget<AnimatedContainer>(track).decoration!
                        as BoxDecoration)
                    .color!
                    .a,
                closeTo(0.20, 0.01),
              );
              expect(handle, findsNothing);
            }
            await tester.pumpWidget(const SizedBox.shrink());
            await session.pauseByUser();
            semantics.dispose();
            semanticsDisposed = true;
          },
        );
      }
    }
  }

  // spec_ref: specs/feature-tree/discovery-content/content-display-consistency/video-display-journey/spec.md#gwt-004
  testWidgets('低亮度长作品保留键盘与语义步进 seek', (tester) async {
    final controller = (await tester.runAsync(_initializedController))!;
    final session = VideoPlaybackSession()..attach(controller);
    await session.pauseByUser();
    await tester.pumpWidget(
      _TimelineHarness(
        timeline: VideoPlaybackTimeline(
          session: session,
          profile: VideoPlaybackTimelineProfile.workBrowser,
          showDuration: false,
        ),
      ),
    );
    final hit = find.byKey(const ValueKey('video-playback-timeline-hit-area'));
    Focus.of(tester.element(hit)).requestFocus();
    await tester.pump();
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));
    expect(fakePlatform.seekTargets, [const Duration(seconds: 10)]);
    final semantic = tester.widget<Semantics>(
      find.byWidgetPredicate(
        (widget) =>
            widget is Semantics &&
            widget.properties.label == MediaText.videoPlaybackProgressLabel &&
            widget.properties.onIncrease != null,
      ),
    );
    semantic.properties.onIncrease!();
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));
    expect(fakePlatform.seekTargets, [
      const Duration(seconds: 10),
      const Duration(seconds: 20),
    ]);
    expect(session.snapshot.intent, VideoPlaybackIntent.manualPause);
    expect(session.snapshot.isPlaying, isFalse);
    await tester.pumpWidget(const SizedBox.shrink());
    session
      ..detach(controller)
      ..dispose();
    await tester.runAsync(controller.dispose);
  });

  test('分钟级与小时级权威时长格式稳定', () {
    expect(formatVideoPlaybackDuration(const Duration(seconds: 125)), '2:05');
    expect(formatVideoPlaybackDuration(const Duration(seconds: 3595)), '59:55');
    expect(
      formatVideoPlaybackDuration(const Duration(seconds: 3605)),
      '1:00:05',
    );
  });

  test('时间轴视觉 token 覆盖 2/4/6dp 轨道与 8/12dp 圆点', () {
    final normal = VideoTimelineVisualTokens.resolve(
      VideoTimelineVisualLevel.normal,
    );
    final paused = VideoTimelineVisualTokens.resolve(
      VideoTimelineVisualLevel.paused,
    );
    final scrubbing = VideoTimelineVisualTokens.resolve(
      VideoTimelineVisualLevel.scrubbing,
    );

    expect(normal.trackHeight, AppSpacing.two);
    expect(normal.handleSize, 0);
    expect(paused.trackHeight, AppSpacing.xs);
    expect(paused.handleSize, AppSpacing.sm);
    expect(scrubbing.trackHeight, AppSpacing.six);
    expect(scrubbing.handleSize, AppSpacing.interGroupSm);
    expect(scrubbing.progressAlpha, 1);
  });

  testWidgets('WorkBrowser 时长位于整轨上方且时间轴具有 44dp 热区', (tester) async {
    final controller = (await tester.runAsync(_initializedController))!;
    final session = VideoPlaybackSession()..attach(controller);
    addTearDown(() async {
      session
        ..detach(controller)
        ..dispose();
      await controller.dispose();
    });

    await tester.pumpWidget(
      _TimelineHarness(
        timeline: VideoPlaybackTimeline(
          session: session,
          profile: VideoPlaybackTimelineProfile.workBrowser,
        ),
      ),
    );
    await tester.pump();

    final root = find.byKey(
      const ValueKey<String>('video-playback-timeline-workBrowser'),
    );
    final label = find.byKey(
      const ValueKey<String>('works-video-transient-duration'),
    );
    final track = find.byKey(
      const ValueKey<String>('video-playback-timeline-track'),
    );
    final handle = find.byKey(
      const ValueKey<String>('video-playback-timeline-handle'),
    );
    expect(root, findsOneWidget);
    expect(label, findsOneWidget);
    expect(find.text('2:05'), findsOneWidget);
    expect(tester.getSize(root).height, greaterThanOrEqualTo(44));
    expect(
      tester.getTopRight(label).dx,
      closeTo(tester.getTopRight(track).dx, 1),
    );
    expect(
      tester.getBottomLeft(label).dy,
      lessThan(tester.getTopLeft(track).dy),
    );
    expect(tester.getSize(track).width, closeTo(tester.getSize(root).width, 1));
    expect(
      tester.getBottomLeft(track).dy,
      closeTo(tester.getBottomLeft(root).dy, 1),
      reason: '暂停态轨道本体必须贴住工具栏边界，不能只让 44dp 热区贴底。',
    );
    expect(handle, findsNothing, reason: '静息长视频只保留暗淡细轨。');
    expect(
      find.byWidgetPredicate(
        (widget) =>
            widget is Semantics &&
            widget.properties.label == MediaText.videoPlaybackProgressLabel &&
            widget.properties.onIncrease != null &&
            widget.properties.onDecrease != null,
      ),
      findsOneWidget,
    );
  });

  // spec_ref: specs/feature-tree/discovery-content/content-display-consistency/video-display-journey/spec.md#gwt-004
  testWidgets('首页 ended 保持百分百且末端 thumb 与轨道共中心', (tester) async {
    final controller = (await tester.runAsync(_initializedController))!;
    controller.value = controller.value.copyWith(
      position: controller.value.duration,
      isPlaying: false,
    );
    final session = VideoPlaybackSession()..attach(controller);
    addTearDown(() async {
      session
        ..detach(controller)
        ..dispose();
      await controller.dispose();
    });

    await tester.pumpWidget(
      _TimelineHarness(timeline: InlineFeedPlaybackOverlay(session: session)),
    );
    await tester.pump(const Duration(milliseconds: 200));

    expect(session.snapshot.isEnded, isTrue);
    expect(session.snapshot.progress, 1);
    final track = find.byKey(
      const ValueKey<String>('video-playback-timeline-track'),
    );
    final progress = find.byKey(
      const ValueKey<String>('video-playback-timeline-progress'),
    );
    final handle = find.byKey(
      const ValueKey<String>('video-playback-timeline-handle'),
    );
    expect(
      tester.getCenter(handle).dy,
      closeTo(tester.getCenter(track).dy, 0.01),
    );
    expect(
      tester.getCenter(progress).dy,
      closeTo(tester.getCenter(track).dy, 0.01),
    );
    expect(
      tester.getRect(handle).right,
      closeTo(tester.getRect(track).right, 0.01),
    );
    expect(
      tester.getRect(progress).right,
      closeTo(tester.getRect(track).right, 0.01),
    );
  });

  testWidgets('内容 Post 轨道贴底且总时长位于右端上方并保持被动交互', (tester) async {
    final controller = (await tester.runAsync(_initializedController))!;
    final session = VideoPlaybackSession()..attach(controller);
    addTearDown(() async {
      session
        ..detach(controller)
        ..dispose();
      await controller.dispose();
    });

    await tester.pumpWidget(
      _TimelineHarness(timeline: InlineFeedPlaybackOverlay(session: session)),
    );
    await tester.pump();

    final label = find.byKey(const ValueKey<String>('home-video-duration'));
    final track = find.byKey(
      const ValueKey<String>('video-playback-timeline-track'),
    );
    final handle = find.byKey(
      const ValueKey<String>('video-playback-timeline-handle'),
    );
    final root = find.byKey(
      const ValueKey<String>('video-playback-timeline-inlineFeed'),
    );
    expect(find.text('2:05'), findsOneWidget);
    expect(
      tester.getTopRight(label).dx,
      closeTo(tester.getTopRight(track).dx, 1),
    );
    expect(
      tester.getBottomLeft(label).dy,
      lessThan(tester.getTopLeft(track).dy),
    );
    expect(
      tester.getBottomLeft(handle).dy,
      closeTo(tester.getBottomLeft(root).dy, 1),
    );
    expect(
      find.byWidgetPredicate(
        (widget) => widget is IgnorePointer && widget.ignoring,
      ),
      findsWidgets,
    );
    await tester.pump(const Duration(seconds: 6));
    expect(
      tester.widget<Opacity>(label).opacity,
      1,
      reason: '首页 Post 总时长必须常驻，不得继承 WorkBrowser 的五秒窗口。',
    );
  });

  testWidgets('宿主隐藏视觉时长时立即透明且保留完整进度语义', (tester) async {
    final controller = (await tester.runAsync(_initializedController))!;
    final session = VideoPlaybackSession()..attach(controller);
    addTearDown(() async {
      session
        ..detach(controller)
        ..dispose();
      await controller.dispose();
    });

    await tester.pumpWidget(
      _TimelineHarness(
        timeline: VideoPlaybackTimeline(
          session: session,
          profile: VideoPlaybackTimelineProfile.workBrowser,
          showDuration: false,
        ),
      ),
    );
    await tester.pump();

    expect(
      find.byKey(const ValueKey<String>('works-video-transient-duration')),
      findsNothing,
    );
    expect(
      find.byWidgetPredicate(
        (widget) =>
            widget is Semantics &&
            widget.properties.label == MediaText.videoPlaybackProgressLabel &&
            widget.properties.value == '0:00 / 2:05',
      ),
      findsOneWidget,
    );
  });

  testWidgets('视觉时长隐藏不改变 WorkBrowser 轨道尺寸或位置', (tester) async {
    final controller = (await tester.runAsync(_initializedController))!;
    final session = VideoPlaybackSession()..attach(controller);
    final durationVisible = ValueNotifier<bool>(true);
    addTearDown(() async {
      durationVisible.dispose();
      session
        ..detach(controller)
        ..dispose();
      await controller.dispose();
    });

    await tester.pumpWidget(
      _TimelineHarness(
        timeline: ValueListenableBuilder<bool>(
          valueListenable: durationVisible,
          builder: (context, visible, _) {
            return VideoPlaybackTimeline(
              session: session,
              profile: VideoPlaybackTimelineProfile.workBrowser,
              showDuration: visible,
            );
          },
        ),
      ),
    );
    await tester.pump();

    final root = find.byKey(
      const ValueKey<String>('video-playback-timeline-workBrowser'),
    );
    final track = find.byKey(
      const ValueKey<String>('video-playback-timeline-track'),
    );
    final duration = find.byKey(
      const ValueKey<String>('works-video-transient-duration'),
    );
    final rootRectBefore = tester.getRect(root);
    final trackRectBefore = tester.getRect(track);

    durationVisible.value = false;
    await tester.pump();

    expect(duration, findsNothing);
    expect(tester.getRect(root), rootRectBefore);
    expect(tester.getRect(track), trackRectBefore);
  });

  testWidgets('关闭视觉时间轴仍保留 current/total 无障碍语义', (tester) async {
    final controller = (await tester.runAsync(_initializedController))!;
    final session = VideoPlaybackSession()..attach(controller);
    addTearDown(() async {
      session
        ..detach(controller)
        ..dispose();
      await controller.dispose();
    });

    await tester.pumpWidget(
      _TimelineHarness(
        timeline: VideoPlaybackTimeline(
          session: session,
          profile: VideoPlaybackTimelineProfile.workBrowser,
          showVisuals: false,
        ),
      ),
    );
    await tester.pump();

    expect(
      find.byKey(const ValueKey<String>('video-playback-timeline-track')),
      findsNothing,
    );
    expect(
      find.byWidgetPredicate(
        (widget) =>
            widget is Semantics &&
            widget.properties.label == MediaText.videoPlaybackProgressLabel &&
            widget.properties.value == '0:00 / 2:05',
      ),
      findsOneWidget,
    );
  });

  // spec_ref: specs/feature-tree/discovery-content/content-display-consistency/video-display-journey/spec.md#gwt-004
  testWidgets('thumb 在零至百分百端点按虚拟目标横向定位且不越轨', (tester) async {
    final controller = (await tester.runAsync(_initializedController))!;
    final session = VideoPlaybackSession()..attach(controller);
    addTearDown(() async {
      session
        ..detach(controller)
        ..dispose();
      await controller.dispose();
    });
    await tester.pumpWidget(
      _TimelineHarness(
        timeline: VideoPlaybackTimeline(
          session: session,
          profile: VideoPlaybackTimelineProfile.workBrowser,
          showDuration: false,
        ),
      ),
    );
    await session.beginScrub();
    await tester.pump();
    final track = find.byKey(
      const ValueKey<String>('video-playback-timeline-track'),
    );
    final handle = find.byKey(
      const ValueKey<String>('video-playback-timeline-handle'),
    );
    for (final fraction in <double>[0, 0.25, 0.5, 0.75, 1]) {
      session.updateScrubTarget(
        Duration(
          milliseconds: (controller.value.duration.inMilliseconds * fraction)
              .round(),
        ),
      );
      await tester.pump(const Duration(milliseconds: 200));
      final trackRect = tester.getRect(track);
      final handleRect = tester.getRect(handle);
      final expectedX = (trackRect.left + trackRect.width * fraction).clamp(
        trackRect.left + handleRect.width / 2,
        trackRect.right - handleRect.width / 2,
      );
      expect(tester.getCenter(handle).dx, closeTo(expectedX, 0.01));
      expect(handleRect.left, greaterThanOrEqualTo(trackRect.left));
      expect(handleRect.right, lessThanOrEqualTo(trackRect.right));
    }
    await session.endScrub(commit: false);
  });

  testWidgets('拖动期间只更新虚拟目标，释放时提交一次 seek', (tester) async {
    final controller = (await tester.runAsync(_initializedController))!;
    final session = VideoPlaybackSession()..attach(controller);
    addTearDown(() async {
      session
        ..detach(controller)
        ..dispose();
      await controller.dispose();
    });

    Future<void> pumpTimeline() {
      return tester.pumpWidget(
        _TimelineHarness(
          timeline: ListenableBuilder(
            listenable: session,
            builder: (context, child) {
              return VideoPlaybackTimeline(
                session: session,
                profile: VideoPlaybackTimelineProfile.workBrowser,
                previewBuilder: (context, snapshot, target) {
                  return const SizedBox(
                    key: ValueKey<String>('storyboard-preview-probe'),
                  );
                },
              );
            },
          ),
        ),
      );
    }

    await pumpTimeline();
    final timelineHitArea = find.byKey(
      const ValueKey<String>('video-playback-timeline-hit-area'),
    );
    final rect = tester.getRect(timelineHitArea);
    final gesture = await tester.startGesture(
      Offset(rect.left + rect.width * 0.1, rect.center.dy),
    );
    await gesture.moveTo(Offset(rect.left + rect.width * 0.6, rect.center.dy));
    await tester.pump();

    expect(session.snapshot.isScrubbing, isTrue);
    expect(fakePlatform.seekTargets, isEmpty);
    expect(find.text('1:15 / 2:05'), findsOneWidget);
    final scrubTime = tester.widget<Opacity>(
      find.byKey(const ValueKey<String>('video-playback-scrub-time-label')),
    );
    final scrubText = scrubTime.child! as Text;
    expect(scrubText.style?.fontSize, AppTypography.lg);
    expect(
      find.byKey(const ValueKey<String>('storyboard-preview-probe')),
      findsOneWidget,
    );
    final timelineRoot = find.byKey(
      const ValueKey<String>('video-playback-timeline-workBrowser'),
    );
    final track = find.byKey(
      const ValueKey<String>('video-playback-timeline-track'),
    );
    final handle = find.byKey(
      const ValueKey<String>('video-playback-timeline-handle'),
    );
    expect(
      tester.getCenter(track).dy,
      closeTo(tester.getCenter(handle).dy, 0.01),
      reason: '拖动轨道与 thumb 共中心，视觉范围整体保持贴底。',
    );
    expect(
      tester.getRect(handle).bottom,
      closeTo(tester.getRect(timelineRoot).bottom, 0.01),
    );

    await gesture.up();
    await tester.pumpAndSettle();

    expect(fakePlatform.seekTargets, hasLength(1));
    expect(fakePlatform.seekTargets.single, const Duration(seconds: 75));
    expect(session.snapshot.isScrubbing, isFalse);
  });
}

final class _TimelineHarness extends StatelessWidget {
  const _TimelineHarness({required this.timeline});

  final Widget timeline;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      home: Scaffold(
        backgroundColor: Colors.black,
        body: Center(
          child: SizedBox(
            width: 320,
            height: AppSpacing.minInteractiveSize,
            child: timeline,
          ),
        ),
      ),
    );
  }
}

Future<VideoPlayerController> _initializedController() async {
  final controller = VideoPlayerController.networkUrl(
    Uri.parse('https://media.example.test/video.mp4'),
  );
  await controller.initialize();
  return controller;
}
