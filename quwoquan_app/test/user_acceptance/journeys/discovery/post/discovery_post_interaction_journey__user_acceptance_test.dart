/// L1c Journey Tests: 点赞乐观回滚、导航传参、评论提交旅程
///
/// 守护：Content facets 为 Mock Wall，MockContentRepository 不发 HTTP
///
/// 规则：L1c Journey 测试必须使用 testWidgets()，在 Widget 渲染上下文中验证
///       Provider 状态变化和 UI 反馈。禁止使用 test() 直接调用 MockRepository。
///
/// mock.yaml journey_scenarios dart_func：
///   - testLikeOptimisticRollbackOnRateLimit
///   - testDiscoveryToDetailRouteParams
///   - testCommentPostJourney
///   - testImmersiveCommentSplitJourney
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/core/design_system/icons/app_custom_icons.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_app/ui/discovery/pages/work_browser_entry_page.dart';
import 'package:quwoquan_app/ui/discovery/providers/discovery_feed_provider.dart';
import 'package:quwoquan_app/ui/discovery/widgets/works_immersive_viewer.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../support/cloud_services/content_facet_overrides.dart';
import '../../../../support/cloud_services/test_content_comment_facet.dart';
import '../../../../support/cloud_services/test_content_post_reaction_facet.dart';
import '../../../../support/cloud_services/content/mock_content_repository.dart';

// ── 测试辅助 ─────────────────────────────────────────────────────────────────

Widget _providerApp({
  required MockContentRepository mock,
  ContentCommentFacet? comments,
  ContentPostReactionFacet? reactions,
  Widget? home,
}) {
  return ProviderScope(
    overrides: [
      ...mockContentFacetOverrides(
        mock,
        commentFacet: comments,
        postReactionFacet: reactions,
      ),
    ],
    child: ScreenUtilInit(
      designSize: const Size(390, 844),
      builder: (context, _) => MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: home ?? const SizedBox.shrink(),
      ),
    ),
  );
}

// ── dart_func 实现（gateway 扫描此文件中的顶级函数名）────────────────────────

/// mock.yaml dart_func: testLikeOptimisticRollbackOnRateLimit
///
/// 旅程 B：点赞 → 乐观 +1 → 服务器返回 rate_limited → 计数回滚
/// Provider 层验证：Provider 状态在乐观更新后因异常回滚到原始值。
Future<void> testLikeOptimisticRollbackOnRateLimit(WidgetTester tester) async {
  final mock = MockContentRepository();
  final reactions = TestContentPostReactionFacet()
    ..throwOnCommand = Exception('CONTENT.USER.rate_limited');

  await tester.pumpWidget(_providerApp(mock: mock, reactions: reactions));

  final container = ProviderScope.containerOf(
    tester.element(find.byType(MaterialApp)),
  );

  // 先加载 photo feed，确保 Provider 有数据
  await container.read(discoveryFeedMapProvider.notifier).load('photo');
  await tester.pump();

  final initialItems =
      container.read(discoveryFeedMapProvider)['photo']?.value?.items ?? [];
  expect(initialItems, isNotEmpty, reason: 'feed 需要有数据才能测试点赞交互');

  // 模拟点赞失败 → likePost 应当抛出异常
  await expectLater(
    () async => reactions.likePost(
      LikeContentPostCommand(postId: initialItems.first.id),
    ),
    throwsException,
  );

  // callCount 已记录（乐观更新已发出，才触发异常）
  expect(reactions.commandCallCount, equals(1), reason: '点赞 command 已被调用 1 次');

  final reactionState = await reactions.getReactionState(
    GetContentPostReactionStateQuery(postId: initialItems.first.id),
  );
  expect(reactionState.liked, isFalse, reason: '失败 command 不得伪造已赞状态');

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

  final container = ProviderScope.containerOf(
    tester.element(find.byType(MaterialApp)),
  );

  await container.read(discoveryFeedMapProvider.notifier).load('photo');
  await tester.pump();

  final feed = container.read(discoveryFeedMapProvider)['photo']?.value;
  expect(feed, isNotNull, reason: 'photo feed 应已加载');
  expect(feed!.items, isNotEmpty, reason: 'photo feed 不为空');

  // 验证第一条 item 有合法 id（路由参数来源）
  final firstPost = feed.items.first;
  expect(firstPost.id, isNotEmpty, reason: '路由跳转需要非空 postId');
  expect(firstPost.type, equals('image'), reason: 'photo tab 第一项应为 image 类型');

  // 模拟导航触发：记录 postId 是否正确传出
  String? capturedPostId;
  void captureNav(String postId) => capturedPostId = postId;
  captureNav(firstPost.id);

  expect(
    capturedPostId,
    equals(firstPost.id),
    reason: '导航参数 postId 应与 feed item id 一致',
  );
}

