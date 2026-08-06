/// user_acceptance Patrol：环境注入的视频播放 canary。
library;

import 'package:flutter/widgets.dart';
import 'package:flutter/rendering.dart' show RenderObject, RenderParagraph;
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/immersive_engagement_bar.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import '../../../support/runtime/patrol/patrol_test_support.dart';

import '../../../support/runtime/patrol/patrol_environment_harness.dart';

const _videoWorkId = String.fromEnvironment('VIDEO_PLAYBACK_CANARY_WORK_ID');
const _hourVideoWorkId = String.fromEnvironment(
  'VIDEO_PLAYBACK_HOUR_CANARY_WORK_ID',
);
const _requireNativePlaybackSignals = bool.fromEnvironment(
  'REQUIRE_NATIVE_VIDEO_PLAYBACK_SIGNALS',
);
const _timelineKey = ValueKey<String>('video-playback-timeline-workBrowser');
const _trackKey = ValueKey<String>('video-playback-timeline-track');
const _durationKey = ValueKey<String>('works-video-transient-duration');
const _captionKey = ValueKey<String>('works-caption-rail');
const _nativeFirstFrameKey = ValueKey<String>(
  'video-player-native-first-frame',
);
const _nativeSeekSettledKeyPrefix = 'video-player-native-seek-settled-';
const _videoProbeKeys = <ValueKey<String>>[
  ValueKey<String>('works-video-stage-$_videoWorkId-0'),
  ValueKey<String>('works-video-$_videoWorkId-0'),
  ValueKey<String>('home-video-player-$_videoWorkId'),
];

void main() {
  patrolTest(
    'environment_video_playback_canary',
    tags: ['user-acceptance', 'environment-smoke', 'video-playback'],
    skip: !kRunPatrolAcceptance,
    config: PatrolTesterConfig(
      visibleTimeout: const Duration(seconds: 12),
      printLogs: true,
    ),
    ($) async {
      await launchEnvironmentPatrolApp($);
      expect(
        _videoWorkId.trim(),
        isNotEmpty,
        reason:
            'environment Patrol requires an injected video playback canary work id',
      );

      await patrolGoTo(
        $,
        AppRoutePaths.workBrowser(
          workId: _videoWorkId,
          source: 'environmentVideoPlaybackCanary',
        ),
      );
      final videoStageKey = await _waitForAnyKey($, _videoProbeKeys);
      expect(
        videoStageKey,
        isNotNull,
        reason: 'configured video canary stage should render',
      );
      await $(find.byKey(videoStageKey!)).tap();
      await $.pump(const Duration(milliseconds: 500));
      final playerReady = await _waitForAnyKey($, const <ValueKey<String>>[
        ValueKey<String>('video-player-ready'),
      ]);
      final playerError = find
          .byKey(const ValueKey<String>('video-player-error'))
          .evaluate()
          .isNotEmpty;
      expect(
        playerReady,
        isNotNull,
        reason: playerError
            ? 'native video player entered its explicit error state'
            : 'native video player must reach ready state',
      );
      expect(
        find.byKey(const ValueKey<String>('video-player-error')).evaluate(),
        isEmpty,
        reason: 'configured video canary must not enter the error state',
      );
      expect(
        find.byKey(_timelineKey).evaluate(),
        isNotEmpty,
        reason: '125 秒 canary 必须使用共享 WorkBrowser 时间轴',
      );
      expect(
        find.text('2:05').evaluate(),
        isNotEmpty,
        reason: '播放器必须读取服务端权威 125 秒时长',
      );
      _expectTimelineSemantics(valueSuffix: '/ 2:05');
      await _requireNativeFirstFrameEvidence($);
      await _expectBottomStackGeometryAndExpiry($);

      await _scrubTimeline(
        $,
        startFraction: 0.08,
        startLabel: '0:10 / 2:05',
        endFraction: 0.60,
        endLabel: '1:15 / 2:05',
        targetPositionMs: 75000,
      );
      await _scrubTimeline(
        $,
        startFraction: 0.60,
        startLabel: '1:15 / 2:05',
        endFraction: 0.96,
        endLabel: '2:00 / 2:05',
        targetPositionMs: 120000,
      );
      if (_requireNativePlaybackSignals) {
        // 环境 runner 只从设备所属的 Patrol 日志解析此行，不能由 stackctl 环境变量伪造。
        debugPrint(
          'QWQ_VIDEO_PLAYBACK_EVIDENCE '
          '{"nativeFirstFrame":true,"nativeSeekSettled":true}',
        );
      }
    },
  );

  patrolTest(
    'environment_hour_boundary_video_playback_canary',
    tags: ['user-acceptance', 'environment-smoke', 'video-playback'],
    skip: !kRunPatrolAcceptance || _hourVideoWorkId.isEmpty,
    config: PatrolTesterConfig(
      visibleTimeout: const Duration(seconds: 12),
      printLogs: true,
    ),
    ($) async {
      await launchEnvironmentPatrolApp($);
      await patrolGoTo(
        $,
        AppRoutePaths.workBrowser(
          workId: _hourVideoWorkId,
          source: 'environmentHourVideoPlaybackCanary',
        ),
      );
      final stageKey = await _waitForAnyKey($, <ValueKey<String>>[
        ValueKey<String>('works-video-stage-$_hourVideoWorkId-0'),
        ValueKey<String>('works-video-$_hourVideoWorkId-0'),
      ]);
      expect(stageKey, isNotNull);
      await $(find.byKey(stageKey!)).tap();
      await $.pump(const Duration(milliseconds: 500));
      expect(find.text('59:55').evaluate(), isNotEmpty);

      await _scrubTimeline(
        $,
        startFraction: 10 / 3595,
        startLabel: '0:10 / 59:55',
        endFraction: 1800 / 3595,
        endLabel: '30:00 / 59:55',
        targetPositionMs: 1800000,
      );
      await _scrubTimeline(
        $,
        startFraction: 3300 / 3595,
        startLabel: '55:00 / 59:55',
        endFraction: 3570 / 3595,
        endLabel: '59:30 / 59:55',
        targetPositionMs: 3570000,
      );
    },
  );
}

