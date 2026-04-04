/// L1b Widget 测试：VideoPostCard（视频帖子卡片组件）
///
/// 三维度覆盖：
///   渲染契约  — 视频内容区域渲染；组件树存在
///   数据契约  — duration 字段正确展示
///   错误态渲染 — 空 videoUrl 安全渲染，不崩溃
///
/// mock.yaml dart_func: testVideoCardDurationFormat
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/video_post_dto.g.dart';
import 'package:quwoquan_app/components/content/video_post_card.dart';
import 'package:quwoquan_app/core/test_keys.dart';

// ─── fixtures ─────────────────────────────────────────────────────────────────

const _videoFixture = <String, dynamic>{
  'postId': 'test_video_001',
  'contentType': 'video',
  'authorId': 'user_2',
  'displayName': '视频创作者',
  'authorAvatarUrl': '',
  'authorBackgroundUrl': '',
  'coverUrl': '',
  'thumbnailUrl': '',
  'videoUrl': 'https://example.com/video.mp4',
  'durationMs': 93000,
  'width': 1080,
  'height': 1920,
  'likesCount': 128,
  'commentsCount': 15,
  'savesCount': 9,
  'body': '精彩视频内容',
  'publishedAt': '2025-01-02T00:00:00Z',
};

const _minimalVideoFixture = <String, dynamic>{
  'postId': 'min_video_001',
  'contentType': 'video',
  'authorId': 'u2',
  'displayName': '',
  'authorAvatarUrl': '',
  // Missing videoUrl — should render safely
  'publishedAt': '2025-01-01T00:00:00Z',
};

// ─── helper ───────────────────────────────────────────────────────────────────

void _suppressImageErrors() {
  final original = FlutterError.onError;
  FlutterError.onError = (FlutterErrorDetails details) {
    final msg = details.exception.toString();
    if (msg.contains('HTTP request failed') ||
        msg.contains('NetworkImageLoadException') ||
        msg.contains('precache')) {
      return;
    }
    original?.call(details);
  };
}

Widget _wrapCard(Widget child) {
  return ProviderScope(
    child: ScreenUtilInit(
      designSize: const Size(390, 844),
      builder: (context, _) => MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(child: child),
        ),
      ),
    ),
  );
}

// ── dart_func 实现（mock.yaml: widget_scenarios）──────────────────────────────

/// mock.yaml dart_func: testVideoCardDurationFormat
///
/// 渲染契约：VideoPostCard 接收 duration 字段时正确渲染组件（不崩溃）。
/// 当 VideoPostCard 添加时长格式化显示（"1:33" for 93s）时，
/// 此测试应扩展为断言 find.text("1:33") findsOneWidget。
Future<void> testVideoCardDurationFormat(WidgetTester tester) async {
  _suppressImageErrors();
  await tester.pumpWidget(_wrapCard(
    VideoPostCard(
      post: VideoPostDto.fromMap(_videoFixture),
      onPostTap: (post, _) {},
      onUserTap: (_) {},
    ),
  ));
  await tester.pump();

  // 基础渲染契约：组件不崩溃
  expect(find.byType(VideoPostCard), findsOneWidget,
      reason: 'VideoPostCard 应正常渲染');

  // 播放图标：视频内容区域存在时，应显示播放按钮
  expect(find.byIcon(Icons.play_arrow), findsOneWidget,
      reason: '视频卡片应包含播放图标');

  // 时长格式化：93秒 → "1:33"
  expect(find.byKey(TestKeys.videoDurationText), findsOneWidget,
      reason: '视频卡片应显示时长角标');
  expect(find.text('1:33'), findsOneWidget,
      reason: '93 秒应格式化为 "1:33"');
}

// ─── tests ────────────────────────────────────────────────────────────────────