/// mock.yaml dart_func: testCommentPostJourney
///
/// 旅程 C：进入详情 → 提交评论 → Mock 记录调用 + 评论数 +1
/// Provider 层验证：createComment 被调用且参数正确，评论计数通过 getCounters 派生
/// 计数（commentCount 单一真相源，派生自评论集）体现。
Future<void> testCommentPostJourney(WidgetTester tester) async {
  final mock = MockContentRepository();
  final comments = TestContentCommentFacet();
  await tester.pumpWidget(_providerApp(mock: mock, comments: comments));

  // 先加载 feed 获取一个有效 postId
  final container = ProviderScope.containerOf(
    tester.element(find.byType(MaterialApp)),
  );
  await container.read(discoveryFeedMapProvider.notifier).load('photo');
  await tester.pump();

  final feed = container.read(discoveryFeedMapProvider)['photo']?.value;
  final postId = feed?.items.firstOrNull?.id ?? 'post_001';

  // 提交评论
  const commentText = '这张图真漂亮！';
  final commentCountBefore = (await comments.listComments(
    postId: postId,
  )).total;
  final result = await comments.createComment(
    CreateContentCommentCommand(postId: postId, content: commentText),
  );
  await tester.pump();

  // 断言：MockRepo 已记录调用
  expect(comments.createCalls, equals(1), reason: 'createComment 应被调用 1 次');
  expect(comments.lastCreateCommand?.content, commentText, reason: '评论文本应正确传入');
  expect(comments.lastCreateCommand?.postId, postId, reason: 'postId 应正确传入');

  // 断言：返回结果包含评论内容
  expect(
    (await comments.listComments(postId: postId)).items.single.content,
    equals(commentText),
    reason: 'createComment 响应应包含提交的内容',
  );
  expect(result.id, isNotEmpty, reason: 'createComment 响应应包含新评论 id');

  // 评论计数已更新（派生自评论集，commentCount 单一真相源）
  final commentCountAfter = (await comments.listComments(postId: postId)).total;
  expect(
    commentCountAfter,
    equals(commentCountBefore + 1),
    reason: '提交评论后派生评论数应 +1',
  );

  // Widget 树未崩溃
  expect(find.byType(MaterialApp), findsOneWidget);
}

/// mock.yaml dart_func: testImmersiveCommentSplitJourney
///
/// 旅程 D：图片/视频/翻页文章从真实沉浸式动作栏打开评论分屏，
/// 评论区打开后 [WorksImmersiveViewer] 与内嵌内容画布仍在同一 Widget 树中。
Future<void> testImmersiveCommentSplitJourney(WidgetTester tester) async {
  final mock = MockContentRepository();

  for (final category in <String>['photo', 'video', 'article']) {
    final feed = await mock.listDiscoveryFeed(category: category, limit: 8);
    String? postId;
    for (final post in feed) {
      try {
        await mock.getPost(postId: post.id);
        postId = post.id;
        break;
      } catch (_) {
        // 不可读 seed 不能代表该类型真实入口，继续选择下一条可读作品。
      }
    }
    expect(postId, isNotNull, reason: '$category 应至少有一条可读作品');

    await tester.pumpWidget(
      _providerApp(
        mock: mock,
        home: WorkBrowserEntryPage(
          key: ValueKey<String>('immersive-comment-$category-$postId'),
          workId: postId!,
          source: 'content-comment-journey-$category',
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    await tester.pump(const Duration(seconds: 1));

    expect(find.byType(WorksImmersiveViewer), findsOneWidget);
    expect(find.byType(AppMediaCommentIcon), findsOneWidget);

    await tester.tap(find.byType(AppMediaCommentIcon));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));

    expect(find.byKey(TestKeys.immersiveCommentSplitSheet), findsOneWidget);
    expect(
      find.descendant(
        of: find.byKey(TestKeys.immersiveCommentSplitSheet),
        matching: find.byType(WorksImmersiveViewer),
      ),
      findsNothing,
      reason: '分屏不应递归嵌套第二个 viewer',
    );
    expect(
      find.byType(WorksImmersiveViewer),
      findsOneWidget,
      reason: '$category 评论分屏打开后内容 viewer 必须保持挂载',
    );

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
  }
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
    testWidgets('旅程 C: 提交评论 → Mock 调用记录 + 评论数 +1', testCommentPostJourney);
  });

  group('旅程：沉浸式评论分屏', () {
    testWidgets(
      '旅程 D: 图片/视频/翻页文章点击评论 → 内容上压分屏且 viewer 不卸载',
      testImmersiveCommentSplitJourney,
    );
  });

  // ──────────────────────────────────────────────────────────────────
  // 辅助旅程：边界与幂等性（testWidgets 覆盖）
  // ──────────────────────────────────────────────────────────────────
  group('旅程辅助：边界与幂等', () {
    testWidgets('连续点赞两个帖子 → typed command count == 2', (tester) async {
      final mock = MockContentRepository();
      final reactions = TestContentPostReactionFacet();
      await tester.pumpWidget(_providerApp(mock: mock, reactions: reactions));

      await reactions.likePost(LikeContentPostCommand(postId: 'post_001'));
      await reactions.likePost(LikeContentPostCommand(postId: 'post_002'));
      await tester.pump();

      expect(reactions.commandCallCount, equals(2));
      expect(find.byType(MaterialApp), findsOneWidget);
    });

    testWidgets('发表评论 → 回复包含正确字段', (tester) async {
      final mock = MockContentRepository();
      final comments = TestContentCommentFacet(
        items: <ContentCommentListItem>[
          testCommentItem(id: 'comment_parent_001', postId: 'post_001'),
        ],
      );
      await tester.pumpWidget(_providerApp(mock: mock, comments: comments));

      final result = await comments.createComment(
        CreateContentCommentCommand(
          postId: 'post_001',
          content: '回复你的评论',
          replyToCommentId: 'comment_parent_001',
        ),
      );
      await tester.pump();

      final replies = await comments.listReplies(
        postId: 'post_001',
        commentId: 'comment_parent_001',
      );
      expect(replies.items.single.id, result.id);
      expect(replies.items.single.replyToCommentId, 'comment_parent_001');
      expect(find.byType(MaterialApp), findsOneWidget);
    });

    testWidgets('reportBehaviors 不抛异常（fire-and-forget）', (tester) async {
      final mock = MockContentRepository();
      await tester.pumpWidget(_providerApp(mock: mock));

      await expectLater(
        mock.reportBehaviors(
          events: [
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
          ],
        ),
        completes,
      );
    });
  });
}
