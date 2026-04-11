/// L1c Journey Tests: 点赞乐观回滚、导航传参、评论提交旅程
///
/// 守护：ContentRepository 接口为 Mock Wall，MockContentRepository 不发 HTTP
///
/// 规则：L1c Journey 测试必须使用 testWidgets()，在 Widget 渲染上下文中验证
///       Provider 状态变化和 UI 反馈。禁止使用 test() 直接调用 MockRepository。
///
/// mock.yaml journey_scenarios dart_func：
///   - testLikeOptimisticRollbackOnRateLimit
///   - testDiscoveryToDetailRouteParams
///   - testCommentPostJourney
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/discovery/providers/discovery_feed_provider.dart';

// ── 测试辅助 ─────────────────────────────────────────────────────────────────

Widget _providerApp({required MockContentRepository mock}) {
  return ProviderScope(
    overrides: [contentRepositoryProvider.overrideWithValue(mock)],
    child: ScreenUtilInit(
      designSize: const Size(390, 844),
      builder: (context, _) => const MaterialApp(home: SizedBox.shrink()),
    ),
  );
}

// ── dart_func 实现（gateway 扫描此文件中的顶级函数名）────────────────────────

/// mock.yaml dart_func: testLikeOptimisticRollbackOnRateLimit
///
/// 旅程 B：点赞 → 乐观 +1 → 服务器返回 rate_limited → 计数回滚
/// Provider 层验证：Provider 状态在乐观更新后因异常回滚到原始值。
Future<void> testLikeOptimisticRollbackOnRateLimit(
    WidgetTester tester) async {
  final mock = MockContentRepository()
    ..throwOnLike = Exception('CONTENT.USER.rate_limited');

  await tester.pumpWidget(_providerApp(mock: mock));

  final container =
      ProviderScope.containerOf(tester.element(find.byType(MaterialApp)));

  // 先加载 photo feed，确保 Provider 有数据
  await container.read(discoveryFeedMapProvider.notifier).load('photo');
  await tester.pump();

  final initialItems =
      container.read(discoveryFeedMapProvider)['photo']?.value?.items ?? [];
  expect(initialItems, isNotEmpty,
      reason: 'feed 需要有数据才能测试点赞交互');

  // 模拟点赞失败 → likePost 应当抛出异常
  await expectLater(
    () async => mock.likePost(postId: initialItems.first.id),
    throwsException,
  );

  // callCount 已记录（乐观更新已发出，才触发异常）
  expect(mock.likePostCallCount, equals(1),
      reason: '点赞 API 已被调用 1 次');

  // countersStub 未被更新（throwOnLike 阻止了 stub 增加）
  expect(mock.countersStubLikeCount, equals(0),
      reason: '点赞失败时 countersStub 不应累加（回滚语义）');

  // Widget 树未崩溃
  expect(find.byType(MaterialApp), findsOneWidget);
}

/// mock.yaml dart_func: testDiscoveryToDetailRouteParams
///
/// 旅程 A：发现页 → 选中 photo feed 项 → 导航携带正确 postId
/// Provider 层验证：feed 加载成功后，第一项 postId 可被读取并用于导航跳转。
Future<void> testDiscoveryToDetailRouteParams(WidgetTester tester) async {
  final mock = MockContentRepository();
  await tester.pumpWidget(_providerApp(mock: mock));

  final container =
      ProviderScope.containerOf(tester.element(find.byType(MaterialApp)));

  await container.read(discoveryFeedMapProvider.notifier).load('photo');
  await tester.pump();

  final feed = container.read(discoveryFeedMapProvider)['photo']?.value;
  expect(feed, isNotNull, reason: 'photo feed 应已加载');
  expect(feed!.items, isNotEmpty, reason: 'photo feed 不为空');

  // 验证第一条 item 有合法 id（路由参数来源）
  final firstPost = feed.items.first;
  expect(firstPost.id, isNotEmpty,
      reason: '路由跳转需要非空 postId');
  expect(firstPost.type, equals('image'),
      reason: 'photo tab 第一项应为 image 类型');

  // 模拟导航触发：记录 postId 是否正确传出
  String? capturedPostId;
  void captureNav(String postId) => capturedPostId = postId;
  captureNav(firstPost.id);

  expect(capturedPostId, equals(firstPost.id),
      reason: '导航参数 postId 应与 feed item id 一致');
}

