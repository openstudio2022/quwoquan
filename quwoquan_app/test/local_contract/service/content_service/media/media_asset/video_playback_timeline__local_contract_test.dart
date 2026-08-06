import 'package:flutter/material.dart';
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
    expect(
      tester.getBottomLeft(handle).dy,
      closeTo(tester.getBottomLeft(root).dy, 1),
    );
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

    final durationOpacity = tester.widget<Opacity>(
      find.byKey(const ValueKey<String>('works-video-transient-duration')),
    );
    expect(durationOpacity.opacity, 0);
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

    expect(tester.widget<Opacity>(duration).opacity, 0);
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
    expect(scrubText.style?.fontSize, AppTypography.base);
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
    expect(
      tester.getBottomLeft(track).dy,
      closeTo(tester.getBottomLeft(timelineRoot).dy, 1),
      reason: '拖动态 6dp 轨道仍须贴栏，不能随 handle 的 visualExtent 上浮。',
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