Future<void> _expectBottomStackGeometryAndExpiry(
  PatrolIntegrationTester $,
) async {
  final timeline = find.byKey(_timelineKey);
  final track = find.byKey(_trackKey);
  final duration = find.byKey(_durationKey);
  final caption = find.byKey(_captionKey);
  final toolbar = find.byType(ImmersiveEngagementBar);
  final engagementRail = find.byKey(
    const ValueKey<String>('immersive-engagement-rail'),
  );
  expect(timeline.evaluate(), isNotEmpty);
  expect(track.evaluate(), isNotEmpty);
  expect(duration.evaluate(), isNotEmpty);
  expect(caption.evaluate(), isNotEmpty);
  expect(toolbar.evaluate(), isNotEmpty);
  expect(engagementRail.evaluate(), isNotEmpty);

  final timelineRect = $.tester.getRect(timeline.first);
  final trackRect = $.tester.getRect(track.first);
  final captionRect = $.tester.getRect(caption.first);
  final durationRect = $.tester.getRect(duration.first);
  expect(
    timelineRect.bottom,
    closeTo($.tester.getRect(toolbar.first).top, 1),
    reason: 'WorkBrowser 时间轴热区必须紧贴互动工具栏顶边。',
  );
  expect(
    trackRect.bottom,
    closeTo($.tester.getRect(toolbar.first).top, 1),
    reason: '暂停/拖动态也必须由轨道本体贴栏，不能只让 44dp 热区贴栏。',
  );
  expect(trackRect.width, closeTo(timelineRect.width, 1));
  expect(
    timelineRect.left,
    closeTo($.tester.getRect(engagementRail.first).left, 1),
  );
  expect(
    timelineRect.right,
    closeTo($.tester.getRect(engagementRail.first).right, 1),
  );
  final durationOpacity = $.tester.widget<Opacity>(duration.first).opacity;
  final textCollides = _globalTextPaintRects(
    $.tester,
    caption.first,
  ).any((rect) => rect.inflate(AppSpacing.intraGroupXs).overlaps(durationRect));
  if (textCollides) {
    expect(durationOpacity, 0, reason: '真实文本碰撞时只允许隐藏视觉总时长。');
  } else {
    expect(durationOpacity, 1, reason: '实际字形未碰撞时，入口五秒窗口内应显示总时长。');
  }

  await $.pump(const Duration(seconds: 6));
  expect(
    $.tester.widget<Opacity>(duration.first).opacity,
    0,
    reason: '总时长在首次进入后最多显示五秒。',
  );
  expect($.tester.getRect(timeline.first), timelineRect);
  expect($.tester.getRect(track.first), trackRect);
  expect($.tester.getRect(caption.first), captionRect);
}