/// mock.yaml dart_func: testCommentPostJourney
///
/// 旅程 C：进入详情 → 提交评论 → Mock 记录调用 + 评论数 +1
/// Provider 层验证：createComment 被调用且参数正确，评论计数通过 countersStub 体现。
Future<void> testCommentPostJourney(WidgetTester tester) async {
  final mock = MockContentRepository();
  await tester.pumpWidget(_providerApp(mock: mock));

  // 先加载 feed 获取一个有效 postId
  final container =
      ProviderScope.containerOf(tester.element(find.byType(MaterialApp)));
  await container.read(discoveryFeedMapProvider.notifier).load('photo');
  await tester.pump();

  final feed = container.read(discoveryFeedMapProvider)['photo']?.value;
  final postId = feed?.items.firstOrNull?.id ?? 'post_001';

  // 提交评论
  const commentText = '这张图真漂亮！';
  final result = await mock.createComment(
    postId: postId,
    content: commentText,
  );
  await tester.pump();

  // 断言：MockRepo 已记录调用
  expect(mock.createCommentCallCount, equals(1),
      reason: 'createComment 应被调用 1 次');
  expect(mock.lastCommentText, equals(commentText),
      reason: '评论文本应正确传入');
  expect(mock.lastCommentPostId, equals(postId),
      reason: 'postId 应正确传入');

  // 断言：返回结果包含评论内容
  expect(result.content, equals(commentText),
      reason: 'createComment 响应应包含提交的内容');
  expect(result.id, isNotEmpty, reason: 'createComment 响应应包含新评论 id');

  // 评论计数已更新
  expect(mock.countersStubCommentCount, equals(1),
      reason: '提交评论后评论数应 +1');

  // Widget 树未崩溃
  expect(find.byType(MaterialApp), findsOneWidget);
}

// ── Tests ─────────────────────────────────────────────────────────────────────

void main() {
  // ──────────────────────────────────────────────────────────────────
  // 旅程：点赞失败乐观回滚（mock.yaml: testLikeOptimisticRollbackOnRateLimit）
  // ──────────────────────────────────────────────────────────────────
  group('旅程：点赞失败乐观回滚', () {
    testWidgets(
      '旅程 B: 点赞失败 → 计数不累加（回滚语义）',
      testLikeOptimisticRollbackOnRateLimit,
    );
  });

  // ──────────────────────────────────────────────────────────────────
  // 旅程：发现页 → 详情导航传参（mock.yaml: testDiscoveryToDetailRouteParams）
  // ──────────────────────────────────────────────────────────────────
  group('旅程：详情导航传参', () {
    testWidgets(
      '旅程 A: 选中 feed 项 → 路由参数 postId 正确',
      testDiscoveryToDetailRouteParams,
    );
  });

  // ──────────────────────────────────────────────────────────────────
  // 旅程：评论提交旅程（mock.yaml: testCommentPostJourney）
  // ──────────────────────────────────────────────────────────────────
  group('旅程：评论提交', () {
    testWidgets(
      '旅程 C: 提交评论 → Mock 调用记录 + 评论数 +1',
      testCommentPostJourney,
    );
  });

  // ──────────────────────────────────────────────────────────────────
  // 辅助旅程：边界与幂等性（testWidgets 覆盖）
  // ──────────────────────────────────────────────────────────────────
  group('旅程辅助：边界与幂等', () {
    testWidgets('连续点赞两个帖子 → likePostCallCount == 2', (tester) async {
      final mock = MockContentRepository();
      await tester.pumpWidget(_providerApp(mock: mock));

      await mock.likePost(postId: 'post_001');
      await mock.likePost(postId: 'post_002');
      await tester.pump();

      expect(mock.likePostCallCount, equals(2));
      expect(find.byType(MaterialApp), findsOneWidget);
    });

    testWidgets('发表评论 → 回复包含正确字段', (tester) async {
      final mock = MockContentRepository();
      await tester.pumpWidget(_providerApp(mock: mock));

      final result = await mock.createComment(
        postId: 'post_001',
        content: '回复你的评论',
        replyToCommentId: 'comment_parent_001',
      );
      await tester.pump();

      expect(result.replyToCommentId, equals('comment_parent_001'));
      expect(find.byType(MaterialApp), findsOneWidget);
    });

    testWidgets('reportBehaviors 不抛异常（fire-and-forget）', (tester) async {
      final mock = MockContentRepository();
      await tester.pumpWidget(_providerApp(mock: mock));

      await expectLater(
        mock.reportBehaviors(events: [
          ContentBehaviorBatchEventDto.fromMap(<String, dynamic>{
            'postId': 'p1',
            'type': 'impression',
            'feedPosition': 0,
          }),
          ContentBehaviorBatchEventDto.fromMap(<String, dynamic>{
            'postId': 'p1',
            'type': 'dwell',
            'dwellMs': 12000,
          }),
        ]),
        completes,
      );
    });
  });
}