void main() {
  setUp(_suppressImageErrors);

  // ──────────────────────────────────────────────────────────────────
  // 渲染契约
  // ──────────────────────────────────────────────────────────────────
  group('VideoPostCard — 渲染契约', () {
    testWidgets('renders VideoPostCard widget tree without error', (tester) async {
      await tester.pumpWidget(_wrapCard(
        VideoPostCard(
          post: VideoPostDto.fromMap(_videoFixture),
          onPostTap: (post, _) {},
          onUserTap: (_) {},
        ),
      ));
      await tester.pump();
      expect(find.byType(VideoPostCard), findsOneWidget);
    });

    testWidgets(
      'testVideoCardDurationFormat: duration 字段渲染契约',
      testVideoCardDurationFormat,
    );

    testWidgets('duration badge shows correct MM:SS format', (tester) async {
      await tester.pumpWidget(_wrapCard(
        VideoPostCard(
          post: VideoPostDto.fromMap({..._videoFixture, 'durationMs': 125000}),
          onPostTap: (post, _) {},
          onUserTap: (_) {},
        ),
      ));
      await tester.pump();
      expect(find.text('2:05'), findsOneWidget,
          reason: '125 秒应格式化为 "2:05"');
    });

    testWidgets('duration badge shows H:MM:SS for long video', (tester) async {
      await tester.pumpWidget(_wrapCard(
        VideoPostCard(
          post: VideoPostDto.fromMap({..._videoFixture, 'durationMs': 3723000}),
          onPostTap: (post, _) {},
          onUserTap: (_) {},
        ),
      ));
      await tester.pump();
      expect(find.text('1:02:03'), findsOneWidget,
          reason: '3723 秒应格式化为 "1:02:03"');
    });

    testWidgets('duration badge absent when duration is zero', (tester) async {
      await tester.pumpWidget(_wrapCard(
        VideoPostCard(
          post: VideoPostDto.fromMap({..._videoFixture, 'durationMs': 0}),
          onPostTap: (post, _) {},
          onUserTap: (_) {},
        ),
      ));
      await tester.pump();
      expect(find.byKey(TestKeys.videoDurationText), findsNothing,
          reason: '时长为 0 时不应显示角标');
    });

    testWidgets('durationMs fallback when duration absent', (tester) async {
      final postWithoutDuration = Map<String, dynamic>.from(_videoFixture)
        ..['durationMs'] = 90000;
      await tester.pumpWidget(_wrapCard(
        VideoPostCard(
          post: VideoPostDto.fromMap(postWithoutDuration),
          onPostTap: (post, _) {},
          onUserTap: (_) {},
        ),
      ));
      await tester.pump();
      expect(find.text('1:30'), findsOneWidget,
          reason: '90000ms → 90s → "1:30"');
    });

    testWidgets('renders all optional callbacks', (tester) async {
      await tester.pumpWidget(_wrapCard(
        VideoPostCard(
          post: VideoPostDto.fromMap(_videoFixture),
          onPostTap: (post, _) {},
          onUserTap: (_) {},
          onLike: (_) {},
          onComment: (_) {},
          onShare: (_) {},
          onBookmark: (_) {},
        ),
      ));
      await tester.pump();
      expect(find.byType(VideoPostCard), findsOneWidget);
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 错误态渲染
  // ──────────────────────────────────────────────────────────────────
  group('VideoPostCard — 错误态渲染', () {
    testWidgets('empty videoUrl → renders without crash', (tester) async {
      expect(() async {
        await tester.pumpWidget(_wrapCard(
          VideoPostCard(
            post: VideoPostDto.fromMap(_minimalVideoFixture),
            onPostTap: (post, _) {},
            onUserTap: (_) {},
          ),
        ));
        await tester.pump();
      }, returnsNormally);
    });

    testWidgets('no optional callbacks → renders without crash', (tester) async {
      await tester.pumpWidget(_wrapCard(
        VideoPostCard(
          post: VideoPostDto.fromMap(_videoFixture),
          onPostTap: (post, _) {},
          onUserTap: (_) {},
        ),
      ));
      await tester.pump();
      expect(find.byType(VideoPostCard), findsOneWidget);
    });
  });
}