List<Rect> _globalTextPaintRects(WidgetTester tester, Finder finder) {
  final root = tester.renderObject<RenderObject>(finder);
  final result = <Rect>[];
  void collect(RenderObject object) {
    if (object is RenderParagraph && object.attached && object.hasSize) {
      final textLength = object.text.toPlainText().length;
      if (textLength > 0) {
        for (final box in object.getBoxesForSelection(
          TextSelection(baseOffset: 0, extentOffset: textLength),
        )) {
          final localRect = box.toRect();
          result.add(
            Rect.fromPoints(
              object.localToGlobal(localRect.topLeft),
              object.localToGlobal(localRect.bottomRight),
            ),
          );
        }
      }
    }
    object.visitChildren(collect);
  }

  collect(root);
  return result;
}

Future<void> _scrubTimeline(
  PatrolIntegrationTester $, {
  required double startFraction,
  required String startLabel,
  required double endFraction,
  required String endLabel,
  required int targetPositionMs,
}) async {
  final timeline = find.byKey(_timelineKey);
  expect(timeline.evaluate(), isNotEmpty);
  final rect = $.tester.getRect(timeline.first);
  final gesture = await $.tester.startGesture(
    Offset(rect.left + rect.width * startFraction, rect.center.dy),
  );
  await $.pump(const Duration(milliseconds: 120));
  expect(find.text(startLabel).evaluate(), isNotEmpty);
  _expectTimelineSemantics(value: startLabel);
  await gesture.moveTo(
    Offset(rect.left + rect.width * endFraction, rect.center.dy),
  );
  await $.pump(const Duration(milliseconds: 180));
  expect(find.text(endLabel).evaluate(), isNotEmpty);
  _expectTimelineSemantics(value: endLabel);
  await gesture.up();
  await $.pump(const Duration(seconds: 2));
  if (_requireNativePlaybackSignals) {
    final nativeSettled = await _waitForAnyKey($, <ValueKey<String>>[
      ValueKey<String>('$_nativeSeekSettledKeyPrefix$targetPositionMs'),
    ]);
    expect(
      nativeSettled,
      isNotNull,
      reason:
          'release seek 必须在 native discontinuity 后由渲染帧确认 settle，'
          '不能以 seekTo Future 或 controller ready 代替',
    );
  }
  expect(
    find.byKey(const ValueKey<String>('video-player-error')).evaluate(),
    isEmpty,
    reason: 'release-only seek 不得把播放器推进失败态',
  );
}

void _expectTimelineSemantics({String? value, String? valueSuffix}) {
  final semantics = find.byWidgetPredicate(
    (widget) =>
        widget is Semantics &&
        widget.properties.label == MediaText.videoPlaybackProgressLabel &&
        widget.properties.onIncrease != null &&
        widget.properties.onDecrease != null &&
        (value == null || widget.properties.value == value) &&
        (valueSuffix == null ||
            (widget.properties.value ?? '').endsWith(valueSuffix)),
  );
  expect(
    semantics.evaluate(),
    isNotEmpty,
    reason: '125 秒 canary 时间轴必须暴露当前值与增减 seek 的无障碍语义',
  );
}

Future<void> _requireNativeFirstFrameEvidence(PatrolIntegrationTester $) async {
  if (!_requireNativePlaybackSignals) {
    return;
  }
  final nativeFirstFrame = await _waitForAnyKey($, const <ValueKey<String>>[
    _nativeFirstFrameKey,
  ]);
  expect(
    nativeFirstFrame,
    isNotNull,
    reason:
        'Android 真机播放必须等待 native rendered-first-frame，不能以 controller ready 代替',
  );
}

Future<Key?> _waitForAnyKey(
  PatrolIntegrationTester $,
  Iterable<Key> keys, {
  Duration timeout = const Duration(seconds: 60),
}) async {
  final deadline = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(deadline)) {
    for (final key in keys) {
      if (find.byKey(key).evaluate().isNotEmpty) {
        return key;
      }
    }
    await $.pump(const Duration(milliseconds: 500));
  }
  return null;
}
